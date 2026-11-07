"""Pair second-instance cases with the first-instance judgment they review.

An appellate judgment names the judgment under review in its header::

    na skutek apelacji pozwanego
    od wyroku Sądu Rejonowego w Gliwicach
    z dnia 20 października 2008 r. sygn. akt VI P 1651/07

This module reads that header from ``operative_text``, adds the signatures
SAOS itself extracted (``cited_case_numbers``) and looks the signature up in
``cases.parquet``. A match is accepted only when the first-instance court is a
direct child of the appellate court in the court dictionary and its judgment
is older than the appeal. SAOS' own ``judgmentIds`` links are not trusted:
they sometimes point at a case with the same signature in another court.

Output, one row per second-instance case (matched or not), in ``INTERIM_DIR``::

    pairs.parquet            appeal case, header fields, matched first-instance case, flags

and a per-domain census in ``results/pairing-census.csv``.

Usage::

    saos-pair
    saos-pair --domain labour --domain social_insurance
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from tqdm import tqdm

from saos_appeals import config
from saos_appeals.data.judgments import parse_signature

log = logging.getLogger(__name__)

HEADER_WINDOW = 900  # characters after "od wyroku" that can hold date and signature

# --- header parsing ----------------------------------------------------------

_CHALLENGED = re.compile(
    r"\b(?:od|na)\s+(?:wyrok(?:u|ów)?|postanowieni[ae]|orzecze[nń]i?a)\b", re.I
)
_LEVEL = re.compile(r"S[ąa]du\s+(Rejonowego|Okr[ęe]gowego|Apelacyjnego)", re.I)
# The court phrase runs from the level word to the date or signature that follows it.
_COURT_PHRASE = re.compile(
    r"S[ąa]du\s+(?:Rejonowego|Okr[ęe]gowego|Apelacyjnego)([^\n]{0,160}?)(?=\n|z\s+dnia|sygn)", re.I
)
# Words that do not identify a court: level, division, "Sąd Pracy" suffixes, prepositions.
_GENERIC_COURT_WORDS = {
    "sąd", "sądu", "rejonowy", "rejonowego", "okręgowy", "okręgowego", "apelacyjny",
    "apelacyjnego", "w", "we", "dla", "i", "pracy", "ubezpieczeń", "społecznych",
    "wydział", "wydziału", "wydziale", "cywilny", "cywilnego", "karny", "karnego",
    "gospodarczy", "gospodarczego", "rodzinny", "rodzinnego", "nieletnich", "ośrodek",
    "ośrodka", "zamiejscowy", "zamiejscowego", "m.", "st.", "m.st.",
}  # fmt: skip
_MONTHS = {
    name: i + 1
    for i, name in enumerate(
        (
            "stycznia lutego marca kwietnia maja czerwca lipca sierpnia "
            "września października listopada grudnia"
        ).split()
    )
}
_DATE = re.compile(
    r"z\s+dnia\s+(\d{1,2})\s*(?:(" + "|".join(_MONTHS) + r")|[./-]\s*(\d{1,2})\s*[./-])\s*(\d{4})",
    re.I,
)
_SIG_IN_TEXT = re.compile(r"\b([IVXL]{1,5})\s?([A-Z][A-Za-z]{0,4})\s?(\d{1,6})\s?/\s?(\d{2,4})\b")

_LEVELS = {"rej": "DISTRICT", "okr": "REGIONAL", "ape": "APPEAL"}


def _iso(day: str, month_name: str | None, month_num: str | None, year: str) -> str | None:
    month = _MONTHS[month_name.lower()] if month_name else int(month_num or 0)
    if not 1 <= month <= 12 or not 1 <= int(day) <= 31:
        return None
    return f"{int(year):04d}-{month:02d}-{int(day):02d}"


def court_tokens(name: str) -> set[str]:
    """Words that identify a court: ``"Sąd Rejonowy dla Warszawy-Mokotowa w Warszawie"``
    gives ``{"warszawy", "mokotowa", "warszawie"}``. Anonymised bits like ``"W."``
    or ``"(...)"`` are dropped, so an anonymised header gives an empty set."""
    out: set[str] = set()
    for tok in re.split(r"[\s\-–]+", name.lower().replace(",", "")):
        if not tok or tok in _GENERIC_COURT_WORDS or re.fullmatch(r"[ivxl]+", tok):
            continue
        if len(tok) <= 2 or tok.endswith(".") or "(" in tok or ")" in tok:
            continue
        out.add(tok)
    return out


def parse_header(operative_text: str) -> dict[str, Any]:
    """Pull the challenged judgment's court, date and signature(s) from a header."""
    out: dict[str, Any] = {
        "header_found": False,
        "header_level": None,
        "header_court": None,
        "header_date": None,
        "header_signature": None,
        "header_signatures": [],
    }
    hit = _CHALLENGED.search(operative_text)
    if not hit:
        return out
    window = operative_text[hit.end() : hit.end() + HEADER_WINDOW]
    out["header_found"] = True
    level = _LEVEL.search(window)
    if level:
        out["header_level"] = _LEVELS[level.group(1).lower()[:3]]
    court = _COURT_PHRASE.search(window)
    if court:
        out["header_court"] = re.sub(r"\s+", " ", court.group(0)).strip(" -–")
    date = _DATE.search(window)
    after = window
    if date:
        out["header_date"] = _iso(date.group(1), date.group(2), date.group(3), date.group(4))
        after = window[date.end() :]
    sigs = [
        parse_signature(f"{m.group(1)} {m.group(2)} {m.group(3)}/{m.group(4)}")
        for m in _SIG_IN_TEXT.finditer(after)
    ]
    sigs = [s["case_number_norm"] for s in sigs if s["code"]]
    out["header_signatures"] = list(dict.fromkeys(sigs))
    out["header_signature"] = out["header_signatures"][0] if sigs else None
    return out


