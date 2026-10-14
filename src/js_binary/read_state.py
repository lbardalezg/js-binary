"""Wraps a bytes buffer with a read head pointer (mirror of ``ReadState``)."""

import struct

from ._js import to_js_string


class ReadState:
    def __init__(self, buffer):
        if not isinstance(buffer, (bytes, bytearray, memoryview)):
            raise TypeError("Expected a bytes-like buffer, got " + to_js_string(buffer))
        self._buffer = bytes(buffer)
        self._offset = 0

    def _require(self, count):
        if self._offset + count > len(self._buffer):
            raise IndexError("Trying to access beyond buffer length")

    def peek_uint8(self):
        self._require(1)
        return self._buffer[self._offset]

    def read_uint8(self):
        self._require(1)
        value = self._buffer[self._offset]
        self._offset += 1
        return value

    def read_uint16(self):
        self._require(2)
        value = struct.unpack_from(">H", self._buffer, self._offset)[0]
        self._offset += 2
        return value

    def read_uint32(self):
        self._require(4)
        value = struct.unpack_from(">I", self._buffer, self._offset)[0]
        self._offset += 4
        return value

    def read_double(self):
        self._require(8)
        value = struct.unpack_from(">d", self._buffer, self._offset)[0]
        self._offset += 8
        return value

    def read_buffer(self, length):
        self._require(length)
        value = self._buffer[self._offset:self._offset + length]
        self._offset += length
        return value

    def has_ended(self):
        return self._offset == len(self._buffer)

    peekUInt8 = peek_uint8
    readUInt8 = read_uint8
    readUInt16 = read_uint16
    readUInt32 = read_uint32
    readDouble = read_double
    readBuffer = read_buffer
    hasEnded = has_ended
