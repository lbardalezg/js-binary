"""Helpers that reproduce JavaScript runtime semantics used by the encoder.

These mirror what the original library relies on from the JS runtime:
``String(value)`` for error messages, ``JSON.stringify`` for the ``json`` type,
and UTF-8 encoding of JS strings (including lone-surrogate replacement).
"""

import math
import re

_ARRAY_INDEX_RE = re.compile(r"^[0-9]+$")


def _is_array_index(key):
    if not _ARRAY_INDEX_RE.match(key):
        return False
    if len(key) > 1 and key[0] == "0":
        return False
    return int(key) <= 0xFFFFFFFE


def js_object_keys(mapping):
    """Return keys in JS ``Object.keys`` order: array indices ascending, then the rest."""
    indices = []
    others = []
    for key in mapping:
        if isinstance(key, str) and _is_array_index(key):
            indices.append((int(key), key))
        else:
            others.append(key)
    indices.sort(key=lambda pair: pair[0])
    return [key for _, key in indices] + others


class _Undefined:
    """The JavaScript ``undefined`` value (distinct from ``None``/``null``)."""

    __slots__ = ()

    def __repr__(self):
        return "undefined"

    def __str__(self):
        return "undefined"

    def __bool__(self):
        return False


UNDEFINED = _Undefined()


def number_to_string(value):
    """Format a number the way ECMAScript ``Number::toString`` does."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    x = float(value)
    if math.isnan(x):
        return "NaN"
    if x == 0.0:
        return "0"
    if math.isinf(x):
        return "Infinity" if x > 0 else "-Infinity"
    if x < 0:
        return "-" + number_to_string(-x)
    digits, n = _shortest_digits(x)
    k = len(digits)
    if k <= n <= 21:
        return digits + "0" * (n - k)
    if 0 < n <= 21:
        return digits[:n] + "." + digits[n:]
    if -6 < n <= 0:
        return "0." + "0" * (-n) + digits
    exponent = n - 1
    sign = "+" if exponent >= 0 else "-"
    mantissa = digits if k == 1 else digits[0] + "." + digits[1:]
    return mantissa + "e" + sign + str(abs(exponent))


def _shortest_digits(x):
    text = repr(x)
    mantissa, _, exp_text = text.partition("e")
    exponent = int(exp_text) if exp_text else 0
    int_part, _, frac_part = mantissa.partition(".")
    digits = int_part + frac_part
    e10 = exponent - len(frac_part)
    digits = digits.lstrip("0")
    trailing = len(digits) - len(digits.rstrip("0"))
    digits = digits.rstrip("0")
    e10 += trailing
    return digits, e10 + len(digits)


_JSON_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


def _quote(text):
    out = ['"']
    for ch in text:
        escape = _JSON_ESCAPES.get(ch)
        if escape is not None:
            out.append(escape)
            continue
        code = ord(ch)
        if code < 0x20 or 0xD800 <= code <= 0xDFFF:
            out.append("\\u%04x" % code)
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _member_key(key):
    if isinstance(key, str):
        return key
    if key is True:
        return "true"
    if key is False:
        return "false"
    if key is None:
        return "null"
    if isinstance(key, (int, float)):
        return number_to_string(key)
    return str(key)


def _serialize(value):
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _quote(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return "null"
        return number_to_string(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_serialize(item) for item in value) + "]"
    if isinstance(value, dict):
        items = [
            _quote(_member_key(key)) + ":" + _serialize(value[key])
            for key in js_object_keys(value)
        ]
        return "{" + ",".join(items) + "}"
    if isinstance(value, (bytes, bytearray, memoryview)):
        raw = bytes(value)
        return '{"type":"Buffer","data":[' + ",".join(str(b) for b in raw) + "]}"
    return "null"


def json_dumps(value):
    """Serialize ``value`` exactly like JavaScript ``JSON.stringify``."""
    return _serialize(value)


def to_js_string(value):
    """Format ``value`` the way JavaScript ``String(value)`` does (for messages)."""
    if value is UNDEFINED:
        return "undefined"
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return number_to_string(value)
    if isinstance(value, (list, tuple)):
        return ",".join(
            "" if (item is None or item is UNDEFINED) else to_js_string(item)
            for item in value
        )
    if isinstance(value, dict):
        return "[object Object]"
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).decode("utf-8", "replace")
    return str(value)


def utf8_encode(text):
    """Encode ``text`` as UTF-8, replacing lone surrogates with U+FFFD like JS."""
    try:
        return text.encode("utf-8")
    except UnicodeEncodeError:
        return text.encode("utf-16", "surrogatepass").decode("utf-16", "replace").encode("utf-8")


def normalize_regex_source(source):
    """Return the source the way JS ``RegExp.prototype.source`` does.

    Escapes unescaped ``/`` and line terminators; an empty source becomes ``(?:)``.
    """
    if source == "":
        return "(?:)"
    out = []
    pending = 0
    in_class = False
    for ch in source:
        if ch == "\\":
            out.append(ch)
            pending += 1
            continue
        escaped = pending % 2 == 1
        if ch == "/":
            if not in_class and not escaped:
                out.append("\\")
            out.append("/")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\u2028":
            out.append("\\u2028")
        elif ch == "\u2029":
            out.append("\\u2029")
        elif ch == "[" and not in_class and not escaped:
            in_class = True
            out.append(ch)
        elif ch == "]" and in_class and not escaped:
            in_class = False
            out.append(ch)
        else:
            out.append(ch)
        pending = 0
    return "".join(out)
