"""Turn raw SAOS dump pages into one deduplicated JSON Lines file per court type.

The dump is paged by position, not by a stable cursor, so a judgment can show
up on two pages when records were added while the download was running. This
step keeps the first occurrence of every ``id`` and writes records unchanged,
one per line, to ``INTERIM_DIR/judgments-<courttype>.jsonl.gz``::

    judgments-common.jsonl.gz                  common courts, the project's input
    judgments-supreme.jsonl.gz                 Supreme Court
    judgments-constitutional_tribunal.jsonl.gz
    judgments-national_appeal_chamber.jsonl.gz
    judgments-extract.json                     counts and provenance

Usage::

    saos-extract
    saos-extract --court-type COMMON
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any

from tqdm import tqdm

from saos_appeals import config

log = logging.getLogger(__name__)

COURT_TYPES = ("COMMON", "SUPREME", "CONSTITUTIONAL_TRIBUNAL", "NATIONAL_APPEAL_CHAMBER")


def output_path(out_dir: Path, court_type: str) -> Path:
    return out_dir / f"judgments-{court_type.lower()}.jsonl.gz"


def iter_pages(pages_dir: Path) -> list[Path]:
    pages = sorted(pages_dir.glob("page-*.json.gz"))
    if not pages:
        raise SystemExit(f"no dump pages found in {pages_dir}; run saos-download first")
    return pages


def extract(
    pages_dir: Path,
    out_dir: Path,
    court_types: tuple[str, ...] = COURT_TYPES,
) -> dict[str, Any]:
    """Stream every page once and split records by court type. Returns a summary."""
    pages = iter_pages(pages_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp_paths = {ct: output_path(out_dir, ct).with_suffix(".gz.part") for ct in court_types}
    writers: dict[str, IO[str]] = {
        ct: gzip.open(path, "wt", encoding="utf-8", compresslevel=6)
        for ct, path in tmp_paths.items()
    }
    seen: set[int] = set()
    kept: Counter[str] = Counter()
    skipped: Counter[str] = Counter()
    duplicates = 0
    try:
        for page_file in tqdm(pages, unit="page", desc="extract", dynamic_ncols=True):
            with gzip.open(page_file, "rt", encoding="utf-8") as fh:
                items = json.load(fh)["items"]
            for record in items:
                record_id = record["id"]
                if record_id in seen:
                    duplicates += 1
                    continue
                seen.add(record_id)
                court_type = record["courtType"]
                writer = writers.get(court_type)
                if writer is None:
                    skipped[court_type] += 1
                    continue
                writer.write(json.dumps(record, ensure_ascii=False))
                writer.write("\n")
                kept[court_type] += 1
    finally:
        for writer in writers.values():
            writer.close()
    for ct, tmp in tmp_paths.items():
        tmp.replace(output_path(out_dir, ct))

    dump_meta_path = pages_dir / "_meta.json"
    dump_meta = (
        json.loads(dump_meta_path.read_text(encoding="utf-8")) if dump_meta_path.exists() else {}
    )
    summary = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "pages": len(pages),
        "records_seen": len(seen) + duplicates,
        "duplicates_dropped": duplicates,
        "kept": dict(kept),
        "skipped_court_types": dict(skipped),
        "dump": {k: dump_meta.get(k) for k in ("started_at", "finished_at", "pages_on_disk")},
        "files": {ct: output_path(out_dir, ct).name for ct in court_types},
    }
    (out_dir / "judgments-extract.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="saos-extract",
        description="Split raw SAOS dump pages into one JSON Lines file per court type.",
    )
    parser.add_argument(
        "--pages",
        type=Path,
        default=config.SAOS_JUDGMENTS_DIR,
        help="directory with page-NNNNN.json.gz (default: $DATA_DIR/raw/saos/judgments)",
    )
    parser.add_argument(
        "--out", type=Path, default=config.INTERIM_DIR, help="default: $DATA_DIR/interim"
    )
    parser.add_argument(
        "--court-type",
        action="append",
        choices=COURT_TYPES,
        help="only these court types (repeatable); default: all four",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    court_types = tuple(args.court_type) if args.court_type else COURT_TYPES
    summary = extract(args.pages, args.out, court_types)
    log.info(
        "done: %d records, %d duplicates dropped, kept %s",
        summary["records_seen"],
        summary["duplicates_dropped"],
        summary["kept"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
