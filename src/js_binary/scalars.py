"""Scalar type implementations (mirror of js-binary's ``types.js``)."""

import json as _json
import math
import re
from datetime import datetime, timedelta, timezone

from ._js import (
    UNDEFINED,
    json_dumps,
    normalize_regex_source,
    to_js_string,
    utf8_encode,
)
from .regex import Regex

POW32 = 2 ** 32
MAX_DOUBLE_INT = 2 ** 53
MAX_UINT8 = 2 ** 7
MAX_UINT16 = 2 ** 14
MAX_UINT32 = 2 ** 29
MAX_INT8 = 2 ** 6
MAX_INT16 = 2 ** 13
MAX_INT32 = 2 ** 28

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def _int32(value):
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value >= 0x80000000 else value


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_integral(value):
    if isinstance(value, int):
        return True
    return math.isfinite(value) and value == math.floor(value)


def _hex_decode(value):
    result = bytearray()
    for index in range(0, len(value) - 1, 2):
        pair = value[index:index + 2]
        if pair[0] not in _HEX_DIGITS or pair[1] not in _HEX_DIGITS:
            break
        result.append(int(pair, 16))
    return bytes(result)


class _UInt:
    def write(self, value, data, path=UNDEFINED):
        if not _is_number(value) or not _is_integral(value) or value > MAX_DOUBLE_INT or value < 0:
            raise TypeError(
                "Expected unsigned integer at %s, got %s"
                % (to_js_string(path), to_js_string(value))
            )
        value = int(value)
        if value < MAX_UINT8:
            data.write_uint8(value)
        elif value < MAX_UINT16:
            data.write_uint16(value + 0x8000)
        elif value < MAX_UINT32:
            data.write_uint32(value + 0xC0000000)
        else:
            data.write_uint32(value // POW32 + 0xE0000000)
            data.write_uint32(value & 0xFFFFFFFF)

    def read(self, state):
        first = state.peek_uint8()
        if not first & 0x80:
            state._offset += 1
            return first
        if not first & 0x40:
            return state.read_uint16() - 0x8000
        if not first & 0x20:
            return state.read_uint32() - 0xC0000000
        return (state.read_uint32() - 0xE0000000) * POW32 + state.read_uint32()


class _Int:
    def write(self, value, data, path=UNDEFINED):
        if not _is_number(value) or not _is_integral(value) or value > MAX_DOUBLE_INT or value < -MAX_DOUBLE_INT:
            raise TypeError(
                "Expected signed integer at %s, got %s"
                % (to_js_string(path), to_js_string(value))
            )
        value = int(value)
        if -MAX_INT8 <= value < MAX_INT8:
            data.write_uint8(value & 0x7F)
        elif -MAX_INT16 <= value < MAX_INT16:
            data.write_uint16((value & 0x3FFF) + 0x8000)
        elif -MAX_INT32 <= value < MAX_INT32:
            data.write_uint32((value & 0x1FFFFFFF) + 0xC0000000)
        else:
            data.write_uint32(((value // POW32) & 0x1FFFFFFF) + 0xE0000000)
            data.write_uint32(value & 0xFFFFFFFF)

    def read(self, state):
        first = state.peek_uint8()
        if not first & 0x80:
            state._offset += 1
            return first - 0x80 if first & 0x40 else first
        if not first & 0x40:
            value = state.read_uint16() - 0x8000
            return _int32(value | 0xFFFFC000) if value & 0x2000 else value
        if not first & 0x20:
            value = state.read_uint32() - 0xC0000000
            return _int32(value | 0xE0000000) if value & 0x10000000 else value
        value = state.read_uint32() - 0xE0000000
        value = _int32(value | 0xE0000000) if value & 0x10000000 else value
        return value * POW32 + state.read_uint32()


class _Float:
    def write(self, value, data, path=UNDEFINED):
        if not _is_number(value):
            raise TypeError(
                "Expected a number at %s, got %s"
                % (to_js_string(path), to_js_string(value))
            )
        data.write_double(value)

    def read(self, state):
        return state.read_double()


class _String:
    def write(self, value, data, path=UNDEFINED):
        if not isinstance(value, str):
            raise TypeError(
                "Expected a string at %s, got %s"
                % (to_js_string(path), to_js_string(value))
            )
        _BUFFER.write(utf8_encode(value), data, path)

    def read(self, state):
        return _BUFFER.read(state).decode("utf-8", "replace")


class _Buffer:
    def write(self, value, data, path=UNDEFINED):
        if not isinstance(value, (bytes, bytearray, memoryview)):
            raise TypeError(
                "Expected a Buffer at %s, got %s"
                % (to_js_string(path), to_js_string(value))
            )
        raw = bytes(value)
        _UINT.write(len(raw), data, path)
        data.append_buffer(raw)

    def read(self, state):
        return state.read_buffer(_UINT.read(state))


class _Boolean:
    def write(self, value, data, path=UNDEFINED):
        if not isinstance(value, bool):
            raise TypeError(
                "Expected a boolean at %s, got %s"
                % (to_js_string(path), to_js_string(value))
            )
        data.write_uint8(1 if value else 0)

    def read(self, state):
        value = state.read_uint8()
        if value > 1:
            raise ValueError("Invalid boolean value")
        return bool(value)


class _Json:
    def write(self, value, data, path=UNDEFINED):
        _STRING.write(json_dumps(value), data, path)

    def read(self, state):
        return _json.loads(_STRING.read(state))


class _Oid:
    def write(self, value, data, path=UNDEFINED):
        if isinstance(value, (bytes, bytearray, memoryview)):
            raw = bytes(value)
        else:
            raw = _hex_decode(to_js_string(value))
        if len(raw) != 12:
            raise TypeError(
                "Expected an object id (12 bytes) at %s, got %s"
                % (to_js_string(path), to_js_string(value))
            )
        data.append_buffer(raw)

    def read(self, state):
        return state.read_buffer(12).hex()


def _regex_source_flags(value, path):
    if isinstance(value, Regex):
        return value.source, value.flags
    if isinstance(value, re.Pattern):
        flags = ""
        if value.flags & re.IGNORECASE:
            flags += "i"
        if value.flags & re.MULTILINE:
            flags += "m"
        return normalize_regex_source(value.pattern), flags
    if isinstance(value, str):
        return normalize_regex_source(value), ""
    raise TypeError(
        "Expected an instance of RegExp at %s, got %s"
        % (to_js_string(path), to_js_string(value))
    )


class _Regex:
    def write(self, value, data, path=UNDEFINED):
        source, flags = _regex_source_flags(value, path)
        _STRING.write(source, data, path)
        bits = 0
        if "g" in flags:
            bits |= 1
        if "i" in flags:
            bits |= 2
        if "m" in flags:
            bits |= 4
        data.write_uint8(bits)

    def read(self, state):
        source = _STRING.read(state)
        flags = state.read_uint8()
        text = (
            ("g" if flags & 1 else "")
            + ("i" if flags & 2 else "")
            + ("m" if flags & 4 else "")
        )
        return Regex(source, text)


def _datetime_to_ms(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    delta = value - _EPOCH
    return delta.days * 86400000 + delta.seconds * 1000 + delta.microseconds // 1000


class _Date:
    def write(self, value, data, path=UNDEFINED):
        if isinstance(value, datetime):
            milliseconds = _datetime_to_ms(value)
        elif _is_number(value) and _is_integral(value):
            milliseconds = int(value)
        else:
            raise TypeError(
                "Expected an instance of Date at %s, got %s"
                % (to_js_string(path), to_js_string(value))
            )
        _UINT.write(milliseconds, data, path)

    def read(self, state):
        milliseconds = _UINT.read(state)
        try:
            return _EPOCH + timedelta(milliseconds=milliseconds)
        except OverflowError:
            # JavaScript dates span ~±8.64e15 ms, beyond datetime's range.
            # Return the raw milliseconds so no valid value is ever lost.
            return milliseconds


_UINT = _UInt()
_INT = _Int()
_FLOAT = _Float()
_STRING = _String()
_BUFFER = _Buffer()
_BOOLEAN = _Boolean()
_JSON = _Json()
_OID = _Oid()
_REGEX = _Regex()
_DATE = _Date()

types = {
    "uint": _UINT,
    "int": _INT,
    "float": _FLOAT,
    "string": _STRING,
    "Buffer": _BUFFER,
    "boolean": _BOOLEAN,
    "json": _JSON,
    "oid": _OID,
    "regex": _REGEX,
    "date": _DATE,
}
