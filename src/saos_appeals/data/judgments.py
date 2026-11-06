"""Build flat judgment tables from the extracted common-court records.

Two outputs in ``INTERIM_DIR``:

``records.parquet``
    One row per SAOS record, in file order. Raw fields kept as columns, plus
    everything derived: parsed case signature, court and division from the
    dictionary, normalised judge names, regulation keys, and the text split
    into plain ``text``, ``operative_text`` and ``reasons_text``. This is the
    only file holding text, written in row groups so it never has to fit in
    memory at once.

``cases.parquet``
    One row per court and case signature, metadata only. Merges the separate
    SENTENCE and REASONS records of the same case (``sentence_id`` /
    ``reasons_id``) and unions their keyword, regulation and citation lists.
    Small enough for pandas; pairing and census work on this file.

Usage::

    saos-judgments            # both tables
    saos-judgments --cases-only
    saos-judgments --limit 20000   # smoke test
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import re
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from tqdm import tqdm

from saos_appeals import config
from saos_appeals.data.text import html_to_text, split_operative_reasons

log = logging.getLogger(__name__)

ROW_GROUP = 2000

# --- case signatures ---------------------------------------------------------

_SIGNATURE = re.compile(r"^([IVXL]+)\s*([A-Za-z][A-Za-z\-]*?)\s*(\d+)/(\d+)$")

# Domain by code prefix after stripping the appellate-court "A". Longest first.
_DOMAIN_PREFIXES = [
    ("Am", "competition"),
    ("RC", "family"),
    ("RNs", "family"),
    ("Nsm", "family"),
    ("Np", "labour"),
    ("P", "labour"),
    ("U", "social_insurance"),
    ("G", "commercial"),
    ("C", "civil"),
    ("N", "civil"),
    ("K", "criminal"),
    ("W", "misdemeanour"),
    ("S", "other"),
]


def parse_signature(case_number: str) -> dict[str, Any]:
    """Split ``"IV Pa 47/12"`` into division numeral, code, sequence, year, domain, kind."""
    norm = re.sub(r"\s+", " ", case_number.strip())
    out: dict[str, Any] = {
        "case_number_norm": norm,
        "division_roman": None,
        "code": None,
        "case_seq": None,
        "case_year": None,
        "domain": None,
        "appeal_kind": None,
        "instance": None,
    }
    match = _SIGNATURE.match(norm)
    if not match:
        return out
    roman, code, seq, year = match.groups()
    year_int = int(year)
    if year_int < 100:
        year_int += 2000 if year_int < 50 else 1900
    appellate = code.startswith("A") and len(code) > 1 and code[1].isupper()
    base = code[1:] if appellate else code
    if len(base) > 1 and base.endswith("a"):
        kind = "appeal"
    elif len(base) > 1 and base.endswith("z"):
        kind = "complaint"
    elif len(base) > 1 and base.endswith("o"):
        kind = "other"
    else:
        kind = "first_instance"
    domain = next((d for prefix, d in _DOMAIN_PREFIXES if base.startswith(prefix)), "unknown")
    out.update(
        division_roman=roman,
        code=code,
        case_seq=int(seq),
        case_year=year_int,
        domain=domain,
        appeal_kind=kind,
        instance=2 if kind in ("appeal", "complaint") else 1,
    )
    return out


# --- judges and regulations --------------------------------------------------

_JUDGE_TITLE = re.compile(
    r"\b(?:SSO|SSR|SSA|SA|SO|SR|SN|del\.?|spr\.?|s[eę]dzia|przewodnicz[aą]cy)\b\.?", re.I
)
_PAREN = re.compile(r"\([^)]*\)")


def normalise_judge(name: str) -> str:
    name = _PAREN.sub(" ", name)
    name = _JUDGE_TITLE.sub(" ", name)
    return re.sub(r"\s+", " ", name).strip().lower()


_ARTICLES = re.compile(r"\(Dz\.\s*U\.[^)]*?-\s*(.*)\)\s*$", re.S)


def regulation_keys(regulations: Iterable[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """``("1997/553", ...)`` journal keys and ``"1997/553 art. 52 § 1"`` article keys."""
    journals: list[str] = []
    articles: list[str] = []
    for reg in regulations:
        key = f"{reg.get('journalYear')}/{reg.get('journalEntry')}"
        journals.append(key)
        match = _ARTICLES.search(reg.get("text") or "")
        if match:
            for art in match.group(1).split(";"):
                art = re.sub(r"\s+", " ", art).strip()
                if art:
                    articles.append(f"{key} {art}")
    return sorted(set(journals)), sorted(set(articles))


# --- court dictionary --------------------------------------------------------

_LABOUR_DIVISION = re.compile(r"Pracy|Ubezpiecze", re.I)


def load_divisions(path: Path) -> dict[int, dict[str, Any]]:
    """Map ``division.id`` to court and division attributes."""
    courts = json.loads(path.read_text(encoding="utf-8"))
    divisions: dict[int, dict[str, Any]] = {}
    for court in courts:
        parent = (court.get("parentCourt") or {}).get("id")
        for div in court.get("divisions", []):
            divisions[div["id"]] = {
                "division_id": div["id"],
                "division_name": div.get("name"),
                "division_type": div.get("type"),
                "court_id": court["id"],
                "court_name": court["name"],
                "court_level": court["type"],
                "parent_court_id": parent,
                "is_labour_division": bool(_LABOUR_DIVISION.search(div.get("type") or "")),
            }
    return divisions


# --- records table -----------------------------------------------------------

RECORD_SCHEMA = pa.schema(
    [
        ("id", pa.int64()),
        ("case_key", pa.string()),
        ("case_number", pa.string()),
        ("case_number_norm", pa.string()),
        ("division_roman", pa.string()),
        ("code", pa.string()),
        ("case_seq", pa.int32()),
        ("case_year", pa.int16()),
        ("domain", pa.string()),
        ("appeal_kind", pa.string()),
        ("instance", pa.int8()),
        ("judgment_type", pa.string()),
        ("judgment_date", pa.string()),
        ("judgment_year", pa.int16()),
        ("division_id", pa.int32()),
        ("division_name", pa.string()),
        ("division_type", pa.string()),
        ("court_id", pa.int32()),
        ("court_name", pa.string()),
        ("court_level", pa.string()),
        ("parent_court_id", pa.int32()),
        ("is_labour_division", pa.bool_()),
        ("judges", pa.list_(pa.string())),
        ("presiding_judge", pa.string()),
        ("judges_n", pa.int8()),
        ("keywords", pa.list_(pa.string())),
        ("legal_bases", pa.list_(pa.string())),
        ("regulation_journals", pa.list_(pa.string())),
        ("regulation_articles", pa.list_(pa.string())),
        ("cited_case_numbers", pa.list_(pa.string())),
        ("cited_judgment_ids", pa.list_(pa.int64())),
        ("summary", pa.string()),
        ("source_url", pa.string()),
        ("publication_date", pa.string()),
        ("html_len", pa.int32()),
        ("operative_len", pa.int32()),
        ("reasons_len", pa.int32()),
        ("text", pa.string()),
        ("operative_text", pa.string()),
        ("reasons_text", pa.string()),
    ]
)

TEXT_COLUMNS = ("text", "operative_text", "reasons_text")


def _judgment_year(date: str | None) -> int | None:
    if not date or not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        return None
    year = int(date[:4])
    return year if 1950 <= year <= 2030 else None


def record_to_row(record: dict[str, Any], divisions: dict[int, dict[str, Any]]) -> dict[str, Any]:
    case_number = record["courtCases"][0]["caseNumber"] if record.get("courtCases") else ""
    sig = parse_signature(case_number)
    div = divisions.get((record.get("division") or {}).get("id")) or {}
    judges = [normalise_judge(j.get("name") or "") for j in record.get("judges") or []]
    presiding = next(
        (
            normalise_judge(j.get("name") or "")
            for j in record.get("judges") or []
            if "PRESIDING_JUDGE" in (j.get("specialRoles") or [])
        ),
        None,
    )
    journals, articles = regulation_keys(record.get("referencedRegulations") or [])
    cited = record.get("referencedCourtCases") or []
    html = record.get("textContent") or ""
    text = html_to_text(html)
    if record.get("judgmentType") == "REASONS":
        operative, reasons = "", split_operative_reasons(text)[1] or text
    else:
        operative, reasons = split_operative_reasons(text)
    court_id = div.get("court_id")
    return {
        "id": record["id"],
        "case_key": f"{court_id}|{sig['case_number_norm']}" if court_id else None,
        "case_number": case_number,
        **sig,
        "judgment_type": record.get("judgmentType"),
        "judgment_date": record.get("judgmentDate"),
        "judgment_year": _judgment_year(record.get("judgmentDate")),
        "division_id": (record.get("division") or {}).get("id"),
        "division_name": div.get("division_name"),
        "division_type": div.get("division_type"),
        "court_id": court_id,
        "court_name": div.get("court_name"),
        "court_level": div.get("court_level"),
        "parent_court_id": div.get("parent_court_id"),
        "is_labour_division": div.get("is_labour_division", False),
        "judges": [j for j in judges if j],
        "presiding_judge": presiding,
        "judges_n": len(judges),
        "keywords": list(record.get("keywords") or []),
        "legal_bases": list(record.get("legalBases") or []),
        "regulation_journals": journals,
        "regulation_articles": articles,
        "cited_case_numbers": [c.get("caseNumber") for c in cited if c.get("caseNumber")],
        "cited_judgment_ids": sorted({i for c in cited for i in c.get("judgmentIds") or []}),
        "summary": record.get("summary"),
        "source_url": (record.get("source") or {}).get("judgmentUrl"),
        "publication_date": (record.get("source") or {}).get("publicationDate"),
        "html_len": len(html),
        "operative_len": len(operative),
        "reasons_len": len(reasons),
        "text": text,
        "operative_text": operative,
        "reasons_text": reasons,
    }


def iter_records(path: Path, limit: int | None = None) -> Iterator[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for n, line in enumerate(fh):
            if limit is not None and n >= limit:
                break
            yield json.loads(line)


def build_records(
    input_path: Path, out_path: Path, divisions: dict[int, dict[str, Any]], limit: int | None
) -> int:
    tmp = out_path.with_suffix(".parquet.part")
    rows: list[dict[str, Any]] = []
    total = 0
    with pq.ParquetWriter(tmp, RECORD_SCHEMA, compression="zstd") as writer:
        for record in tqdm(
            iter_records(input_path, limit), unit="rec", desc="records", dynamic_ncols=True
        ):
            rows.append(record_to_row(record, divisions))
            if len(rows) >= ROW_GROUP:
                writer.write_table(pa.Table.from_pylist(rows, schema=RECORD_SCHEMA))
                total += len(rows)
                rows = []
        if rows:
            writer.write_table(pa.Table.from_pylist(rows, schema=RECORD_SCHEMA))
            total += len(rows)
    tmp.replace(out_path)
    return total


# --- cases table -------------------------------------------------------------

LIST_COLUMNS = (
    "keywords",
    "legal_bases",
    "regulation_journals",
    "regulation_articles",
    "cited_case_numbers",
    "cited_judgment_ids",
)
CASE_META_COLUMNS = (
    "case_number",
    "case_number_norm",
    "division_roman",
    "code",
    "case_seq",
    "case_year",
    "domain",
    "appeal_kind",
    "instance",
    "division_id",
    "division_name",
    "division_type",
    "court_id",
    "court_name",
    "court_level",
    "parent_court_id",
    "is_labour_division",
)


_RECORD_TYPES = {f.name: f.type for f in RECORD_SCHEMA}
CASE_SCHEMA = pa.schema(
    [("case_key", pa.string())]
    + [(c, _RECORD_TYPES[c]) for c in CASE_META_COLUMNS]
    + [
        ("judgment_date", pa.string()),
        ("judgment_year", pa.int16()),
        ("sentence_id", pa.int64()),
        ("reasons_id", pa.int64()),
        ("decision_ids", pa.list_(pa.int64())),
        ("record_ids", pa.list_(pa.int64())),
        ("n_records", pa.int16()),
        ("has_sentence", pa.bool_()),
        ("has_reasons", pa.bool_()),
        ("operative_len", pa.int32()),
        ("reasons_len", pa.int32()),
        ("judges", pa.list_(pa.string())),
        ("presiding_judge", pa.string()),
        ("summary", pa.string()),
    ]
    + [(c, _RECORD_TYPES[c]) for c in LIST_COLUMNS]
)


def _union(values: Iterable[Any]) -> list[Any]:
    seen: set[Any] = set()
    out: list[Any] = []
    for lst in values:
        for item in lst or []:
            if item not in seen:
                seen.add(item)
                out.append(item)
    return out


def _pick_records(small: pd.DataFrame) -> pd.DataFrame:
    """Per case: main record, reasons record and bookkeeping, from scalar columns only."""
    is_sentence = small["judgment_type"] == "SENTENCE"
    is_reasons = small["judgment_type"] == "REASONS"
    small = small.assign(_prio=np.select([is_sentence, is_reasons], [0, 1], 2))
    main = small.sort_values(
        ["case_key", "_prio", "operative_len", "id"], ascending=[True, True, False, True]
    ).drop_duplicates("case_key")
    main = main.set_index("case_key")[["id", "judgment_type", "operative_len"]]
    main.columns = ["main_id", "main_type", "operative_len"]

    cand = small[is_reasons | (is_sentence & (small["reasons_len"] > 0))]
    cand = cand.assign(_prio=np.where(cand["judgment_type"] == "REASONS", 0, 1))
    cand = cand.sort_values(
        ["case_key", "_prio", "reasons_len"], ascending=[True, True, False]
    ).drop_duplicates("case_key")
    reasons = cand.set_index("case_key")[["id", "reasons_len"]]
    reasons.columns = ["reasons_id", "reasons_len"]

    grouped = small.groupby("case_key")
    agg = pd.DataFrame({"n_records": grouped["id"].size(), "record_ids": grouped["id"].agg(list)})
    decisions = small[small["judgment_type"].isin(("DECISION", "RESOLUTION", "REGULATION"))]
    agg["decision_ids"] = decisions.groupby("case_key")["id"].agg(list)

    picked = main.join(reasons, how="left").join(agg, how="left")
    picked["decision_ids"] = picked["decision_ids"].apply(
        lambda v: v if isinstance(v, list) else []
    )
    picked["has_sentence"] = picked["main_type"] == "SENTENCE"
    picked["sentence_id"] = picked["main_id"].where(picked["has_sentence"])
    picked["has_reasons"] = picked["reasons_id"].notna()
    picked["reasons_len"] = picked["reasons_len"].fillna(0)
    return picked


def build_cases(records_path: Path, out_path: Path) -> int:
    """One row per court + signature. Lists stay in Arrow; pandas sees scalar columns only."""
    meta_columns = [c for c in RECORD_SCHEMA.names if c not in TEXT_COLUMNS]
    table = pq.read_table(records_path, columns=meta_columns)
    table = table.filter(pc.is_valid(table["case_key"]))
    small = table.select(
        ["id", "case_key", "judgment_type", "operative_len", "reasons_len"]
    ).to_pandas()
    log.info("cases: %d records with a court and signature", len(small))
    picked = _pick_records(small)
    del small

    # Metadata of the main record, in file order, straight from Arrow.
    main_ids = pa.array(picked["main_id"].to_numpy(), type=pa.int64())
    main = table.filter(pc.is_in(table["id"], value_set=main_ids))
    keys = main["case_key"].to_pylist()
    picked = picked.reindex(keys)

    # Union of list columns only where a case has more than one record.
    multi_keys = pa.array(list(picked.index[picked["n_records"] > 1]), type=pa.string())
    multi = table.filter(pc.is_in(table["case_key"], value_set=multi_keys))
    multi_key_list = multi["case_key"].to_pylist()
    patched: dict[str, pa.Array] = {}
    for col in LIST_COLUMNS:
        by_key: dict[str, list[Any]] = {}
        for key, value in zip(multi_key_list, multi[col].to_pylist(), strict=True):
            by_key.setdefault(key, []).append(value)
        values = main[col].to_pylist()
        for i, key in enumerate(keys):
            if key in by_key:
                values[i] = _union(by_key[key])
        patched[col] = pa.array(values, type=RECORD_SCHEMA.field(col).type)
    del multi

    from_main = set(CASE_META_COLUMNS) | {
        "judges",
        "presiding_judge",
        "summary",
        "judgment_date",
        "judgment_year",
        "operative_len",
    }

    def column(name: str) -> pa.Array:
        if name == "case_key":
            return pa.array(keys, type=pa.string())
        if name in patched:
            return patched[name]
        if name in from_main:
            return main[name].combine_chunks()
        series = picked[name]
        if name in ("decision_ids", "record_ids"):
            return pa.array(series.tolist(), type=pa.list_(pa.int64()))
        return pa.array(series.astype(object).where(series.notna(), None).tolist())

    out = pa.table({name: column(name) for name in CASE_SCHEMA.names}).cast(CASE_SCHEMA)
    tmp = out_path.with_suffix(".parquet.part")
    pq.write_table(out, tmp, compression="zstd")
    tmp.replace(out_path)
    return out.num_rows


# --- CLI ---------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="saos-judgments", description="Build records.parquet and cases.parquet."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=config.INTERIM_DIR / "judgments-common.jsonl.gz",
        help="output of saos-extract (default: $DATA_DIR/interim/judgments-common.jsonl.gz)",
    )
    parser.add_argument(
        "--courts",
        type=Path,
        default=config.SAOS_DICTIONARIES_DIR / "commonCourts.json",
        help="court dictionary from saos-download dictionaries",
    )
    parser.add_argument("--out", type=Path, default=config.INTERIM_DIR)
    parser.add_argument("--limit", type=int, default=None, help="only the first N records")
    parser.add_argument(
        "--cases-only", action="store_true", help="rebuild cases.parquet from records.parquet"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args.out.mkdir(parents=True, exist_ok=True)
    records_path = args.out / "records.parquet"
    cases_path = args.out / "cases.parquet"
    if not args.cases_only:
        divisions = load_divisions(args.courts)
        n = build_records(args.input, records_path, divisions, args.limit)
        log.info("records.parquet: %d rows", n)
    n = build_cases(records_path, cases_path)
    log.info("cases.parquet: %d rows", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
