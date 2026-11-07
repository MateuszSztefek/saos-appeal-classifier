"""Data-quality checks on the SAOS dump, as seen through the interim tables.

Every check returns one or more rows of ``(issue, count, out_of, note, example)``
so that a notebook can show them as a table and plot the interesting ones.
Only metadata columns of ``records.parquet`` are read; text-based checks use
the small ruling texts in ``labels.parquet`` and the frozen datasets.

Usage in a notebook::

    from saos_appeals import quality
    tables = quality.load()
    report = quality.run_all(tables)
"""

from __future__ import annotations

import glob
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from saos_appeals import config

RECORD_COLUMNS = [
    "id",
    "case_key",
    "case_number",
    "code",
    "domain",
    "appeal_kind",
    "judgment_type",
    "judgment_date",
    "judgment_year",
    "division_type",
    "court_id",
    "court_name",
    "court_level",
    "parent_court_id",
    "is_labour_division",
    "judges",
    "keywords",
    "legal_bases",
    "cited_case_numbers",
    "cited_judgment_ids",
    "summary",
    "publication_date",
    "html_len",
    "operative_len",
    "reasons_len",
]


@dataclass
class Tables:
    records: pd.DataFrame
    cases: pd.DataFrame
    pairs: pd.DataFrame
    labels: pd.DataFrame
    datasets: pd.DataFrame  # concatenated frozen datasets, text columns dropped


def load(interim: Path = config.INTERIM_DIR, processed: Path = config.PROCESSED_DIR) -> Tables:
    records = pq.read_table(interim / "records.parquet", columns=RECORD_COLUMNS).to_pandas()
    cases = pd.read_parquet(interim / "cases.parquet")
    pairs = pd.read_parquet(interim / "pairs.parquet")
    labels = pd.read_parquet(interim / "labels.parquet")
    parts = []
    for f in sorted(glob.glob(str(processed / "appeals-*.parquet"))):
        d = pd.read_parquet(f)
        d["anon_tokens"] = d["first_reasons_text"].str.count(r"\(\.\.\.\)")
        parts.append(d.drop(columns=["first_operative_text", "first_reasons_text"]))
    datasets = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    return Tables(records, cases, pairs, labels, datasets)


def _row(issue: str, count: int, out_of: int, note: str = "", example: Any = "") -> dict[str, Any]:
    return {
        "issue": issue,
        "count": int(count),
        "out_of": int(out_of),
        "share": round(count / out_of, 4) if out_of else None,
        "note": note,
        "example": str(example)[:120],
    }


# --- checks on records -------------------------------------------------------


def empty_texts(t: Tables) -> list[dict[str, Any]]:
    r = t.records
    sent = r[r["judgment_type"] == "SENTENCE"]
    reas = r[r["judgment_type"] == "REASONS"]
    empty_sent = sent[sent["html_len"] == 0]
    by_level = empty_sent["court_level"].value_counts().to_dict()
    return [
        _row(
            "SENTENCE record with empty textContent",
            len(empty_sent),
            len(sent),
            f"by court level {by_level}; the judgment exists in SAOS but carries no text",
            empty_sent["id"].iloc[0] if len(empty_sent) else "",
        ),
        _row(
            "REASONS record with empty textContent",
            (reas["html_len"] == 0).sum(),
            len(reas),
            "reasons announced but not published",
            reas.loc[reas["html_len"] == 0, "id"].head(3).tolist(),
        ),
    ]


