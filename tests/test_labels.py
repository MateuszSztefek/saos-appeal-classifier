import pytest

from saos_appeals.data.labels import classify_ruling, ruling_text

HEADER = (
    "Sygn. akt IV Pa 47/12\nWYROK\nna skutek apelacji pozwanego\n"
    "od wyroku Sądu Rejonowego w Sieradzu\nz dnia 12 maja 2012 r. sygn. akt IV P 248/11\n"
)


def test_ruling_text_starts_after_the_header():
    assert ruling_text(HEADER + "oddala apelację.") == "oddala apelację."


def test_ruling_text_without_header_is_the_whole_text():
    assert ruling_text("oddala apelację.") == "oddala apelację."


@pytest.mark.parametrize(
    ("text", "outcome", "label"),
    [
        ("oddala apelację.", "dismissed", 0),
        ("o d d a l a apelację.-", "dismissed", 0),
        ("I. apelację oddala; II. zasądza od powoda 120 zł", "dismissed", 0),
        ("oddala obie apelacje.", "dismissed", 0),
        ("oddala apelację pozwanego w całości.", "dismissed", 0),
        ("utrzymuje w mocy zaskarżony wyrok.", "dismissed", 0),
        ("oddal apelację.", "dismissed", 0),
        ("oddala apleację.", "dismissed", 0),
        ("1. oddala apelacj e ; 2. zasądza", "dismissed", 0),
        ("postanowił: oddalić apelację", "dismissed", 0),
        ("zamienia zaskarżony wyrok oraz poprzedzającą go decyzję", "changed", 1),
        ("I. uchyla:\n- zaskarżony wyrok z 13 września 2012 r.", "set_aside", 1),
        ("uchylić zaskarżony wyrok w odniesieniu do punktu 2", "set_aside", 1),
        ("oddala skargę o wznowienie postępowania.", "unknown", None),
        ("zmienia zaskarżony wyrok w punkcie I i powództwo oddala.", "changed", 1),
        ("zmienia zaskarżony wyrok i oddala odwołanie", "changed", 1),
        ("zaskarżony wyrok zmienia w ten sposób, że zasądza 100 zł", "changed", 1),
        (
            "1. zmienia zaskarżony wyrok w pkt I; 2. oddala apelację w pozostałej części",
            "changed_partly",
            1,
        ),
        (
            "oddala apelację powoda; na skutek apelacji pozwanego zmienia zaskarżony wyrok",
            "changed_partly",
            1,
        ),
        (
            "uchyla zaskarżony wyrok i przekazuje sprawę do ponownego rozpoznania",
            "set_aside",
            1,
        ),
        ("uchyla zaskarżony wyrok i umarza postępowanie w sprawie", "set_aside", 1),
        ("odrzuca apelację.", "rejected", None),
        ("umarza postępowanie apelacyjne.", "discontinued", None),
        ("prostuje oczywistą omyłkę pisarską", "unknown", None),
    ],
)
def test_classify_ruling(text, outcome, label):
    result = classify_ruling(text)
    assert result["outcome"] == outcome
    assert result["label"] == label


def test_powodztwo_oddala_is_not_a_dismissed_appeal():
    # "oddala" refers to the claim, not the appeal
    assert classify_ruling("zmienia wyrok i powództwo oddala")["dismiss"] is False


def test_remand_flag():
    result = classify_ruling("uchyla zaskarżony wyrok i sprawę przekazuje do ponownego rozpoznania")
    assert result["remand"] is True
