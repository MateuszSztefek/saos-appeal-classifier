"""Label appeals by what the appellate court did with the challenged judgment.

The operative part of an appellate sentence ends with the ruling, in a small
fixed vocabulary::

    oddala apelację                               appeal dismissed
    utrzymuje w mocy zaskarżony wyrok             upheld (criminal cases), same thing
    zmienia zaskarżony wyrok ... i oddala apelację w pozostałej części
                                                  changed in part
    uchyla zaskarżony wyrok i przekazuje sprawę do ponownego rozpoznania
                                                  set aside and remanded
    odrzuca apelację                              rejected on formal grounds
    umarza postępowanie apelacyjne                discontinued (appeal withdrawn)

:func:`classify_ruling` turns the text after the header into flags and one
``outcome``. The binary ``label`` is 1 when the appeal changed anything
(``changed``, ``changed_partly``, ``set_aside``), 0 when it was dismissed, and
null otherwise (rejected, discontinued, unrecognised), so the latter are left
out of the modelling set rather than forced into a class.

Output in ``INTERIM_DIR``::

    labels.parquet      one row per second-instance case in pairs.parquet that
                        has a sentence text: flags, outcome, label, ruling text

and a per-domain summary in ``results/label-census.csv``.

Usage::

    saos-label
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from tqdm import tqdm

from saos_appeals import config
from saos_appeals.data.pairs import _CHALLENGED, _SIG_IN_TEXT

log = logging.getLogger(__name__)


# Verbs in the present tense ("oddala") or the infinitive ("postanowił: oddalić"),
# tolerant of spaced letters and the typos that recur in SAOS ("oddal", "zamienia").
_DISMISS_V = r"o\s?d\s?d\s?a\s?l\s?(?:a|ić)?"
_CHANGE_V = r"z\s?a?\s?m\s?i\s?e\s?n\s?i\s?(?:a|ć)"
_SET_ASIDE_V = r"u\s?c\s?h\s?y\s?l\s?(?:a|ić)"
_UPHOLD_V = r"u\s?t\s?r\s?z\s?y\s?m\s?(?:uje|ać)"
_REJECT_V = r"o\s?d\s?r\s?z\s?u\s?c\s?(?:a|ić)"
_DISCONTINUE_V = r"(?:u\s?m\s?a\s?r\s?z\s?a|umorzyć)"
# "apelację", "apelacje", "apelacj e", "apleację", "apelcję", "a p e l a c j ę"
_APPEAL = r"(?:a\s?p\s?(?:e\s?l|l\s?e\s?l?)\s?a?\s?c\s?j?\s?[ęeią]|apelacyjn\w*|zażaleni[ea])"
_JUDGMENT = r"(?:zaskarżon\w+|wyrok\w*|orzeczeni\w+|postanowieni\w+|punk\w+|pkt\.?)"
_GAP = r"(?:[^.;]{0,60}?)"  # a few words, never across a clause boundary
_SEP = r"[\s:,–-]+"  # between the verb and its object: "uchyla:\n- zaskarżony wyrok"

DISMISS = re.compile(
    rf"\b(?:{_DISMISS_V}{_SEP}{_GAP}{_APPEAL}|{_APPEAL}{_SEP}{_GAP}{_DISMISS_V})\b", re.I
)
DISMISS_PARTLY = re.compile(
    rf"\b{_DISMISS_V}{_SEP}{_GAP}{_APPEAL}\s+{_GAP}w\s+pozostał\w+\s+(?:części|zakresie)", re.I
)
CHANGE = re.compile(
    rf"\b(?:{_CHANGE_V}{_SEP}{_GAP}{_JUDGMENT}|{_JUDGMENT}{_SEP}{_GAP}{_CHANGE_V})\b", re.I
)
SET_ASIDE = re.compile(
    rf"\b(?:{_SET_ASIDE_V}{_SEP}{_GAP}{_JUDGMENT}|{_JUDGMENT}{_SEP}{_GAP}{_SET_ASIDE_V})\b", re.I
)
UPHOLD = re.compile(rf"\b{_UPHOLD_V}{_SEP}{_GAP}w\s+mocy", re.I)
REMAND = re.compile(r"\bdo\s+ponownego\s+rozpozn", re.I)
REJECT = re.compile(rf"\b{_REJECT_V}{_SEP}{_GAP}{_APPEAL}", re.I)
DISCONTINUE = re.compile(
    rf"\b{_DISCONTINUE_V}{_SEP}postępowani\w+\s+(?:apelacyjn\w+|odwoławcz\w+|zażaleniow\w+)", re.I
)

OUTCOMES = ("dismissed", "changed", "changed_partly", "set_aside", "rejected", "discontinued", "unknown")


def ruling_text(operative_text: str) -> str:
    """The part of the operative text after the header: from the challenged
    judgment's signature on. Falls back to the whole text."""
    hit = _CHALLENGED.search(operative_text)
    if not hit:
        return operative_text
    tail = operative_text[hit.end() :]
    sig = _SIG_IN_TEXT.search(tail)
    if not sig:
        return tail
    end = tail.find("\n", sig.end())
    return tail[end + 1 :] if end >= 0 else tail[sig.end() :]


