import pytest

from saos_appeals.data.judgments import parse_signature
from saos_appeals.data.pairs import court_matches, court_tokens, parse_header
from saos_appeals.data.text import html_to_text, split_operative_reasons


def test_parse_signature_labour_appeal():
    sig = parse_signature("IV Pa 47/12")
    assert sig["division_roman"] == "IV"
    assert sig["code"] == "Pa"
    assert sig["case_seq"] == 47
    assert sig["case_year"] == 2012
    assert sig["domain"] == "labour"
    assert sig["appeal_kind"] == "appeal"
    assert sig["instance"] == 2


def test_parse_signature_appellate_court_code():
    sig = parse_signature("III AUa 2342/03")
    assert sig["domain"] == "social_insurance"
    assert sig["appeal_kind"] == "appeal"


def test_parse_signature_first_instance_and_two_digit_year():
    sig = parse_signature("II K 336/97")
    assert sig["appeal_kind"] == "first_instance"
    assert sig["case_year"] == 1997


def test_parse_signature_pen_is_criminal_not_labour():
    sig = parse_signature("II Pen 257/19")
    assert sig["code"] == "Pen"
    assert sig["domain"] == "criminal"
    assert sig["appeal_kind"] == "first_instance"


def test_parse_signature_rejects_garbage():
    assert parse_signature("I 2C 1691/13")["code"] is None


def test_html_to_text_strips_tags_and_keeps_paragraphs():
    html = "<p>Sygn. akt <span class='anon'>IV P 1/12</span></p><!-- x --><p>WYROK</p>"
    assert html_to_text(html) == "Sygn. akt IV P 1/12\n\nWYROK"


def test_split_operative_reasons_on_plain_and_spaced_heading():
    assert split_operative_reasons("wyrok\nUZASADNIENIE\nPowód") == ("wyrok", "Powód")
    assert split_operative_reasons("wyrok\nU Z A S A D N I E N I E\nPowód") == ("wyrok", "Powód")
    assert split_operative_reasons("wyrok\nSygn. akt II AKa 1/05 UZASADNIENIE\nSąd") == (
        "wyrok",
        "Sąd",
    )


def test_split_operative_reasons_ignores_the_word_in_a_sentence():
    text = "wyrok\nwniosek o uzasadnienie wyroku został złożony\nkoszty"
    assert split_operative_reasons(text) == (text, "")


def test_parse_header():
    header = parse_header(
        "na skutek apelacji pozwanego\nod wyroku Sądu Rejonowego w Gliwicach\n"
        "z dnia 20 października 2008 r.\nsygn. akt VI P 1651/07\n1. oddala apelację"
    )
    assert header["header_level"] == "DISTRICT"
    assert header["header_date"] == "2008-10-20"
    assert header["header_signature"] == "VI P 1651/07"
    assert court_tokens(header["header_court"]) == {"gliwicach"}


def test_court_tokens_drop_anonymised_parts():
    assert court_tokens("Sądu Okręgowego w. W.") == set()
    assert court_tokens("Sąd Rejonowy dla Warszawy-Mokotowa w Warszawie") == {
        "warszawy",
        "mokotowa",
        "warszawie",
    }


@pytest.mark.parametrize(
    ("dictionary_name", "header", "expected"),
    [
        ("Sąd Rejonowy w Lubinie", "Sądu Rejonowego w Lubinie", True),
        ("Sąd Rejonowy w Lubinie", "Sądu Rejonowego w Legnicy", False),
        # header omits the seat of a named district court
        (
            "Sąd Rejonowy dla Wrocławia-Śródmieścia we Wrocławiu",
            "Sądu Rejonowego dla Wrocławia-Śródmieścia X Wydział Pracy",
            True,
        ),
        # sibling court in the same city
        (
            "Sąd Rejonowy dla Wrocławia-Śródmieścia we Wrocławiu",
            "Sądu Rejonowego dla Wrocławia-Krzyków",
            False,
        ),
        ("Sąd Okręgowy w Piotrkowie Trybunalskim", "Sądu Okręgowego w Piotrkowie Tryb.", True),
        (
            "Sąd Rejonowy Gdańsk-Południe w Gdańsku",
            "Sądu Rejonowego Gdańsk-Północ w Gdańsku",
            False,
        ),
    ],
)
def test_court_matches(dictionary_name, header, expected):
    assert court_matches(dictionary_name, court_tokens(header)) is expected
