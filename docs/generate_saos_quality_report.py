from __future__ import annotations

# The report template contains intentionally long HTML and CSS lines.
# ruff: noqa: E501
import csv
import html
from pathlib import Path

ROOT = Path(__file__).parent.parent
HTML_PATH = ROOT / "docs" / "saos-data-quality-report.html"
CSV_PATH = ROOT / "results" / "saos-data-quality.csv"

_ISSUE_DESCRIPTIONS = {
    "SENTENCE record with empty textContent": (
        "The source record identifies a judgment but contains no operative text. "
        "Metadata cannot safely replace the missing judgment wording."
    ),
    "REASONS record with empty textContent": (
        "The source marks reasons as present or registered, but this record "
        "contains no written reasoning. Another record for the same case may "
        "still provide usable reasons."
    ),
    "judgment date outside 1990–2026 or unparseable": (
        "The source date is missing, malformed, or outside the analysis range. "
        "Such a value can corrupt chronological checks and temporal splits."
    ),
    "published before the judgment date": (
        "The publication metadata precedes the judgment date. This is a metadata "
        "anomaly and does not by itself invalidate the judgment text."
    ),
    "reasons record dated before its sentence": (
        "The separate REASONS record has an earlier source date than the "
        "SENTENCE record for the same case. The dates may describe publication "
        "or preparation events rather than the ruling date."
    ),
    "reasons record dated > 1 year after its sentence": (
        "The separate REASONS record is dated substantially later than the "
        "SENTENCE record. This may reflect when reasons were written or "
        "published, not a different case."
    ),
    "case signature not in the standard form": (
        "The case-number parser cannot extract the division, code, sequence, "
        "and year. Without these fields, domain classification, case keys, and "
        "pairing may fail."
    ),
    "  of which a digit after the division numeral (I 2C 15/13)": (
        "These signatures contain a court-specific numbered sub-division, such "
        "as IV 1 P 51/11. The notation may be valid even though the current "
        "parser does not recognise it."
    ),
    "case with more than one SENTENCE record": (
        "One case key has multiple SENTENCE records. They may represent a "
        "retrial, partial judgment, duplicate upload, or different publication "
        "versions, so selecting one record can change the model input."
    ),
    "case key shared by 3+ records": (
        "At least three source records share one case key. Combining them "
        "without checking record types and text can mix incompatible documents "
        "or create duplicate information."
    ),
    "labour / social-insurance signature outside a labour division": (
        "The parsed legal domain suggests labour or social insurance, while the "
        "court division is not a labour division. This indicates a parser or "
        "source-classification mismatch."
    ),
    "other signature inside a labour division": (
        "A code classified outside the labour domains occurs in a labour "
        "division. It may affect domain assignment and cross-domain comparisons."
    ),
    "record without any judge": (
        "The record has no judge entries. The judgment text can still be usable, "
        "but judge-based metadata features are unavailable."
    ),
    "record without a presiding judge in the modelling set": (
        "The role marker is missing in 398 rows, but the cases differ: 340 have "
        "no judge, 54 have exactly one judge whose role is unambiguous, and only "
        "4 have multiple judges without a role marker."
    ),
    "judge name anonymised to initials": (
        "The judge identity is represented only by initials or an anonymisation "
        "marker. This prevents reliable judge identity features."
    ),
    "two judges in one name field": (
        "A source name field appears to contain two judges or additional text. "
        "Using it as one identity can corrupt judge counts and identity features."
    ),
    "record without keywords": (
        "The source record has no keyword metadata. This does not remove the "
        "operative or reasons text."
    ),
    "record without legal bases": (
        "The source record has no extracted legal-basis metadata. Legal features "
        "are missing even when the judgment text is available."
    ),
    "record without summary": (
        "The source record has no summary. The current model does not require "
        "this optional metadata field."
    ),
    "appeal sentence without text": (
        "The appellate SENTENCE record has no usable text, so its outcome cannot "
        "be extracted reliably for the target label."
    ),
    "appeal text without a recognisable header": (
        "The appellate text does not expose a reliable challenged-judgment "
        "header. Automatic first-instance pairing is therefore uncertain."
    ),
    "header without a first-instance signature": (
        "The appeal header lacks the signature needed to locate the reviewed "
        "first-instance judgment."
    ),
    "first-instance judgment not published in SAOS": (
        "The appeal names a first-instance signature, but no matching child-court "
        "judgment exists in the available SAOS dump."
    ),
    "matched by signature but header date disagrees": (
        "A candidate was found by signature and hierarchy, but its date differs "
        "from the date stated in the appeal header. Accepting it could pair the "
        "wrong text with the outcome."
    ),
    "appellate text is a hearing transcript, not a judgment": (
        "The appellate text contains transcript or timestamp patterns rather "
        "than a clean judgment. Outcome extraction may therefore be unreliable."
    ),
    "ruling unrecognised although the text speaks of dismissing the appeal": (
        "The outcome parser returns unknown even though the text contains "
        "language indicating dismissal. This creates label loss or bias."
    ),
    "ruling extraction empty after the header": (
        "The extracted text contains no characters after the recognised "
        "challenged-judgment header and signature. This is a screening signal, "
        "not proof that the raw SAOS document was physically truncated. The "
        "extraction rule must be fixed or validated against raw text."
    ),
    "first-instance reasons with heavy anonymisation (> 5 '(...)' per 1k chars)": (
        "The reasons contain many anonymisation placeholders. Legal context and "
        "linguistic signals may be missing, reducing model quality."
    ),
    "first-instance text shorter than 2,000 chars": (
        "The first-instance reasons are unusually short. This may be a valid "
        "brief decision or incomplete publication, so length alone is not proof "
        "of corruption."
    ),
}