def dates(t: Tables) -> list[dict[str, Any]]:
    r = t.records
    bad_year = r[
        r["judgment_year"].isna() | (r["judgment_year"] < 1990) | (r["judgment_year"] > 2026)
    ]
    pub = pd.to_datetime(r["publication_date"], errors="coerce")
    jd = pd.to_datetime(r["judgment_date"], errors="coerce")
    pub_before = r[pub.notna() & jd.notna() & (pub < jd)]
    c = t.cases
    rec_date = r.set_index("id")["judgment_date"]
    two = c[
        c["sentence_id"].notna() & c["reasons_id"].notna() & (c["sentence_id"] != c["reasons_id"])
    ]
    d1 = pd.to_datetime(two["sentence_id"].map(rec_date), errors="coerce")
    d2 = pd.to_datetime(two["reasons_id"].map(rec_date), errors="coerce")
    gap = (d2 - d1).dt.days
    return [
        _row(
            "judgment date outside 1990–2026 or unparseable",
            len(bad_year),
            len(r),
            "typos in the source, e.g. year 208 or 3013",
            list(zip(bad_year["id"], bad_year["judgment_date"], strict=False))[:3],
        ),
        _row(
            "published before the judgment date",
            len(pub_before),
            len(r),
            "publication_date earlier than judgment_date",
            pub_before[["id", "judgment_date", "publication_date"]].head(2).values.tolist(),
        ),
        _row(
            "reasons record dated before its sentence",
            (gap < 0).sum(),
            len(two),
            "in cases with separate SENTENCE and REASONS records",
            two.loc[gap < 0, "case_key"].head(3).tolist(),
        ),
        _row(
            "reasons record dated > 1 year after its sentence",
            (gap > 365).sum(),
            len(two),
            "REASONS judgment_date is often the date reasons were written, not the ruling date",
            two.loc[gap > 365, "case_key"].head(3).tolist(),
        ),
    ]


def signatures(t: Tables) -> list[dict[str, Any]]:
    r = t.records
    bad = r[r["code"].isna()]
    digit_div = bad[bad["case_number"].str.contains(r"^[IVXL]+\s?\d", regex=True, na=False)]
    forms = Counter(re.sub(r"\d+", "N", s) for s in bad["case_number"])
    c = t.cases
    multi_sent = c[c["n_records"] > 1]
    per_type = r.groupby(["case_key", "judgment_type"]).size().rename("n").reset_index()
    dup_sent = per_type[(per_type["judgment_type"] == "SENTENCE") & (per_type["n"] > 1)]
    return [
        _row(
            "case signature not in the standard form",
            len(bad),
            len(r),
            f"most common shapes {forms.most_common(4)}",
            bad["case_number"].head(3).tolist(),
        ),
        _row(
            "  of which a digit after the division numeral (I 2C 15/13)",
            len(digit_div),
            len(bad),
            "sub-divisions numbered with digits in a few courts",
            digit_div["case_number"].head(3).tolist(),
        ),
        _row(
            "case with more than one SENTENCE record",
            len(dup_sent),
            len(c),
            "same court and signature, several sentences "
            "(re-trial, partial judgment or duplicate upload)",
            dup_sent["case_key"].head(2).tolist(),
        ),
        _row(
            "case key shared by 3+ records",
            (c["n_records"] >= 3).sum(),
            len(multi_sent),
            "out of cases with more than one record",
            c.loc[c["n_records"] >= 3, "case_key"].head(3).tolist(),
        ),
    ]


def divisions(t: Tables) -> list[dict[str, Any]]:
    r = t.records[t.records["code"].notna()]
    labour_code = r["domain"].isin(["labour", "social_insurance"])
    mismatch_a = r[labour_code & ~r["is_labour_division"]]
    mismatch_b = r[~labour_code & r["is_labour_division"]]
    return [
        _row(
            "labour / social-insurance signature outside a labour division",
            len(mismatch_a),
            labour_code.sum(),
            f"division types seen {mismatch_a['division_type'].value_counts().head(3).to_dict()}",
            mismatch_a["case_number"].head(3).tolist(),
        ),
        _row(
            "other signature inside a labour division",
            len(mismatch_b),
            r["is_labour_division"].sum(),
            f"codes seen {mismatch_b['code'].value_counts().head(4).to_dict()}",
            mismatch_b["case_number"].head(3).tolist(),
        ),
    ]


