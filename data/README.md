# data/

Everything in this directory except this file is ignored by git.
Set `DATA_DIR` to point somewhere else if you keep data outside the repo.

```
data/
  raw/saos/
    judgments/       page-NNNNN.json.gz  -- raw pages of /api/dump/judgments, never edited
    dictionaries/    commonCourts.json, scChambers.json, enrichments.json.gz
  interim/           filtered / deduplicated subsets derived from raw
  processed/         frozen modelling datasets, shared with the team via Google Drive
```

Rules:

- `raw/` is write-once. Re-download rather than fix in place.
- Anything in `processed/` that the team shares must be reproducible from `raw/`
  with a script in `src/saos_appeals/` and must carry a content hash in its name
  or sidecar file so everyone can verify they have the same version.