_RARE_CASE_EVIDENCE = {
    "judgment date outside 1990–2026 or unparseable": (
        "Independent SAOS API checks: record 358516 has "
        "judgmentDate=0208-03-14 and text fragment “Sygn. akt II K 336/17 ... "
        "UZASADNIENIE”; record 227221 has judgmentDate=2101-04-14 and text "
        "“Dnia 14 kwietnia 21016 r.”; record 31345 has judgmentDate=3013-12-04 "
        "and text “Dnia 4 grudnia 3013 roku”."
    ),
    "published before the judgment date": (
        "Independent SAOS API checks: record 199625 has judgmentDate=2016-02-13 "
        "and publicationDate=2016-02-10; record 175911 has "
        "judgmentDate=2016-05-26 and publicationDate=2015-09-09. Record 199625 "
        "contains “Dnia 13 stycznia 2016 roku”, while record 175911 contains "
        "“Dnia 26 maja 2016 roku”."
    ),
    "labour / social-insurance signature outside a labour division": (
        "Independent SAOS API check: record 418443 has case number "
        "“II Pen 257/19”, division “II Wydział Karny”, division type “Karny”, "
        "and court type REGIONAL. The code is therefore criminal, not labour "
        "or social-insurance, despite the mismatch check."
    ),
    "two judges in one name field": (
        "The stored evidence contains the raw field “jacek sikorski i bogdan "
        "gierzyński”, which joins two names with “i”. A second example contains "
        "“wanda czajkowska marcin piotrowski po rozpoznaniu...”, showing that "
        "the field can also absorb surrounding judgment text."
    ),
    "ruling unrecognised although the text speaks of dismissing the appeal": (
        "The stored ruling excerpt is: “Uzasadnienie wyroku z dnia 18 kwietnia "
        "2014 r. ... Apelacja podlega oddaleniu.” The text explicitly contains "
        "the Polish dismissal phrase, while the extracted outcome is unknown."
    ),
    "ruling extraction empty after the header": (
        "This is a derived screening signal, not a confirmed truncation flag. "
        "Manual checks of comparable SAOS API records 43, 91, 31, and 72 found "
        "complete operative rulings after the appeal header. The local dataset "
        "does not contain raw text for the 1,239 flagged records, so the source "
        "problem cannot currently be confirmed."
    ),
    "reasons record dated before its sentence": (
        "The CSV identifies separate-record case keys such as "
        "276|XVII AmC 334/09 and 276|XVII AmC 935/09. Raw interim records were "
        "not available locally, so the exact two source dates cannot be quoted "
        "in this report."
    ),
    "reasons record dated > 1 year after its sentence": (
        "The CSV identifies separate-record case keys such as 39|II K 11/03 "
        "and 159|III Ca 1544/16. Raw interim records were not available locally, "
        "so the exact two source dates cannot be quoted in this report."
    ),
    "first-instance text shorter than 2,000 chars": (
        "All four final modelling texts were individually audited. They have "
        "coherent starts and endings: 155|V U 1462/12 -> 154|III AUa 1647/12 "
        "ends with the dismissal formula; 79|I C 623/13 -> 75|IV Ca 419/16 "
        "is a complete order supplementing a judgment; 24|III K 602/17 -> "
        "20|IV Ka 773/17 is a complete short criminal justification; and "
        "80|II K 120/14 -> 59|II AKa 142/19 is a complete correction order. "
        "No text is visibly truncated."
    ),
}