def judges(t: Tables) -> list[dict[str, Any]]:
    r = t.records
    n_judges = r["judges"].map(len)
    flat = [j for js in r["judges"] for j in js]
    anon = [
        j for j in flat if re.fullmatch(r"(?:[a-ząćęłńóśźż]\.\s?)+(?:\(\d+\))?", j) or "(...)" in j
    ]
    joined = [j for j in flat if " i " in j]
    return [
        _row(
            "record without any judge",
            (n_judges == 0).sum(),
            len(r),
            "",
            r.loc[n_judges == 0, "id"].head(3).tolist(),
        ),
        _row(
            "judge name anonymised to initials",
            len(anon),
            len(flat),
            "anonymisation applied to the bench, not only to parties",
            anon[:3],
        ),
        _row(
            "two judges in one name field",
            len(joined),
            len(flat),
            "names joined with 'i' in the source",
            joined[:2],
        ),
    ]


def enrichment_coverage(t: Tables) -> list[dict[str, Any]]:
    r = t.records
    no_kw = r["keywords"].map(len) == 0
    no_lb = r["legal_bases"].map(len) == 0
    no_sum = r["summary"].isna()

    def ids(mask: pd.Series) -> list[int]:
        return r.loc[mask, "id"].head(3).tolist()

    return [
        _row("record without keywords", no_kw.sum(), len(r), "", ids(no_kw)),
        _row("record without legal bases", no_lb.sum(), len(r), "", ids(no_lb)),
        _row("record without summary", no_sum.sum(), len(r), "", ids(no_sum)),
    ]


# --- checks on links and pairing ----------------------------------------------


def saos_links(t: Tables) -> list[dict[str, Any]]:
    """SAOS' own ``judgmentIds`` cross-references, judged against the court hierarchy."""
    c = t.cases
    pairs_of_ids = zip(c["case_key"], c["record_ids"], strict=False)
    id2case = {int(i): k for k, ids in pairs_of_ids for i in ids}
    meta = c.set_index("case_key")[["court_id", "parent_court_id"]].to_dict("index")
    appeals = c[
        c["appeal_kind"].isin(["appeal", "complaint"])
        & c["court_level"].isin(["REGIONAL", "APPEAL"])
    ]
    kinds: Counter[str] = Counter()
    examples: dict[str, str] = {}
    total = 0
    for key, cid, ids in zip(
        appeals["case_key"], appeals["court_id"], appeals["cited_judgment_ids"], strict=False
    ):
        for i in ids:
            target = id2case.get(int(i))
            if target is None or target == key:
                continue
            total += 1
            m = meta[target]
            if m["parent_court_id"] == cid:
                kind = "child court (plausible)"
            elif m["court_id"] == cid:
                kind = "same court"
            else:
                kind = "unrelated court"
            kinds[kind] += 1
            examples.setdefault(kind, f"{key} -> {target}")
    return [
        _row(
            f"SAOS judgmentIds link from an appeal to a case in: {k}",
            v,
            total,
            "links resolved against the court dictionary; example is appeal -> linked case",
            examples[k],
        )
        for k, v in kinds.most_common()
    ]


def pairing(t: Tables) -> list[dict[str, Any]]:
    p = t.pairs
    ap = p[p["appeal_kind"] == "appeal"]
    with_text = ap[ap["appeal_operative_len"] > 0]
    header = with_text[with_text["header_found"]]
    sig = header[header["header_signature"].notna()]
    matched = sig[sig["first_case_key"].notna()]
    # .eq(True) is null-safe: date_ok / court_ok are None when the header lacks the field
    confirmed = matched[
        matched["date_ok"].eq(True) | (matched["court_ok"].eq(True) & matched["header_date"].isna())
    ]

    def keys(df: pd.DataFrame) -> list[str]:
        return df["appeal_case_key"].head(3).tolist()

    return [
        _row(
            "appeal sentence without text",
            len(ap) - len(with_text),
            len(ap),
            "",
            keys(ap[ap["appeal_operative_len"] == 0]),
        ),
        _row(
            "appeal text without a recognisable header",
            len(with_text) - len(header),
            len(with_text),
            "reopening (skarga o wznowienie), typos, transcripts",
            keys(with_text[~with_text["header_found"]]),
        ),
        _row(
            "header without a first-instance signature",
            len(header) - len(sig),
            len(header),
            "",
            keys(header[header["header_signature"].isna()]),
        ),
        _row(
            "first-instance judgment not published in SAOS",
            len(sig) - len(matched),
            len(sig),
            "the header names a signature that no child court has in the dump",
            keys(sig[sig["first_case_key"].isna()]),
        ),
        _row(
            "matched by signature but header date or court disagrees",
            len(matched) - len(confirmed),
            len(matched),
            "sibling courts reuse signatures; another judgment in the same case",
            keys(matched[~matched.index.isin(confirmed.index)]),
        ),
    ]


