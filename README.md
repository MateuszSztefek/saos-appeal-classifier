# saos-appeal-classifier

Predicting whether an appeal against a first-instance judgment in a Polish
labour-law or social-insurance case will be granted, using public court
judgments from [SAOS](https://www.saos.org.pl) (System Analizy Orzeczeń Sądowych).

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
