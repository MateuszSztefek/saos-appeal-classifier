import pandas as pd
import pytest

from saos_appeals import quality
from saos_appeals.data.judgments import record_to_row


@pytest.mark.parametrize(
    ("record_id", "source_date", "corrected_date"),
    [
        (358516, "0208-03-14", "2018-03-14"),
        (227221, "2101-04-14", "2016-04-14"),
        (31345, "3013-12-04", "2013-12-04"),
    ],
)
def test_record_to_row_corrects_verified_judgment_dates(record_id, source_date, corrected_date):
    row = record_to_row(
        {"id": record_id, "judgmentDate": source_date},
        {},
    )

    assert row["judgment_date"] == corrected_date
    assert row["judgment_year"] == int(corrected_date[:4])


def test_record_to_row_rejects_unexpected_source_date_for_correction():
    with pytest.raises(ValueError, match="Unexpected judgmentDate for SAOS record 358516"):
        record_to_row({"id": 358516, "judgmentDate": "2008-03-14"}, {})


def test_date_quality_row_keeps_corrected_source_typos_auditable():
    tables = quality.Tables(
        records=pd.DataFrame(
            {
                "id": [358516, 227221, 31345],
                "judgment_year": [2018, 2016, 2013],
                "judgment_date": ["2018-03-14", "2016-04-14", "2013-12-04"],
                "publication_date": ["2018-10-25", "2016-06-11", "2014-01-22"],
            }
        ),
        cases=pd.DataFrame(columns=["sentence_id", "reasons_id", "case_key"]),
        pairs=pd.DataFrame(),
        labels=pd.DataFrame(),
        datasets=pd.DataFrame(),
    )

    date_row = quality.dates(tables)[0]

    assert date_row["count"] == 3
    assert date_row["note"] == "typos in the source, e.g. year 208 or 3013"
    assert date_row["treatment"] == "Fixable; corrected in preprocessing"
    assert "358516:0208-03-14->2018-03-14" in date_row["example"]