def coverage_by_court(t: Tables, min_appeals: int = 100) -> pd.DataFrame:
    """Per appellate court: share of appeals whose first-instance judgment exists in SAOS."""
    p = t.pairs
    ap = p[(p["appeal_kind"] == "appeal") & p["header_signature"].notna()]
    g = ap.groupby("appeal_court_name").agg(
        appeals=("appeal_case_key", "size"),
        first_in_saos=("first_case_key", lambda s: s.notna().sum()),
    )
    g["coverage"] = (g["first_in_saos"] / g["appeals"]).round(3)
    return g[g["appeals"] >= min_appeals].sort_values("coverage", ascending=False)


def empty_text_by_year(t: Tables) -> pd.DataFrame:
    r = t.records[t.records["judgment_type"] == "SENTENCE"]
    g = r.groupby("judgment_year")["html_len"].agg(records="size", empty=lambda s: (s == 0).sum())
    g["share"] = (g["empty"] / g["records"]).round(3)
    return g[(g.index >= 2000) & (g.index <= 2026)]


# --- checks on ruling and reasons texts ---------------------------------------


def texts(t: Tables) -> list[dict[str, Any]]:
    lab = t.labels
    rt = lab["ruling_text"].fillna("")
    transcripts = lab[
        rt.str.contains(r"poczatektekstu|\[Przewodnicz|\d\d:\d\d:\d\d\.\d", regex=True)
    ]
    typos = lab[
        (lab["outcome"] == "unknown")
        & (rt.str.len() > 0)
        & rt.str.contains(r"\boddal\w*\s+ap\w+", regex=True)
    ]
    rows = [
        _row(
            "appellate text is a hearing transcript, not a judgment",
            len(transcripts),
            len(lab),
            "OCR/ASR output with timestamps",
            transcripts["appeal_case_key"].head(2).tolist(),
        ),
        _row(
            "ruling unrecognised although the text speaks of dismissing the appeal",
            len(typos),
            len(lab),
            "typos such as oddal apelacje, or the reasons uploaded in place of the sentence",
            typos["ruling_text"].str.strip().head(2).tolist(),
        ),
        _row(
            "ruling text empty (sentence ends with the header)",
            (rt.str.len() == 0).sum(),
            len(lab),
            "",
            lab.loc[rt.str.len() == 0, "appeal_case_key"].head(3).tolist(),
        ),
    ]
    d = t.datasets
    if len(d):
        per_1k = 1000 * d["anon_tokens"] / d["first_reasons_len"].clip(lower=1)
        rows.append(
            _row(
                "first-instance reasons with heavy anonymisation (> 5 '(...)' per 1k chars)",
                (per_1k > 5).sum(),
                len(d),
                f"median {per_1k.median():.1f} per 1k chars across the frozen datasets",
                d.loc[per_1k > 5, "pair_id"].head(2).tolist(),
            )
        )
        rows.append(
            _row(
                "first-instance reasons shorter than 2,000 chars",
                (d["first_reasons_len"] < 2000).sum(),
                len(d),
                "likely truncated or only a fragment published",
                d.loc[d["first_reasons_len"] < 2000, "pair_id"].head(2).tolist(),
            )
        )
    return rows


def run_all(t: Tables) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for check in (
        empty_texts,
        dates,
        signatures,
        divisions,
        judges,
        enrichment_coverage,
        saos_links,
        pairing,
        texts,
    ):
        rows.extend(check(t))
    return pd.DataFrame(rows)
