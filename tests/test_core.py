from truthlayer.extract import (parse_number, sentences, classify_kind,
                                find_entity, find_claims, Claim)
from truthlayer.verify import compare, numbers_in, closest, VERIFIED, INACCURATE, FALSE


def test_parse_plain():
    assert parse_number("1,428", None) == (1428.0, "count")


def test_parse_percent():
    assert parse_number("5.6", "%") == (5.6, "percent")


def test_parse_scale():
    assert parse_number("1.2", "billion") == (1.2e9, "count")


def test_parse_crore():
    assert parse_number("24", "crore") == (2.4e8, "count")


def test_sentences_split():
    s = sentences("India has 1.4 billion people. Its GDP is 3.7 trillion dollars.")
    assert len(s) == 2


def test_classify_population():
    assert classify_kind("the population of india is 1.2 billion") == "population"


def test_classify_inflation():
    assert classify_kind("inflation hit 25% last year") == "inflation"


def test_entity_country():
    assert find_entity("India has 1.4 billion people") == ("India", "country")


def test_entity_org():
    name, kind = find_entity("SarvaaOne serves 166 agents across India")
    assert kind in ("country", "org")


def test_find_claims_finds_numbers():
    claims = find_claims("India's population is 1.2 billion people. The weather is nice.")
    assert len(claims) == 1
    assert claims[0].kind == "population"


def test_find_claims_skips_years():
    claims = find_claims("The report was published in 2019 and says nothing.")
    assert claims == []


def test_compare_verified():
    c = Claim("x", "1.4 billion", 1.4e9, "count", "population", "India", "country")
    assert compare(c, 1.43e9)[0] == VERIFIED


def test_compare_inaccurate():
    c = Claim("x", "1.2 billion", 1.2e9, "count", "population", "India", "country")
    assert compare(c, 1.43e9)[0] == INACCURATE


def test_compare_false():
    c = Claim("x", "500 million", 5e8, "count", "population", "United States", "country")
    assert compare(c, 3.35e8)[0] == FALSE


def test_compare_percent():
    c = Claim("x", "25%", 25.0, "percent", "inflation", "India", "country")
    assert compare(c, 5.6)[0] == FALSE


def test_numbers_in_text():
    assert 1.4e9 in numbers_in("about 1.4 billion people")


def test_closest():
    assert closest([1.4e9, 3.7e12], 1.43e9) == 1.4e9
