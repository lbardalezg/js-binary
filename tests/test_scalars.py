import struct
from datetime import datetime, timedelta, timezone

from js_binary import Regex, Type

import pytest

UTC = timezone.utc


def enc(schema, value):
    return Type(schema).encode(value)


def roundtrip(schema, value):
    return Type(schema).decode(Type(schema).encode(value))


@pytest.mark.parametrize("value,expected", [
    (0, "00"),
    (1, "01"),
    (127, "7f"),
    (128, "8080"),
    (16383, "bfff"),
    (16384, "c0004000"),
    (536870911, "dfffffff"),
    (536870912, "e000000020000000"),
    (2 ** 53, "e020000000000000"),
])
def test_uint_known_bytes(value, expected):
    assert enc("uint", value).hex() == expected


@pytest.mark.parametrize("value", [0, 1, 127, 128, 16383, 16384, 536870911, 536870912,
                                   2 ** 53 - 1, 2 ** 53])
def test_uint_roundtrip(value):
    assert roundtrip("uint", value) == value


def test_uint_accepts_integral_float_like_js():
    assert enc("uint", 5.0).hex() == enc("uint", 5).hex()


@pytest.mark.parametrize("value,expected", [
    (0, "00"),
    (63, "3f"),
    (-1, "7f"),
    (-64, "40"),
    (64, "8040"),
    (-65, "bfbf"),
    (8191, "9fff"),
    (-8192, "a000"),
    (8192, "c0002000"),
])
def test_int_known_bytes(value, expected):
    assert enc("int", value).hex() == expected


@pytest.mark.parametrize("value", [-2 ** 53, -2 ** 28 - 1, -2 ** 28, -8193, -8192, -65, -64,
                                   -1, 0, 63, 64, 8191, 8192, 2 ** 28 - 1, 2 ** 28, 2 ** 53])
def test_int_roundtrip(value):
    assert roundtrip("int", value) == value


@pytest.mark.parametrize("value,expected", [
    (0.0, "0000000000000000"),
    (-0.0, "8000000000000000"),
    (1.5, "3ff8000000000000"),
    (float("nan"), "7ff8000000000000"),
    (float("inf"), "7ff0000000000000"),
    (float("-inf"), "fff0000000000000"),
])
def test_float_known_bytes(value, expected):
    assert enc("float", value).hex() == expected


def test_float_accepts_int():
    assert enc("float", 3).hex() == struct.pack(">d", 3.0).hex()


def test_string_known_bytes():
    assert enc("string", "").hex() == "00"
    assert enc("string", "héllo").hex() == "0668c3a96c6c6f"


def test_buffer_known_bytes():
    assert enc("Buffer", b"\x01\x02").hex() == "020102"
    assert enc("Buffer", b"").hex() == "00"


@pytest.mark.parametrize("value,expected", [(True, "01"), (False, "00")])
def test_boolean_known_bytes(value, expected):
    assert enc("boolean", value).hex() == expected


def test_json_known_bytes():
    assert enc("json", {"a": 1}).hex() == "077b2261223a317d"


def test_json_roundtrip_preserves_structure():
    value = {"a": [1, 2.5, None, True, False], "b": {"c": "á😀"}, "d": 1e21}
    assert roundtrip("json", value) == value


def test_oid_known_bytes():
    oid = "abcdef0123456789abcdef01"
    assert enc("oid", oid).hex() == oid
    assert roundtrip("oid", oid) == oid


def test_oid_accepts_raw_bytes():
    raw = bytes(range(12))
    assert enc("oid", raw).hex() == raw.hex()


@pytest.mark.parametrize("source,flags,expected", [
    ("ab", "", "02616200"),
    ("ab", "i", "02616202"),
    ("a+b", "gim", "03612b6207"),
])
def test_regex_known_bytes(source, flags, expected):
    assert enc("regex", Regex(source, flags)).hex() == expected


def test_regex_roundtrip_and_flags():
    result = roundtrip("regex", Regex("a.c", "gim"))
    assert isinstance(result, Regex)
    assert result.source == "a.c"
    assert result.flags == "gim"
    assert result.global_ and result.ignore_case and result.multiline


def test_regex_accepts_re_pattern():
    import re

    result = roundtrip("regex", re.compile("abc", re.IGNORECASE))
    assert isinstance(result, Regex)
    assert result.source == "abc"
    assert result.flags == "i"


@pytest.mark.parametrize("source,expected", [
    ("", "(?:)"),
    ("a/b", "a\\/b"),
    ("a\nb", "a\\nb"),
    ("a\rb", "a\\rb"),
])
def test_regex_source_is_normalized_like_js(source, expected):
    assert Regex(source).source == expected
    assert enc("regex", Regex(source)) == enc("regex", Regex(expected))


def test_date_known_bytes():
    assert enc("date", datetime(1970, 1, 1, tzinfo=UTC)).hex() == "00"
    assert enc("date", datetime(1970, 1, 1, tzinfo=UTC) + timedelta(milliseconds=1500)).hex() == "85dc"


def test_date_roundtrip_is_utc_aware():
    moment = datetime(2014, 4, 11, 21, 22, 32, 504000, tzinfo=UTC)
    result = roundtrip("date", moment)
    assert result == moment
    assert result.tzinfo is not None


def test_date_accepts_int_milliseconds():
    assert enc("date", 1500).hex() == "85dc"


def test_date_naive_treated_as_utc():
    naive = datetime(1970, 1, 1)
    aware = datetime(1970, 1, 1, tzinfo=UTC)
    assert enc("date", naive) == enc("date", aware)


@pytest.mark.parametrize("schema,value,message", [
    ("uint", -1, "Expected unsigned integer at , got -1"),
    ("uint", 1.5, "Expected unsigned integer at , got 1.5"),
    ("uint", "x", "Expected unsigned integer at , got x"),
    ("uint", 2 ** 53 + 2, "Expected unsigned integer at , got 9007199254740994"),
    ("int", 2 ** 53 + 2, "Expected signed integer at , got 9007199254740994"),
    ("float", "x", "Expected a number at , got x"),
    ("string", b"x", "Expected a string at , got x"),
    ("Buffer", "x", "Expected a Buffer at , got x"),
    ("boolean", 1, "Expected a boolean at , got 1"),
])
def test_scalar_error_messages(schema, value, message):
    with pytest.raises(TypeError) as excinfo:
        Type(schema).encode(value)
    assert str(excinfo.value) == message


def test_boolean_read_invalid():
    with pytest.raises(ValueError) as excinfo:
        Type("boolean").decode(b"\x02")
    assert str(excinfo.value) == "Invalid boolean value"


def test_read_beyond_buffer():
    with pytest.raises(IndexError) as excinfo:
        Type("uint").decode(b"")
    assert str(excinfo.value) == "Trying to access beyond buffer length"


def test_date_out_of_datetime_range_falls_back_to_milliseconds():
    milliseconds = 8640000000000000
    result = roundtrip("date", milliseconds)
    assert result == milliseconds
    assert isinstance(result, int)


def test_regex_pattern_extra_flags_ignored_like_js():
    import re

    result = roundtrip("regex", re.compile("a.b", re.IGNORECASE | re.DOTALL))
    assert result.flags == "i"