def classify_ruling(text: str) -> dict[str, Any]:
    """Flags and outcome for one ruling text. See the module docstring."""
    flags = {
        "dismiss": bool(DISMISS.search(text) or UPHOLD.search(text)),
        "dismiss_partly": bool(DISMISS_PARTLY.search(text)),
        "change": bool(CHANGE.search(text)),
        "set_aside": bool(SET_ASIDE.search(text)),
        "remand": bool(REMAND.search(text)),
        "reject": bool(REJECT.search(text)),
        "discontinue": bool(DISCONTINUE.search(text)),
    }
    if flags["set_aside"] and not flags["change"]:
        outcome = "set_aside"
    elif flags["change"] or flags["set_aside"]:
        outcome = "changed_partly" if flags["dismiss"] else "changed"
    elif flags["dismiss"]:
        outcome = "dismissed"
    elif flags["reject"]:
        outcome = "rejected"
    elif flags["discontinue"]:
        outcome = "discontinued"
    else:
        outcome = "unknown"
    label = {"dismissed": 0, "changed": 1, "changed_partly": 1, "set_aside": 1}.get(outcome)
    return {**flags, "outcome": outcome, "label": label}


LABEL_SCHEMA = pa.schema(
    [
        ("appeal_case_key", pa.string()),
        ("appeal_sentence_id", pa.int64()),
        ("domain", pa.string()),
        ("appeal_code", pa.string()),
        ("is_labour_division", pa.bool_()),
        ("paired", pa.bool_()),
        ("dismiss", pa.bool_()),
        ("dismiss_partly", pa.bool_()),
        ("change", pa.bool_()),
        ("set_aside", pa.bool_()),
        ("remand", pa.bool_()),
        ("reject", pa.bool_()),
        ("discontinue", pa.bool_()),
        ("outcome", pa.string()),
        ("label", pa.int8()),
        ("ruling_text", pa.string()),
    ]
)


def build_labels(pairs_path: Path, records_path: Path, out_path: Path) -> pd.DataFrame:
    pairs = pq.read_table(
        pairs_path,
        columns=[
            "appeal_case_key",
            "appeal_sentence_id",
            "domain",
            "appeal_code",
            "is_labour_division",
            "first_case_key",
        ],
    ).to_pandas()
    pairs = pairs[pairs["appeal_sentence_id"].notna()]
    meta = {
        int(r["appeal_sentence_id"]): r for r in pairs.to_dict("records")
    }
    pf = pq.ParquetFile(records_path)
    rows: list[dict[str, Any]] = []
    for g in tqdm(range(pf.num_row_groups), desc="labels", unit="rg", dynamic_ncols=True):
        batch = pf.read_row_group(g, columns=["id", "operative_text"])
        for rec_id, text in zip(batch["id"].to_pylist(), batch["operative_text"].to_pylist()):
            r = meta.get(rec_id)
            if r is None or not text:
                continue
            ruling = ruling_text(text)
            rows.append(
                {
                    "appeal_case_key": r["appeal_case_key"],
                    "appeal_sentence_id": rec_id,
                    "domain": r["domain"],
                    "appeal_code": r["appeal_code"],
                    "is_labour_division": bool(r["is_labour_division"]),
                    "paired": pd.notna(r["first_case_key"]),
                    **classify_ruling(ruling),
                    "ruling_text": ruling,
                }
            )
    table = pa.Table.from_pylist(rows, schema=LABEL_SCHEMA)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".parquet.part")
    pq.write_table(table, tmp, compression="zstd")
    tmp.replace(out_path)
    return table.to_pandas()


def census(labels: pd.DataFrame) -> pd.DataFrame:
    """Outcome counts per domain, for all second-instance cases and for paired ones."""
    out = (
        labels.assign(subset=labels["paired"].map({True: "paired", False: "unpaired"}))
        .groupby(["domain", "subset", "outcome"])
        .size()
        .unstack("outcome", fill_value=0)
        .reindex(columns=list(OUTCOMES), fill_value=0)
        .reset_index()
    )
    out["total"] = out[list(OUTCOMES)].sum(axis=1)
    out["labelled"] = out[["dismissed", "changed", "changed_partly", "set_aside"]].sum(axis=1)
    out["granted_share"] = (
        out[["changed", "changed_partly", "set_aside"]].sum(axis=1) / out["labelled"]
    ).round(3)
    return out.sort_values(["subset", "total"], ascending=[True, False])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="saos-label", description="Label appeals from the appellate ruling text."
    )
    parser.add_argument("--pairs", type=Path, default=config.INTERIM_DIR / "pairs.parquet")
    parser.add_argument("--records", type=Path, default=config.INTERIM_DIR / "records.parquet")
    parser.add_argument("--out", type=Path, default=config.INTERIM_DIR / "labels.parquet")
    parser.add_argument("--census", type=Path, default=Path("results/label-census.csv"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    labels = build_labels(args.pairs, args.records, args.out)
    summary = census(labels)
    args.census.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.census, index=False, lineterminator="\n")
    counts = labels["outcome"].value_counts().to_dict()
    log.info("done: %d rulings classified, outcomes %s; census in %s", len(labels), counts, args.census)
    return 0


if __name__ == "__main__":
    sys.exit(main())