def issue_register() -> str:
    rows = []
    with CSV_PATH.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    sections = [
        "<h2>Issue-by-issue descriptions and treatments</h2>",
        "<p>This register gives an individual description and treatment for every "
        "check in the CSV. Phrases marked <b>Implementation change required</b> "
        "identify behaviour that is documented but not yet fully implemented.</p>",
    ]
    number = 0
    for row in rows:
        if int(row["count"]) == 0:
            continue
        number += 1
        issue = html.escape(row["issue"])
        description = html.escape(
            _ISSUE_DESCRIPTIONS.get(
                row["issue"], "The quality check identifies this data condition."
            )
        )
        note = html.escape(row["note"] or "No additional note was recorded.")
        example = html.escape(row["example"] or "No example was recorded.")
        treatment = html.escape(row["treatment"])
        importance = html.escape(row.get("model_importance") or "Not assessed")
        evidence = _RARE_CASE_EVIDENCE.get(row["issue"])
        evidence_html = (
            f"<p><b>Individual case audit:</b> {html.escape(evidence)}</p>"
            if evidence and int(row["count"]) <= 200
            else ""
        )
        sections.append(
            f"<h3>{number}. {issue}</h3>"
            f"<p><b>What it means:</b> {description}</p>"
            f"<p><b>How it was identified:</b> This check identifies <code>{issue}</code>. "
            f"The reported count is <b>{html.escape(row['count'])}</b> of "
            f"<b>{html.escape(row['out_of'])}</b> records or cases, depending "
            f"on the denominator. {note}</p>"
            f"<p><b>Example:</b> <code>{example}</code></p>"
            f"{evidence_html}"
            f"<p><b>Model importance:</b> {importance}.</p>"
            f'<div class="warning"><b>Treatment:</b> {treatment}</div>'
        )
    return "\n".join(sections)


