"""Freeze the modelling datasets: one file per domain in ``PROCESSED_DIR``.

A row is one appeal: the first-instance judgment as input (metadata, operative
part and written reasons) and what the appellate court did with it as target.
Nothing from the appellate judgment is kept except the label, the appeal date
(for the temporal split) and the keys needed to trace the row back.

Rows pass through the same filters in every domain:

* a real appeal (``appeal_kind == "appeal"``, not a complaint);
* a confirmed pair: the header's date agrees with the matched judgment, or
  the header has no date but names the same court (see :mod:`pairs`);
* the first-instance judgment has both the operative part and reasons;
* the label is recognised (dismissed / changed / changed in part / set aside);
* one appeal per first-instance judgment (the earliest), so a text never
  appears twice with different labels.

Two evaluation schemes are stored as columns. ``split`` is temporal by appeal
date: the earliest 70 % of rows are ``train``, the next 15 % ``valid``, the
last 15 % ``test``; use it once, for the final report. ``fold`` is a
stratified 5-fold assignment (by label, fixed seed) for cross-validation
while developing, where the domains are too small for one stable test set.

Files are named after the SHA-256 of their bytes,
``appeals-<domain>-<hash8>.parquet``, and ``datasets.json`` next to them
records counts, split boundaries and inputs.

Usage::

    saos-dataset
    saos-dataset --domain labour --domain social_insurance
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from tqdm import tqdm

from saos_appeals import config

log = logging.getLogger(__name__)

SPLIT_FRACTIONS = (0.70, 0.15, 0.15)
N_FOLDS = 5
FOLD_SEED = 0

# First-instance metadata carried over from cases.parquet. Citation columns are
# left out on purpose: SAOS links a judgment to its appeal after the fact.
FIRST_COLUMNS = (
    "case_number",
    "code",
    "division_id",
    "division_name",
    "court_id",
    "court_name",
    "court_level",
    "judgment_date",
    "judgment_year",
    "judges",
    "presiding_judge",
    "keywords",
    "legal_bases",
    "regulation_journals",
    "regulation_articles",
    "operative_len",
    "reasons_len",
)

DATASET_SCHEMA = pa.schema(
    [
        ("pair_id", pa.string()),
        ("domain", pa.string()),
        ("split", pa.string()),
        ("fold", pa.int8()),
        ("label", pa.int8()),
        ("outcome", pa.string()),
        ("remand", pa.bool_()),
        ("first_case_key", pa.string()),
        ("first_sentence_id", pa.int64()),
        ("first_reasons_id", pa.int64()),
        ("first_case_number", pa.string()),
        ("first_code", pa.string()),
        ("first_division_id", pa.int64()),
        ("first_division_name", pa.string()),
        ("first_court_id", pa.int64()),
        ("first_court_name", pa.string()),
        ("first_court_level", pa.string()),
        ("first_judgment_date", pa.string()),
        ("first_judgment_year", pa.int32()),
        ("first_judges", pa.list_(pa.string())),
        ("first_presiding_judge", pa.string()),
        ("first_keywords", pa.list_(pa.string())),
        ("first_legal_bases", pa.list_(pa.string())),
        ("first_regulation_journals", pa.list_(pa.string())),
        ("first_regulation_articles", pa.list_(pa.string())),
        ("first_operative_len", pa.int32()),
        ("first_reasons_len", pa.int32()),
        ("first_operative_text", pa.string()),
        ("first_reasons_text", pa.string()),
        ("appeal_case_key", pa.string()),
        ("appeal_sentence_id", pa.int64()),
        ("appeal_court_id", pa.int64()),
        ("appeal_date", pa.string()),
        ("appeal_year", pa.int32()),
    ]
)


def select_pairs(pairs: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    """Apply the row filters from the module docstring. Returns one row per pair."""
    p = pairs.merge(
        labels[["appeal_case_key", "label", "outcome", "remand"]], on="appeal_case_key", how="left"
    )
    confirmed = (p["date_ok"] == True) | ((p["court_ok"] == True) & p["header_date"].isna())  # noqa: E712
    p = p[
        (p["appeal_kind"] == "appeal")
        & p["first_case_key"].notna()
        & confirmed
        & (p["first_operative_len"] > 0)
        & (p["first_reasons_len"] > 0)
        & p["label"].notna()
    ]
    p = p.sort_values(["first_case_key", "appeal_date", "appeal_sentence_id"])
    return p.drop_duplicates("first_case_key", keep="first")


def assign_split(df: pd.DataFrame) -> tuple[pd.Series, dict[str, str]]:
    """Temporal split by appeal date. Returns the split column and its boundaries."""
    order = df["appeal_date"].fillna("9999").rank(method="first")
    n = len(df)
    train_end = int(round(n * SPLIT_FRACTIONS[0]))
    valid_end = int(round(n * (SPLIT_FRACTIONS[0] + SPLIT_FRACTIONS[1])))
    split = pd.Series("test", index=df.index)
    split[order <= valid_end] = "valid"
    split[order <= train_end] = "train"
    dates = df["appeal_date"]
    bounds = {
        name: f"{dates[split == name].min()} .. {dates[split == name].max()}"
        for name in ("train", "valid", "test")
        if (split == name).any()
    }
    return split, bounds


def assign_folds(df: pd.DataFrame) -> pd.Series:
    """Stratified ``N_FOLDS`` folds: within each label, rows are shuffled with
    ``FOLD_SEED`` (ordered by pair_id first, so the result does not depend on
    input order) and dealt round-robin."""
    fold = pd.Series(-1, index=df.index, dtype="int8")
    rng = np.random.RandomState(FOLD_SEED)
    for _, grp in df.groupby("label"):
        idx = grp.sort_values(["first_case_key", "appeal_case_key"]).index.to_numpy().copy()
        rng.shuffle(idx)
        fold[idx] = (np.arange(len(idx)) % N_FOLDS).astype("int8")
    return fold


def read_texts(records_path: Path, ids: set[int]) -> dict[int, tuple[str, str]]:
    """``id -> (operative_text, reasons_text)`` for the given record ids, streamed."""
    pf = pq.ParquetFile(records_path)
    out: dict[int, tuple[str, str]] = {}
    for g in tqdm(range(pf.num_row_groups), desc="texts", unit="rg", dynamic_ncols=True):
        batch = pf.read_row_group(g, columns=["id", "operative_text", "reasons_text"])
        for rec_id, op, rs in zip(*(batch[c].to_pylist() for c in batch.column_names)):
            if rec_id in ids:
                out[rec_id] = (op or "", rs or "")
    return out


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def build_datasets(
    interim: Path, out_dir: Path, domains: list[str] | None = None
) -> dict[str, Any]:
    pairs = pd.read_parquet(interim / "pairs.parquet")
    labels = pd.read_parquet(interim / "labels.parquet")
    selected = select_pairs(pairs, labels)
    if domains:
        selected = selected[selected["domain"].isin(domains)]
    log.info("%d pairs selected in %d domains", len(selected), selected["domain"].nunique())

    cases = pd.read_parquet(interim / "cases.parquet", columns=["case_key", *FIRST_COLUMNS])
    cases = cases.set_index("case_key")
    ids = set(selected["first_sentence_id"].astype(int)) | set(
        selected["first_reasons_id"].astype(int)
    )
    texts = read_texts(interim / "records.parquet", ids)

    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_commit": _git_commit(),
        "split_fractions": SPLIT_FRACTIONS,
        "filters": [
            "appeal_kind == appeal",
            "pair confirmed by header date, or by court name when the header has no date",
            "first-instance judgment has operative part and reasons",
            "label in dismissed / changed / changed_partly / set_aside",
            "one appeal per first-instance judgment (earliest)",
        ],
        "files": {},
    }
    for domain, group in selected.groupby("domain", sort=True):
        rows: list[dict[str, Any]] = []
        split, bounds = assign_split(group)
        folds = assign_folds(group)
        for (_, r), sp, fd in zip(group.iterrows(), split, folds):
            first = cases.loc[r["first_case_key"]]
            op, _ = texts[int(r["first_sentence_id"])]
            _, rs = texts[int(r["first_reasons_id"])]
            if int(r["first_sentence_id"]) == int(r["first_reasons_id"]):
                op, rs = texts[int(r["first_sentence_id"])]
            row: dict[str, Any] = {
                "pair_id": f"{r['first_case_key']} -> {r['appeal_case_key']}",
                "domain": domain,
                "split": sp,
                "fold": int(fd),
                "label": int(r["label"]),
                "outcome": r["outcome"],
                "remand": bool(r["remand"]),
                "first_case_key": r["first_case_key"],
                "first_sentence_id": int(r["first_sentence_id"]),
                "first_reasons_id": int(r["first_reasons_id"]),
                "first_operative_text": op,
                "first_reasons_text": rs,
                "appeal_case_key": r["appeal_case_key"],
                "appeal_sentence_id": int(r["appeal_sentence_id"]),
                "appeal_court_id": int(r["appeal_court_id"]),
                "appeal_date": r["appeal_date"],
                "appeal_year": None if pd.isna(r["appeal_year"]) else int(r["appeal_year"]),
            }
            for col in FIRST_COLUMNS:
                value = first[col]
                if hasattr(value, "tolist"):
                    value = value.tolist()
                elif isinstance(value, float) and pd.isna(value):
                    value = None
                row[f"first_{col}"] = value
            rows.append(row)
        table = pa.Table.from_pylist(rows, schema=DATASET_SCHEMA)
        tmp = out_dir / f"appeals-{domain}.parquet.part"
        pq.write_table(table, tmp, compression="zstd")
        digest = hashlib.sha256(tmp.read_bytes()).hexdigest()
        final = out_dir / f"appeals-{domain}-{digest[:8]}.parquet"
        tmp.replace(final)
        counts = group.assign(split=split).groupby("split")["label"].agg(["size", "mean"])
        manifest["files"][domain] = {
            "file": final.name,
            "sha256": digest,
            "rows": len(rows),
            "granted_share": round(float(group["label"].mean()), 4),
            "splits": {
                name: {"rows": int(c["size"]), "granted_share": round(float(c["mean"]), 4)}
                for name, c in counts.iterrows()
            },
            "split_dates": bounds,
            "folds": {"n": N_FOLDS, "seed": FOLD_SEED, "stratified_by": "label"},
            "outcomes": group["outcome"].value_counts().to_dict(),
        }
        log.info("%s: %d rows -> %s", domain, len(rows), final.name)
    (out_dir / "datasets.json").write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="saos-dataset", description="Freeze per-domain modelling datasets."
    )
    parser.add_argument("--interim", type=Path, default=config.INTERIM_DIR)
    parser.add_argument("--out", type=Path, default=config.PROCESSED_DIR)
    parser.add_argument(
        "--domain", action="append", help="only these domains (repeatable); default: all"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    manifest = build_datasets(args.interim, args.out, args.domain)
    for domain, info in manifest["files"].items():
        log.info("%-18s %6d rows  granted %.1f%%", domain, info["rows"], 100 * info["granted_share"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