def read_headers(records_path: Path, sentence_ids: set[int]) -> dict[int, dict[str, Any]]:
    """Parse the header of every SENTENCE record in ``sentence_ids`` (streamed)."""
    pf = pq.ParquetFile(records_path)
    headers: dict[int, dict[str, Any]] = {}
    for g in tqdm(range(pf.num_row_groups), desc="headers", unit="rg", dynamic_ncols=True):
        batch = pf.read_row_group(g, columns=["id", "operative_text"])
        for rec_id, text in zip(batch["id"].to_pylist(), batch["operative_text"].to_pylist()):
            if rec_id in sentence_ids and text:
                headers[rec_id] = parse_header(text)
    return headers


def _plain(value: Any) -> Any:
    """pandas scalars to plain Python: NaN -> None, numpy ints -> int, arrays -> list."""
    if isinstance(value, float) and value != value:
        return None
    if isinstance(value, np.generic):
        return None if (isinstance(value, np.floating) and np.isnan(value)) else value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


# --- matching ----------------------------------------------------------------

SigKey = tuple[int, str, str, int, int]  # parent_court_id, division roman, code, seq, year


def _key(parent: int, sig: dict[str, Any]) -> SigKey:
    return (parent, sig["division_roman"], sig["code"], sig["case_seq"], sig["case_year"])


def _lower_index(cases: pd.DataFrame) -> dict[SigKey, list[dict[str, Any]]]:
    """Cases that can be reviewed, keyed by parent court and parsed signature."""
    lower = cases[cases["parent_court_id"].notna() & cases["code"].notna()]
    index: dict[SigKey, list[dict[str, Any]]] = defaultdict(list)
    cols = [
        "case_key",
        "court_id",
        "court_name",
        "court_level",
        "code",
        "judgment_date",
        "sentence_id",
        "reasons_id",
        "has_sentence",
        "has_reasons",
        "operative_len",
        "reasons_len",
    ]
    for row in lower[cols + ["parent_court_id", "division_roman", "case_seq", "case_year"]].to_dict(
        "records"
    ):
        key = (
            int(row["parent_court_id"]),
            row["division_roman"],
            row["code"],
            int(row["case_seq"]),
            int(row["case_year"]),
        )
        index[key].append({c: _plain(row[c]) for c in cols})
    return index