def main() -> None:
    HTML_PATH.write_text(
        """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>SAOS Data Quality Report</title>
<style>
@page { size: A4; margin: 1.5cm; }
body { font-family: Arial, sans-serif; color: #202124; line-height: 1.35; font-size: 10pt; }
h1 { color: #17365d; font-size: 24pt; margin-bottom: 4px; }
h2 { color: #1f4e79; border-bottom: 1px solid #9fbad0; padding-bottom: 4px; margin-top: 24px; }
h3 { color: #2f5597; margin-top: 18px; }
.subtitle { color: #666; margin-top: 0; }
.box { background: #eef5fb; border-left: 5px solid #2f75b5; padding: 10px 14px; margin: 12px 0; }
.warning { background: #fff2cc; border-left: 5px solid #bf9000; padding: 10px 14px; margin: 12px 0; }
.critical { background: #fce4d6; border-left: 5px solid #c00000; padding: 10px 14px; margin: 12px 0; }
code { font-family: Consolas, monospace; background: #f1f1f1; padding: 1px 3px; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 16px; }
th { background: #1f4e79; color: white; text-align: left; }
th, td { border: 1px solid #b7c9d6; padding: 4px 5px; vertical-align: top; }
tr:nth-child(even) { background: #f7fbfe; }
.summary td:first-child { font-weight: bold; width: 28%; }
.all-checks { font-size: 6.8pt; }
.all-checks th, .all-checks td { padding: 3px; }
.all-checks td:nth-child(1) { width: 24%; }
.all-checks td:nth-child(6) { width: 18%; }
.all-checks td:nth-child(8) { width: 18%; word-break: break-word; }
.small { font-size: 8pt; color: #555; }
.page-break { page-break-before: always; }
ul { margin-top: 5px; }
</style>
</head>
<body>
<h1>SAOS Data Quality</h1>
<p class="subtitle">Problems identified in <code>results/saos-data-quality.csv</code> and their treatment</p>
<p><b>Dataset context.</b> The report covers the SAOS common-court dump and the
derived modelling datasets. The CSV contains 32 checks. Counts refer to the
denominator shown in the table; they are not all counts of modelling rows.</p>

<div class="box">
<b>Executive summary.</b> The main modelling limitation is not isolated text noise,
but selective coverage and uncertain pairing. Most appeals do not have a
recoverable first-instance judgment in SAOS. Rows with an empty required text,
an unconfirmed pair, or an unrecognised outcome are excluded from the final
modelling dataset. Source records remain available in intermediate tables for
audit and diagnostics.
</div>

<h2>Model relevance</h2>
<table class="summary">
<tr><td>Critical</td><td>Potentially assigns the wrong first-instance text to the appeal outcome. Such pairs are excluded from modelling.</td></tr>
<tr><td>High</td><td>Can lose rows, create wrong pairs or labels, or bias the selected modelling sample.</td></tr>
<tr><td>Medium</td><td>Can weaken metadata or text features and affect selected subsets, but does not necessarily invalidate the row.</td></tr>
<tr><td>Low</td><td>Mainly affects auditability, temporal interpretation, or optional metadata not used by the current text input.</td></tr>
</table>

<h2>Detailed issue 1: SENTENCE record with empty textContent</h2>
<p>A SAOS record of type <code>SENTENCE</code> may contain metadata such as an
identifier, court, case signature and date, while its <code>textContent</code>
is empty. The report finds <b>21,256 of 357,527</b> sentence records (5.95%).
The example record is <code>491584</code>.</p>

<h3>Why this is not automatically a parser error</h3>
<p>The public SAOS API can return the record with an empty text field and no
usable alternative in fields such as <code>decision</code> or
<code>judgmentResult</code>. The missing text therefore cannot safely be
reconstructed by our parser.</p>
<div class="box"><b>Concrete example — SAOS record 491584.</b> The API returns
<code>judgmentType = SENTENCE</code>, <code>caseNumber = II K 11/03</code>,
<code>judgmentDate = 2003-05-06</code>, and two judges, but
<code>textContent = ""</code>. It also returns
<code>decision = null</code> and <code>judgmentResult = null</code>. The record
therefore proves that the judgment metadata exists, but provides no sentence
text that the model can read.</div>

<h3>Separate SENTENCE and REASONS records</h3>
<p>SAOS can store separate records for the same court and signature:</p>
<ul>
<li><code>SENTENCE</code> contains the operative part;</li>
<li><code>REASONS</code> contains the written reasons.</li>
</ul>
<p>The pipeline groups them by <code>case_key</code>. It can use reasons from a
separate <code>REASONS</code> record, or from a <code>SENTENCE</code> record
that also contains reasons. However, available reasons do not recreate a
missing operative part.</p>

<h3>Pipeline treatment and model impact</h3>
<p>The case-building step keeps the sentence and reasons identifiers
separately. The final dataset requires both
<code>first_operative_len &gt; 0</code> and
<code>first_reasons_len &gt; 0</code>. Therefore a case with an empty first-instance
sentence is retained in intermediate data but excluded from the final model
dataset.</p>
<div class="warning"><b>Decision:</b> excluded from modelling data. Do not invent or infer a missing sentence
from metadata or reasons. Keep the record for audit, but do not use it as a
complete text input.</div>
<p>The broader risk is selection bias: missing text may vary by court, period,
or publication practice. The final model is therefore trained on the subset
with usable published text, not on all SAOS cases.</p>

<h2>Detailed issue 2: REASONS record with empty textContent</h2>
<p>A SAOS record of type <code>REASONS</code> may exist because reasons were
announced or registered, while its <code>textContent</code> is empty. The
report finds <b>4,823 of 53,072</b> reasons records (9.09%). This is different
from an empty sentence: the operative part may still be available, but the
written reasoning needed by the model is missing.</p>
<div class="warning"><b>Important denominator clarification.</b> The value
<b>4,823</b> is a count of raw SAOS <code>REASONS</code> records with empty
<code>textContent</code>. It is measured before combining separate
<code>SENTENCE</code> and <code>REASONS</code> records belonging to the same
<code>case_key</code>. It is therefore <b>not</b> a count of 4,823 final
modelling cases excluded after the pipeline has checked whether another record
provides usable reasons.</div>

<h3>How the records can complement each other</h3>
<p>The pipeline groups records with the same court and case signature. It first
looks for a non-empty separate <code>REASONS</code> record. If that is not
available, it can use reasons embedded in a non-empty <code>SENTENCE</code>
record. An empty <code>REASONS</code> record therefore does not automatically
mean that the whole case has no reasons, but it does mean that this particular
record contributes no reasoning text.</p>
<div class="box"><b>Concrete example — SAOS records 418676, 391901 and
424568.</b> The API returns respectively <code>judgmentType = REASONS</code>
for case signatures <code>XVII AmC 334/09</code>, <code>II Ka 124/12</code>
and <code>VII K 266/12</code>, but each has
<code>textContent = ""</code>. Their metadata and dates are present, yet
there is no written reasoning in those records for the model to read.</div>

<h3>Pipeline treatment and model impact</h3>
<p>When the same case has a non-empty sentence containing reasons, or another
non-empty reasons record, the available text can still be used. When no
reasons text is available, the final dataset condition
<code>first_reasons_len &gt; 0</code> excludes the case. The empty record itself
is retained in intermediate data for audit and coverage analysis.</p>
<div class="warning"><b>Decision:</b> excluded from modelling data when no
usable reasons text exists for the case. Do not treat an empty reasons record as
an empty string that the model can meaningfully learn from, and do not infer
reasons from metadata. Use the case only when usable reasons text is available
from another record.</div>

<h2>Detailed issue 3: matched by signature but header date disagrees</h2>
<p>The pairing pipeline connects an appellate judgment to the first-instance
judgment it reviews. It uses the signature, court hierarchy, court name from
the appellate header, and the first-instance judgment date.</p>

<h3>What the 1,215 cases mean</h3>
<p>The CSV reports <b>1,215 of 13,585</b> matched candidates (8.94%) where
the candidate date differs from the date in the appellate header. The old
wording said “date or court disagrees”, but that was imprecise: a candidate
whose court name disagrees is rejected before it becomes a matched candidate.
Thus this row primarily measures date disagreement.</p>

<h3>Why a matching signature is not enough</h3>
<p>A signature such as <code>I C 312/12</code> is not globally unique. Similar
signatures can occur in different courts, and one court can have multiple
records for a signature because of a retrial, partial judgment, duplicate
upload, or another publication event. A wrong pair would look like:</p>
<div class="critical"><code>text of first-instance judgment A → outcome label from appeal concerning judgment B</code></div>

<h3>Why we take the conservative approach</h3>
<p>The date discrepancy may be a source typo, a difference between announcement
and preparation dates, a parser problem, or a different judgment with the same
signature. Without independent evidence, automatically accepting the pair
could introduce a wrong text-target association.</p>
<div class="box"><b>Concrete example — case key
<code>275|VI ACa 630/11</code>.</b> This is one of the CSV examples in the
1,215-row group. The pairing process found a first-instance candidate by
signature and court hierarchy, but the candidate's judgment date did not equal
the date written in the appellate header. The pair is therefore kept for
diagnostics in <code>pairs.parquet</code>, but excluded from the modelling
dataset rather than assigning a potentially wrong first-instance text to the
appeal label.</div>
<div class="warning"><b>Decision:</b> pairs with a header-date disagreement are
excluded from the final modelling dataset but retained in <code>pairs.parquet</code>
for diagnostics. Court-mismatched candidates are also not accepted.</div>

<h2>Detailed issue 4: judgment date outside 1990–2026 or unparseable</h2>
<p>The report identifies <b>3 of 474,894</b> common-court records whose source
judgment date is outside the expected 1990–2026 range or cannot be parsed as a
valid date. These are source-data anomalies, not ordinary differences between
the date of a judgment and the date on which it was published.</p>
<div class="box"><b>Concrete examples and exact evidence.</b>
<ul>
<li><code>358516</code>, case <code>II K 336/17</code>, has source date
<code>0208-03-14</code>. It is corrected to <code>2018-03-14</code> because
the same-court, same-signature <code>SENTENCE</code> record
<code>358515</code> has judgment date <code>2018-03-14</code>.</li>
<li><code>227221</code>, case <code>II K 84/16</code>, has source date
<code>2101-04-14</code>. It is corrected to <code>2016-04-14</code> because
the text header says “Dnia 14 kwietnia 21016 r.”, the text gives hearing dates
<code>10.03.2016</code> and <code>14.04.2016</code>, and the SAOS source
identifier refers to the 2016 upload.</li>
<li><code>31345</code>, case <code>I ACa 772/13</code>, has source date
<code>3013-12-04</code>. It is corrected to <code>2013-12-04</code> because
the judgment text says it was heard on “4 grudnia 2013 r.” and the SAOS source
identifier includes <code>2013-12-04</code>.</li>
</ul>
These are record-specific evidence chains, not assumptions based only on the
date range.</div>
<h3>Treatment</h3>
<p>Each correction is an explicit record-ID rule in the preprocessing step,
documented in <code>data/CLEANING.md</code>. The rule first verifies that the
source still contains the expected erroneous value and raises an error if it
has changed. This prevents a correction from silently being applied to a
different record. No general rule guesses a year for every malformed date.</p>
<div class="warning"><b>Decision:</b> correct the three verified source typos in
preprocessing and retain the corrected dates in derived data; preserve the
original anomalies in the quality report for audit.</div>

<h2>Detailed issue 5: published before the judgment date</h2>
<p>The report finds <b>44 of 474,894</b> records (0.01%) where the SAOS
<code>source.publicationDate</code> is earlier than the record's
<code>judgmentDate</code>. This is a metadata consistency warning, not proof
that a published document existed before the court actually issued the
judgment.</p>
<div class="box"><b>Concrete examples.</b>
<ul>
<li>Record <code>199625</code> has <code>judgmentDate = 2016-02-13</code> and
<code>publicationDate = 2016-02-10</code>. Its text header says
“dnia 13 stycznia 2016 roku”, so the text itself indicates a date earlier than
the API judgment date. This points to an inconsistent judgment-date field,
not necessarily an impossible publication.</li>
<li>Record <code>175911</code> has <code>judgmentDate = 2016-05-26</code> and
<code>publicationDate = 2015-09-09</code>. The record must be treated as a
source metadata anomaly until the original court publication history is
independently verified.</li>
</ul></div>
<h3>Treatment</h3>
<p>We do not apply a general date correction based only on this comparison.
The text date, source identifier, and publication history can have different
meanings, and the CSV check alone cannot establish which field is wrong. The
records remain available for modelling when they pass the ordinary text and
pairing filters. The anomaly is retained for audit, while
<code>publication_date</code> is not used as the modelling or temporal-split
date.</p>
<div class="warning"><b>Decision:</b> retain in modelling data; flag for audit
and do not use <code>publication_date</code> as the modelling date.</div>

<h2>Detailed issue 6: reasons record dated before its sentence</h2>
<p>The report finds <b>152 of 39,654</b> cases with separate
<code>SENTENCE</code> and <code>REASONS</code> records where the
<code>REASONS</code> record has an earlier <code>judgmentDate</code> than the
sentence record. The comparison is a metadata consistency check; it does not
compare the dates printed inside the documents.</p>
<div class="box"><b>Concrete examples.</b> The CSV lists
<code>276|XVII AmC 334/09</code>, <code>276|XVII AmC 935/09</code>, and
<code>276|XVII AmC 124/07</code>. For each, the derived case table contains
separate sentence and reasons records, and the reasons-record date is earlier
than the sentence-record date. The current checkout does not contain
<code>data/interim/records.parquet</code>, so the exact two source dates for
these examples cannot be independently reproduced here.</div>
<h3>Interpretation</h3>
<p>This may be a source-date problem, a record-linking problem, or a difference
in date semantics. A reasons record can be dated when the reasons were written,
registered, or imported, while the sentence record can carry the date of the
hearing or judgment. The anomaly is therefore not sufficient by itself to
declare the text unusable.</p>
<h3>Treatment</h3>
<p>We do not reorder or discard a case solely because the reasons-record date
precedes the sentence date. If the case has usable sentence and reasons text
and passes the ordinary pairing checks, it remains eligible for modelling.
The date anomaly is retained for audit and is not used as a model feature or
as the temporal split date.</p>
<div class="warning"><b>Decision:</b> retain if the case has usable text and a
valid pairing; flag the date anomaly for audit.</div>

<h2>Detailed issue 7: reasons record dated more than one year after its sentence</h2>
<p>The report finds <b>121 of 39,654</b> cases (0.31%) with separate
<code>SENTENCE</code> and <code>REASONS</code> records where the reasons-record
date is more than 365 days later than the sentence-record date. This is a
record-date gap, not evidence that the written reasons are necessarily wrong
or unusable.</p>
<div class="box"><b>Concrete examples.</b> The CSV lists
<code>39|II K 11/03</code>, <code>159|III Ca 1544/16</code>, and
<code>276|XVII AmC 5200/11</code>. These cases have separate sentence and
reasons records, with the reasons record dated more than a year after the
sentence record. The current checkout does not contain
<code>data/interim/records.parquet</code>, so the exact source dates for these
examples cannot be independently reproduced here.</div>
<h3>Interpretation</h3>
<p>A written justification may be prepared, registered, uploaded, or published
long after the judgment was announced. The two records may therefore use
different date semantics. A large gap can also indicate a source metadata
error or an incorrect record association, so it should remain visible in the
quality audit.</p>
<h3>Treatment</h3>
<p>We do not exclude a case solely because the reasons date is more than one
year later. If the selected sentence and reasons texts are usable and the
appeal pairing is valid, the case remains eligible for modelling. The date is
not used as a model feature or as the temporal split date.</p>
<div class="warning"><b>Decision:</b> retain if the case has usable text and a
valid pairing; flag the date anomaly for audit.</div>

<h2>Detailed issue 8: case signature not in the standard form</h2>
<p>The report finds <b>1,810 of 474,894</b> records (0.38%) whose case
signature is not parsed into the standard roman-division, code, number, and
year structure. The parser represents this by leaving <code>code</code> empty.
This is a parser-recognition problem, not proof that every source signature is
invalid.</p>
<div class="box"><b>Concrete example.</b> The most common examples are
<code>IV 1 P 51/11</code>, <code>IV 2 P 365/10</code>, and
<code>XI 1Ca 508/13</code>. In particular, <code>IV 1 P 51/11</code> has an
extra digit after the division numeral. The current regular expression expects
the roman division to be followed directly by the letter code, so it does not
recognise this local subdivision format.</div>
<h3>Why this matters</h3>
<p>A signature is used to classify the legal domain, determine whether a case
is first-instance or appellate, build the <code>case_key</code>, and find
matching first-instance judgments. If parsing fails, the record can be lost
from domain-specific processing or cannot be paired reliably. On the other
hand, the 1,807 digit-after-division examples may be valid court-specific
notation, so rejecting them solely because they differ from the common format
would lose potentially usable data.</p>
<h3>Treatment</h3>
<p>We do not apply a blanket correction or silently rewrite these source
signatures. A record is eligible only if its signature can be parsed
unambiguously and the resulting case passes the normal court, date, text, and
pairing checks. Records that remain unparsable or cannot be paired are excluded
from modelling data, while the original signature is retained for audit.</p>
<div class="warning"><b>Decision:</b> local signature variants are not rejected
solely for their format; successful parsing and pairing are required before
modelling.</div>

<h2>Other handling rules</h2>
<ul>
<li>Verified source date typos are corrected by explicit record-ID rules and
documented in <code>data/CLEANING.md</code>.</li>
<li>Empty appellate sentences, missing headers, missing first-instance
signatures, and unrecognised outcomes are not used to form reliable modelling
rows.</li>
<li>An empty extracted ruling after the header is an implementation issue:
the extraction must be fixed or checked against raw text before excluding a
source record as truncated.</li>
<li>SAOS <code>judgmentIds</code> are identifiers of cited judgments. They are
not treated as an error or as the primary appeal-pairing mechanism.</li>
<li>Short first-instance text is flagged, not automatically called truncated:
it can be a valid short decision or an incomplete text.</li>
<li>Missing presiding-judge role metadata is reported separately for the final
modelling set: 398 of 10,644 rows (3.74%). Of these, 54 have exactly one judge
and can be corrected deterministically; 340 have no judge and 4 remain
ambiguous.</li>
</ul>

<p class="small">The complete issue table, including counts, examples,
importance and treatment for all checks, is maintained separately in
<code>results/saos-data-quality.csv</code>.</p>
</body>
</html>
""",
        encoding="utf-8",
    )
    report = HTML_PATH.read_text(encoding="utf-8")
    report = report.replace(
        "<h2>Other handling rules</h2>",
        issue_register() + "\n<h2>Other handling rules</h2>",
    )
    HTML_PATH.write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
