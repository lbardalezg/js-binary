import math

from js_binary._js import json_dumps, number_to_string, to_js_string, utf8_encode

import pytest


@pytest.mark.parametrize("value,expected", [
    (0.0, "0"),
    (-0.0, "0"),
    (1.0, "1"),
    (-1.0, "-1"),
    (0.1, "0.1"),
    (-0.1, "-0.1"),
    (1.5, "1.5"),
    (123.456, "123.456"),
    (1e21, "1e+21"),
    (1e20, "100000000000000000000"),
    (1e-6, "0.000001"),
    (1e-7, "1e-7"),
    (3.141592653589793, "3.141592653589793"),
    (2 ** 53, "9007199254740992"),
    (float("inf"), "Infinity"),
    (float("-inf"), "-Infinity"),
])
def test_number_to_string(value, expected):
    assert number_to_string(value) == expected


def test_number_to_string_nan():
    assert number_to_string(float("nan")) == "NaN"


@pytest.mark.parametrize("value,expected", [
    (None, "null"),
    (True, "true"),
    (False, "false"),
    (5, "5"),
    ("a", '"a"'),
    (b"ab", '{"type":"Buffer","data":[97,98]}'),
    ("a\"b\\c\n", '"a\\"b\\\\c\\n"'),
    ("\x00\x1f", '"\\u0000\\u001f"'),
    ({"a": 1.0, "b": 1e21, "c": -0.0, "d": None, "e": True},
     '{"a":1,"b":1e+21,"c":0,"d":null,"e":true}'),
    ([1, 2.5, "x"], '[1,2.5,"x"]'),
    (float("nan"), "null"),
    (float("inf"), "null"),
])
def test_json_dumps(value, expected):
    assert json_dumps(value) == expected


def test_json_dumps_unicode_not_escaped():
    assert json_dumps("á😀漢") == '"á😀漢"'


def test_to_js_string():
    from js_binary._js import UNDEFINED

    assert to_js_string(UNDEFINED) == "undefined"
    assert to_js_string(None) == "null"
    assert to_js_string(True) == "true"
    assert to_js_string([1, None, 2]) == "1,,2"
    assert to_js_string({"a": 1}) == "[object Object]"


def test_json_dumps_object_keys_follow_js_order():
    assert json_dumps({"b": 1, "2": 2, "1": 1}) == '{"1":1,"2":2,"b":1}'
    assert json_dumps({"10": 1, "2": 2, "b": 3, "a": 4}) == '{"2":2,"10":1,"b":3,"a":4}'
    assert json_dumps({"01": 1, "1": 2, "x": 3}) == '{"1":2,"01":1,"x":3}'


def test_js_object_keys_semantics():
    from js_binary._js import js_object_keys

    assert js_object_keys({"b": 1, "2": 2, "1": 1}) == ["1", "2", "b"]
    assert js_object_keys({"01": 1, "1": 2, "x": 3}) == ["1", "01", "x"]
    assert js_object_keys({"10": 1, "2": 2, "b": 3, "a": 4}) == ["2", "10", "b", "a"]


@pytest.mark.parametrize("source,expected", [
    ("", "(?:)"),
    ("a/b", "a\\/b"),
    ("a\nb", "a\\nb"),
    ("a\rb", "a\\rb"),
    ("[/\\\\]", "[/\\\\]"),
    ("(?:)", "(?:)"),
    ("a\\/b", "a\\/b"),
])
def test_normalize_regex_source(source, expected):
    from js_binary._js import normalize_regex_source

    assert normalize_regex_source(source) == expected


def test_utf8_encode_replaces_lone_surrogate():
    assert utf8_encode("\ud800") == b"\xef\xbf\xbd"
    assert utf8_encode("😀") == b"\xf0\x9f\x98\x80"