def match_one(
    appeal: dict[str, Any], header: dict[str, Any], index: dict[SigKey, list[dict[str, Any]]]
) -> dict[str, Any]:
    """Find the first-instance case of one appeal. Returns match columns (nulls if none)."""
    out: dict[str, Any] = {
        "match_method": None,
        "n_candidates": 0,
        "court_ok": None,
        "date_ok": None,
        "first_case_key": None,
    }
    header_sigs = header.get("header_signatures") or []
    appeal_date = appeal["judgment_date"]
    header_date = header.get("header_date")
    header_court = court_tokens(header.get("header_court") or "")
    # Signature and date alone, without the court hierarchy, are not enough:
    # "I C 312/12" decided on the same day exists in several courts. And the
    # hierarchy alone is not enough either: sibling courts under the same
    # appellate court reuse signatures, so the header's court name must agree
    # with the candidate's whenever the header names one.
    sources: list[tuple[str, list[str]]] = [
        ("header", header_sigs),
        ("cited", list(appeal["cited_case_numbers"])),  # numpy array from pandas
    ]
    for method, signatures in sources:
        candidates: list[dict[str, Any]] = []
        for sig_text in signatures:
            sig = parse_signature(sig_text)
            if not sig["code"] or sig["instance"] != 1:
                continue
            for cand in index.get(_key(appeal["court_id"], sig), []):
                cand_date = cand["judgment_date"]
                if cand_date and appeal_date and cand_date >= appeal_date:
                    continue
                if header_court and not court_tokens(cand["court_name"]) <= header_court:
                    continue
                candidates.append(cand)
        if not candidates:
            continue
        chosen = candidates
        if header_date:
            exact = [c for c in candidates if c["judgment_date"] == header_date]
            if exact:
                chosen = exact
        best = chosen[0]
        out.update(
            match_method=method,
            n_candidates=len(candidates),
            court_ok=True if header_court else None,
            date_ok=(best["judgment_date"] == header_date) if header_date else None,
            first_case_key=best["case_key"],
            first_court_id=best["court_id"],
            first_court_name=best["court_name"],
            first_court_level=best["court_level"],
            first_code=best["code"],
            first_date=best["judgment_date"],
            first_sentence_id=best["sentence_id"],
            first_reasons_id=best["reasons_id"],
            first_has_sentence=bool(best["has_sentence"]),
            first_has_reasons=bool(best["has_reasons"]),
            first_operative_len=best["operative_len"],
            first_reasons_len=best["reasons_len"],
        )
        return out
    return out


PAIR_SCHEMA = pa.schema(
    [
        ("appeal_case_key", pa.string()),
        ("appeal_sentence_id", pa.int64()),
        ("appeal_reasons_id", pa.int64()),
        ("appeal_court_id", pa.int64()),
        ("appeal_court_name", pa.string()),
        ("appeal_court_level", pa.string()),
        ("appeal_code", pa.string()),
        ("domain", pa.string()),
        ("appeal_kind", pa.string()),
        ("is_labour_division", pa.bool_()),
        ("appeal_date", pa.string()),
        ("appeal_year", pa.int32()),
        ("appeal_has_sentence", pa.bool_()),
        ("appeal_operative_len", pa.int32()),
        ("appeal_reasons_len", pa.int32()),
        ("header_found", pa.bool_()),
        ("header_level", pa.string()),
        ("header_court", pa.string()),
        ("header_date", pa.string()),
        ("header_signature", pa.string()),
        ("header_signatures", pa.list_(pa.string())),
        ("match_method", pa.string()),
        ("n_candidates", pa.int32()),
        ("court_ok", pa.bool_()),
        ("date_ok", pa.bool_()),
        ("first_case_key", pa.string()),
        ("first_court_id", pa.int64()),
        ("first_court_name", pa.string()),
        ("first_court_level", pa.string()),
        ("first_code", pa.string()),
        ("first_date", pa.string()),
        ("first_sentence_id", pa.int64()),
        ("first_reasons_id", pa.int64()),
        ("first_has_sentence", pa.bool_()),
        ("first_has_reasons", pa.bool_()),
        ("first_operative_len", pa.int32()),
        ("first_reasons_len", pa.int32()),
    ]
)


