# Contributing

## Branches and pull requests

- `main` is protected. Nothing lands on it except through a pull request.
- Branch from `main` and name the branch after what it does: `download-client`,
  `fix-date-parsing`, `eda-label-distribution`. No prefix required.
- A pull request needs one approval from another team member and a green lint
  run. The author merges it and deletes the branch.
- Update your branch from `main` before asking for review if it has drifted.

## Commits

- Imperative mood, English, first line under 72 characters:
  `Add SAOS dump client`, `Handle OCR-corrupted judgment dates`.
- Add a body only when the *why* is not obvious from the diff.
- No prefixes like `feat:` or `chore:`.

## Code

- Reusable code lives in `src/saos_appeals/`. Notebooks import from it; they do
  not define functions that another notebook will need.
- `ruff` is the linter and formatter; `pre-commit` runs it for you. If a hook
  rewrites a file, stage it again and commit.
- Keep dependencies minimal. A runtime dependency is added only when a script
  needs it; anything used just for development goes to the `dev` group in
  `pyproject.toml`. Run `uv lock` after changing dependencies and commit `uv.lock`.
- Type hints and a one-line docstring on public functions.

## Data and results

- Never commit anything from `data/`. The pre-commit hook rejects files over 1 MB
  as a safety net, but small data files are not welcome either.
- Experiment results go to `results/` as CSV or JSON together with the hash of
  the dataset they were computed on, so a table in a pull request can be reproduced.

## Notebooks

- Name them `NN_short_topic.ipynb`, for example `01_eda_raw_dump.ipynb`. Numbers give reading order.
- Outputs are stripped automatically on commit by `nbstripout`. If a plot is
  worth keeping, save it to `results/` or paste it into the pull request.
