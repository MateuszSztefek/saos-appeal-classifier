"""Download the SAOS judgment dump and its dictionaries.

SAOS exposes the whole database through a paged REST endpoint
(``/api/dump/judgments``, at most 100 records per page, no court or division
filter). This module walks the pages and stores each one as it came from the
server, gzipped, so that filtering and cleaning can be re-run offline.

Layout under ``SAOS_RAW_DIR`` (see :mod:`saos_appeals.config`)::

    judgments/
        page-00000.json.gz ...      full dump, one file per page
        _meta.json                  when and with which parameters it was taken
        since-<stamp>/              incremental updates (``--since``)
    dictionaries/
        commonCourts.json, scChambers.json
        enrichments/page-00000.json.gz ...   optional, see ``--enrichments``

A page file is written atomically (temporary file, then rename), so an existing
file is a complete page and the download can be resumed by re-running it.

Usage::

    saos-download judgments
    saos-download judgments --since 2026-11-01T00:00:00.000
    saos-download dictionaries [--enrichments]
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import sys
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from tqdm import tqdm

from saos_appeals import config

log = logging.getLogger(__name__)

BASE_URL = "https://www.saos.org.pl/api"
PAGE_SIZE = 100  # server-side maximum
USER_AGENT = "saos-appeal-classifier/0.1 (+https://github.com/MateuszSztefek/saos-appeal-classifier)"

Page = dict[str, Any]


class SaosClient:
    """Thin HTTP client for the SAOS API with retries and a polite request rate."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: float = 120.0,
        max_retries: int = 6,
        min_interval: float = 0.0,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            # SAOS answers 406 without an explicit JSON Accept header.
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )
        self.max_retries = max_retries
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last_request = 0.0

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> SaosClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET ``path`` and decode JSON, retrying transient failures with backoff."""
        delay = 2.0
        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            try:
                response = self._client.get(path, params=params)
                if response.status_code >= 500 or response.status_code == 429:
                    raise httpx.HTTPStatusError(
                        f"server returned {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                return response.json()
            except (httpx.TransportError, httpx.HTTPStatusError, json.JSONDecodeError) as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status is not None and 400 <= status < 500 and status != 429:
                    raise  # client error, retrying will not help
                if attempt == self.max_retries:
                    raise
                log.warning(
                    "%s %s failed (%s), retry %d/%d in %.0fs",
                    path,
                    params or "",
                    exc,
                    attempt,
                    self.max_retries,
                    delay,
                )
                time.sleep(delay)
                delay = min(delay * 2, 60.0)
        raise AssertionError("unreachable")

    def _throttle(self) -> None:
        if self.min_interval <= 0:
            return
        with self._lock:
            wait = self._last_request + self.min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()


def has_next_page(page: Page) -> bool:
    """A dump page past the end has no items and no ``next`` link."""
    return bool(page.get("items")) and any(
        link.get("rel") == "next" for link in page.get("links", [])
    )


def write_json_gz(path: Path, payload: Any) -> None:
    """Write ``payload`` as gzipped JSON atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    tmp.replace(path)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


def page_path(directory: Path, page_number: int) -> Path:
    return directory / f"page-{page_number:05d}.json.gz"


def download_paged(
    client: SaosClient,
    endpoint: str,
    out_dir: Path,
    params: dict[str, Any] | None = None,
    start_page: int = 0,
    end_page: int | None = None,
    concurrency: int = 3,
    expected_pages: int | None = None,
) -> int:
    """Download all pages of a dump endpoint into ``out_dir``.

    Pages that already exist on disk are skipped. Stops at ``end_page``
    (inclusive) or at the first page the server reports as the last one.
    Returns the number of pages fetched in this run.
    """
    params = {"pageSize": PAGE_SIZE, **(params or {})}
    out_dir.mkdir(parents=True, exist_ok=True)
    stop_at: list[int | None] = [end_page]  # mutable box shared with workers
    stop_lock = threading.Lock()
    fetched = 0

    def should_fetch(n: int) -> bool:
        limit = stop_at[0]
        return limit is None or n <= limit

    def fetch(n: int) -> tuple[int, bool]:
        target = page_path(out_dir, n)
        if target.exists():
            return n, False
        if not should_fetch(n):
            return n, False
        page = client.get_json(endpoint, {**params, "pageNumber": n})
        if not page.get("items"):
            with stop_lock:
                if stop_at[0] is None or n - 1 < stop_at[0]:
                    stop_at[0] = n - 1
            return n, False
        write_json_gz(target, page)
        if not has_next_page(page):
            with stop_lock:
                if stop_at[0] is None or n < stop_at[0]:
                    stop_at[0] = n
        return n, True

    def page_numbers() -> Iterator[int]:
        n = start_page
        while should_fetch(n):
            yield n
            n += 1

    progress = tqdm(
        total=expected_pages,
        initial=start_page,
        unit="page",
        desc=endpoint.rsplit("/", 1)[-1],
        dynamic_ncols=True,
    )
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        # Keep a bounded window of in-flight pages so that reaching the last
        # page does not leave hundreds of useless requests queued.
        window = concurrency * 2
        pending = []
        numbers = page_numbers()
        try:
            for n in numbers:
                pending.append(pool.submit(fetch, n))
                if len(pending) >= window:
                    _, was_fetched = pending.pop(0).result()
                    fetched += int(was_fetched)
                    progress.update(1)
            for future in pending:
                _, was_fetched = future.result()
                fetched += int(was_fetched)
                progress.update(1)
        finally:
            progress.close()
    return fetched


