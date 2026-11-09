# SAOS data cleaning

The raw SAOS dump is immutable. Corrections are applied only while building derived
records, by `clean_judgment_date` in
[`src/saos_appeals/data/cleaning.py`](../src/saos_appeals/data/cleaning.py).
The `saos-judgments` preprocessing command calls this function for each source record.
Its record-ID-specific rules verify the expected source value and raise an error if
SAOS changes it, so corrections cannot silently apply to different data.

## Verified judgment-date corrections

| SAOS record | Source date | Derived date | Evidence |
|---|---|---|---|
| 358516 (`II K 336/17`, REASONS) | `0208-03-14` | `2018-03-14` | Same-court, same-signature SENTENCE record 358515 has judgment date `2018-03-14`. |
| 227221 (`II K 84/16`, SENTENCE) | `2101-04-14` | `2016-04-14` | The text header says `Dnia 14 kwietnia 21016 r.` and gives hearing dates `10.03.2016` and `14.04.2016`; the SAOS source identifier also refers to the 2016 upload. |
| 31345 (`I ACa 772/13`, SENTENCE) | `3013-12-04` | `2013-12-04` | The judgment text says it was heard on `4 grudnia 2013r.`, and the SAOS source identifier includes `2013-12-04`. |

These are explicit, record-specific repairs, not general rules for guessing malformed
years. To rebuild the derived records after changing a rule, rerun `saos-judgments`
from the extracted SAOS input. The quality report retains the three original anomalies
for auditing and marks them as corrected in preprocessing.

## Signature-domain classification

The signature parser maps the `Pen` prefix to the criminal domain before applying the
broader `P` → labour rule. This is verified by SAOS record
[418443](https://www.saos.org.pl/api/judgments/418443), `II Pen 257/19`, whose division
is `II Wydział Karny` (criminal division). Without the specific prefix, `Pen` was
incorrectly classified as labour because it begins with `P`.
