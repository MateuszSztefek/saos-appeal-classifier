# data/

Everything in this directory except this file is ignored by git.
Set `DATA_DIR` to point somewhere else if you keep data outside the repo.

```
data/
  raw/saos/
    judgments/       page-NNNNN.json.gz  -- raw pages of /api/dump/judgments, never edited
    dictionaries/    commonCourts.json, scChambers.json, enrichments.json.gz
  interim/           derived from raw, reproducible with the package's commands
    judgments-<courttype>.jsonl.gz   saos-extract: one record per line, deduplicated by id
    judgments-extract.json           counts and dump provenance for the files above
    records.parquet                  saos-judgments: one row per record with parsed signature,
                                     court, judges, regulation keys and cleaned text (the only file with text)
    cases.parquet                    saos-judgments: one row per court + case signature, metadata only;
                                     SENTENCE and REASONS records of a case merged (sentence_id / reasons_id)
    pairs.parquet                    saos-pair: one row per second-instance case with the matched
                                     first-instance case (if any) and the header fields used to match
  processed/         frozen modelling datasets, shared with the team via Google Drive
```

Rules:

- `raw/` is write-once. Re-download rather than fix in place.
- Anything in `processed/` that the team shares must be reproducible from `raw/`
  with a script in `src/saos_appeals/` and must carry a content hash in its name
  or sidecar file so everyone can verify they have the same version.
