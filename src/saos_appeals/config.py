"""Project-wide paths.

Set the ``DATA_DIR`` environment variable to keep data outside the repository
(for example on a larger drive). Defaults to the ``data/`` directory of the
repository, whatever the current working directory is, so notebooks in
``notebooks/`` and commands run from the root see the same files.
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = Path(os.environ.get("DATA_DIR", REPO_ROOT / "data")).resolve()

RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
RESULTS_DIR = REPO_ROOT / "results"

SAOS_RAW_DIR = RAW_DIR / "saos"
SAOS_JUDGMENTS_DIR = SAOS_RAW_DIR / "judgments"
SAOS_DICTIONARIES_DIR = SAOS_RAW_DIR / "dictionaries"