def estimate_judgment_pages(client: SaosClient) -> int | None:
    """Total page count from the search API, only used for the progress bar."""
    try:
        info = client.get_json("/search/judgments", {"pageSize": 10})["info"]
        return -(-int(info["totalResults"]) // PAGE_SIZE)
    except Exception as exc:  # noqa: BLE001 - cosmetic only
        log.debug("could not estimate page count: %s", exc)
        return None


def download_judgments(
    client: SaosClient,
    out_dir: Path,
    since: str | None,
    start_page: int,
    end_page: int | None,
    concurrency: int,
) -> None:
    params: dict[str, Any] = {"withGenerated": "true"}
    expected = None
    if since:
        params["sinceModificationDate"] = since
        stamp = since.replace(":", "").replace(".", "")
        out_dir = out_dir / f"since-{stamp}"
    else:
        expected = estimate_judgment_pages(client)
    meta_path = out_dir / "_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    meta.setdefault("started_at", datetime.now(UTC).isoformat(timespec="seconds"))
    meta.update({"endpoint": "/dump/judgments", "params": params, "page_size": PAGE_SIZE})
    write_json(meta_path, meta)

    log.info("downloading judgments into %s (expected ~%s pages)", out_dir, expected or "?")
    fetched = download_paged(
        client,
        "/dump/judgments",
        out_dir,
        params,
        start_page=start_page,
        end_page=end_page,
        concurrency=concurrency,
        expected_pages=expected,
    )
    pages = sorted(out_dir.glob("page-*.json.gz"))
    meta.update(
        {
            "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "pages_on_disk": len(pages),
            "last_page": int(pages[-1].stem.split("-")[1].split(".")[0]) if pages else None,
        }
    )
    write_json(meta_path, meta)
    log.info("done: %d pages fetched now, %d pages on disk", fetched, len(pages))


def download_dictionaries(client: SaosClient, out_dir: Path, enrichments: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in ("commonCourts", "scChambers"):
        items: list[Any] = []
        n = 0
        while True:
            page = client.get_json(f"/dump/{name}", {"pageSize": PAGE_SIZE, "pageNumber": n})
            items.extend(page.get("items", []))
            if not has_next_page(page):
                break
            n += 1
        write_json(out_dir / f"{name}.json", items)
        log.info("%s: %d records", name, len(items))
    if enrichments:
        # Redundant with withGenerated=true on judgments, but useful for cross-checks.
        # Roughly 11k pages, so opt-in.
        download_paged(client, "/dump/enrichments", out_dir / "enrichments", concurrency=2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="saos-download", description="Download the SAOS judgment dump."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=config.SAOS_RAW_DIR,
        help="root directory for raw SAOS data (default: $DATA_DIR/raw/saos)",
    )
    parser.add_argument(
        "--concurrency", type=int, default=3, help="parallel requests, keep it small (default 3)"
    )
    parser.add_argument(
        "--min-interval",
        type=float,
        default=0.2,
        help="minimum seconds between requests across all workers (default 0.2)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    judgments = sub.add_parser("judgments", help="download /dump/judgments")
    judgments.add_argument(
        "--since",
        metavar="DATETIME",
        help="only records modified after this moment, format yyyy-MM-ddTHH:mm:ss.SSS; "
        "written to a separate since-<stamp>/ directory",
    )
    judgments.add_argument("--start-page", type=int, default=0)
    judgments.add_argument("--end-page", type=int, default=None, help="inclusive, for testing")

    dictionaries = sub.add_parser("dictionaries", help="download courts and chambers")
    dictionaries.add_argument(
        "--enrichments", action="store_true", help="also download /dump/enrichments (large)"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per request otherwise
    with SaosClient(min_interval=args.min_interval) as client:
        if args.command == "judgments":
            download_judgments(
                client,
                args.out / "judgments",
                since=args.since,
                start_page=args.start_page,
                end_page=args.end_page,
                concurrency=args.concurrency,
            )
        elif args.command == "dictionaries":
            download_dictionaries(client, args.out / "dictionaries", enrichments=args.enrichments)
    return 0


if __name__ == "__main__":
    sys.exit(main())
