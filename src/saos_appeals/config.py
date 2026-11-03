"""Project-wide paths.

Set the ``DATA_DIR`` environment variable to keep data outside the repository
(for example on a larger drive). Defaults to ``./data`` relative to the current
working directory.
"""

import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "data")).resolve()

RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"

SAOS_RAW_DIR = RAW_DIR / "saos"
SAOS_JUDGMENTS_DIR = SAOS_RAW_DIR / "judgments"
SAOS_DICTIONARIES_DIR = SAOS_RAW_DIR / "dictionaries"
