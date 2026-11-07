# saos-appeal-classifier

Predicting whether an appeal against a first-instance judgment of a Polish
common court will be granted, from the first-instance judgment itself, using
public court judgments from [SAOS](https://www.saos.org.pl) (System Analizy
Orzeczeń Sądowych).

## Quickstart

Requires [uv](https://docs.astral.sh/uv/). It installs the right Python version for you.

```bash
git clone https://github.com/MateuszSztefek/saos-appeal-classifier.git
cd saos-appeal-classifier
uv sync                      # creates .venv with runtime + dev dependencies
uv run pre-commit install    # lint and notebook hooks on every commit
```

Run commands inside the environment with `uv run <command>`, or point your IDE at `.venv`.

## Layout

```
src/saos_appeals/      importable package; reusable code goes here, not in notebooks
  config.py            data paths (override with the DATA_DIR environment variable)
  data/                SAOS download, filtering, dataset construction
notebooks/             exploration, numbered 01_, 02_, ...; outputs are stripped on commit
results/               experiment result tables (CSV / JSON) committed to the repo
data/                  raw and derived data, ignored by git (see data/README.md)
docs/                  project documentation
```

## Notebooks

Exploration lives in `notebooks/`, numbered in reading order. The notebooks are
thin: shared code is in `saos_appeals.eda` and `saos_appeals.quality`.

| notebook | what it shows |
|---|---|
| `01_eda_civil.ipynb` | the civil dataset: target, time, courts, bench, texts, legal bases |
| `02_eda_social_insurance.ipynb` | the same for social-insurance cases |
| `03_eda_labour.ipynb` | the same for labour-law cases |
| `04_saos_data_quality.ipynb` | what is wrong or missing in the SAOS dump; writes `results/saos-data-quality.csv` |

Run them with `uv run jupyter lab`. They need the frozen datasets in
`data/processed/` (the quality notebook also needs `data/interim/`).

## Tests

```bash
uv run pytest
```

Tests cover the parsing that the dataset depends on: case signatures,
judgment headers and the regular expressions that label appeal outcomes.

## Workflow

Work happens in short-lived branches merged into `main` through pull requests.
See [CONTRIBUTING.md](CONTRIBUTING.md) for the rules.

## Data

Judgments come from the SAOS REST API (no key required). The full dump is
roughly 545k judgments, about 27 GB of JSON uncompressed. It is downloaded once
per machine and kept outside git. Derived datasets are shared via Google Drive.

```bash
uv run saos-download dictionaries   # courts, divisions, Supreme Court chambers
uv run saos-download judgments      # full dump, resumable, a few hours
uv run saos-download judgments --since 2026-11-01T00:00:00.000   # later updates
```

Pages land in `data/raw/saos/judgments/page-NNNNN.json.gz`; re-running skips
pages already on disk. Set `DATA_DIR` to put them elsewhere.

From the raw pages the pipeline builds, in order:

```bash
uv run saos-extract     # one deduplicated JSON Lines file per court type
uv run saos-judgments   # records.parquet (with text) and cases.parquet (metadata)
uv run saos-pair        # pairs.parquet: appeals matched to first-instance judgments,
                        # plus results/pairing-census.csv
uv run saos-label       # labels.parquet: appeal outcome from the appellate ruling,
                        # plus results/label-census.csv
uv run saos-dataset     # data/processed/appeals-<domain>-<hash>.parquet, one per domain
```

The frozen datasets in `data/processed/` are what the models train on. They are
shared through Google Drive rather than rebuilt by everyone; `datasets.json`
next to them lists each file's SHA-256, row counts and split boundaries, so a
downloaded copy can be verified with `sha256sum`.

See [data/README.md](data/README.md) for what each file holds.