def build_pairs(
    cases_path: Path, records_path: Path, out_path: Path, domains: list[str] | None = None
) -> pd.DataFrame:
    cases = pq.read_table(cases_path).to_pandas()
    appeals = cases[
        cases["appeal_kind"].isin(("appeal", "complaint"))
        & cases["court_level"].isin(("REGIONAL", "APPEAL"))
    ]
    if domains:
        appeals = appeals[appeals["domain"].isin(domains)]
    log.info("%d second-instance cases, reading headers", len(appeals))
    sentence_ids = {int(i) for i in appeals["sentence_id"].dropna()}
    headers = read_headers(records_path, sentence_ids)
    log.info("headers parsed for %d cases, matching", len(headers))

    index = _lower_index(cases)
    rows: list[dict[str, Any]] = []
    for appeal in tqdm(
        appeals.to_dict("records"), desc="pairs", unit="case", dynamic_ncols=True
    ):
        sid = appeal["sentence_id"]
        header = headers.get(int(sid), {}) if pd.notna(sid) else {}
        row: dict[str, Any] = {
            "appeal_case_key": appeal["case_key"],
            "appeal_sentence_id": None if pd.isna(sid) else int(sid),
            "appeal_reasons_id": None
            if pd.isna(appeal["reasons_id"])
            else int(appeal["reasons_id"]),
            "appeal_court_id": int(appeal["court_id"]),
            "appeal_court_name": appeal["court_name"],
            "appeal_court_level": appeal["court_level"],
            "appeal_code": appeal["code"],
            "domain": appeal["domain"],
            "appeal_kind": appeal["appeal_kind"],
            "is_labour_division": bool(appeal["is_labour_division"]),
            "appeal_date": appeal["judgment_date"],
            "appeal_year": None if pd.isna(appeal["judgment_year"]) else int(appeal["judgment_year"]),
            "appeal_has_sentence": bool(appeal["has_sentence"]),
            "appeal_operative_len": int(appeal["operative_len"]),
            "appeal_reasons_len": int(appeal["reasons_len"]),
            "header_found": bool(header.get("header_found", False)),
            "header_level": header.get("header_level"),
            "header_court": header.get("header_court"),
            "header_date": header.get("header_date"),
            "header_signature": header.get("header_signature"),
            "header_signatures": list(header.get("header_signatures") or []),
        }
        row.update(match_one(appeal, header, index))
        rows.append({k: _plain(v) for k, v in row.items()})

    table = pa.Table.from_pylist(rows, schema=PAIR_SCHEMA)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".parquet.part")
    pq.write_table(table, tmp, compression="zstd")
    tmp.replace(out_path)
    return table.to_pandas()


# --- census ------------------------------------------------------------------


def census(pairs: pd.DataFrame) -> pd.DataFrame:
    """Per domain and appeal code: how many appeals, how many paired, with what text.

    ``confirmed`` pairs are those where the header's date agrees with the
    matched judgment, or the header gives no date but names the same court
    (same court and signature with another date is a different judgment in
    that case, e.g. after a remand). ``usable`` adds the requirement that both
    sides have a sentence text.
    """
    p = pairs.assign(
        matched=pairs["first_case_key"].notna(),
        with_text=pairs["appeal_operative_len"] > 0,
    )

    def flag(column: str) -> pd.Series:  # nullable bool -> plain bool, null is False
        return p[column].astype("boolean").fillna(False).astype(bool)

    p["confirmed"] = p["matched"] & (
        flag("date_ok") | (flag("court_ok") & p["header_date"].isna())
    )
    p["usable"] = p["confirmed"] & p["with_text"] & flag("first_has_sentence")
    p["usable_with_reasons"] = p["usable"] & flag("first_has_reasons")
    p["ambiguous"] = p["usable"] & (p["n_candidates"] > 1) & ~flag("date_ok")
    p["labour_div"] = p["is_labour_division"]
    out = (
        p.groupby(["domain", "appeal_code", "appeal_court_level"], dropna=False)
        .agg(
            appeals=("appeal_case_key", "size"),
            with_text=("with_text", "sum"),
            header_found=("header_found", "sum"),
            matched=("matched", "sum"),
            confirmed=("confirmed", "sum"),
            usable=("usable", "sum"),
            usable_with_reasons=("usable_with_reasons", "sum"),
            ambiguous=("ambiguous", "sum"),
            in_labour_division=("labour_div", "sum"),
        )
        .reset_index()
        .sort_values("usable", ascending=False)
    )
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="saos-pair", description="Pair second-instance cases with first-instance judgments."
    )
    parser.add_argument("--cases", type=Path, default=config.INTERIM_DIR / "cases.parquet")
    parser.add_argument("--records", type=Path, default=config.INTERIM_DIR / "records.parquet")
    parser.add_argument("--out", type=Path, default=config.INTERIM_DIR / "pairs.parquet")
    parser.add_argument(
        "--census",
        type=Path,
        default=config.RESULTS_DIR / "pairing-census.csv",
        help="per-domain summary CSV (default: results/pairing-census.csv)",
    )
    parser.add_argument(
        "--domain", action="append", help="restrict to these domains (repeatable); default: all"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    pairs = build_pairs(args.cases, args.records, args.out, args.domain)
    summary = census(pairs)
    args.census.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.census, index=False, lineterminator="\n")
    matched = int(pairs["first_case_key"].notna().sum())
    log.info(
        "done: %d second-instance cases, %d paired, %d usable (both texts); census in %s",
        len(pairs),
        matched,
        int(summary["usable"].sum()),
        args.census,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
