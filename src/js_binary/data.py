"""A mutable-length write-only byte buffer (mirror of js-binary's ``Data``)."""

import struct


class Data:
    def __init__(self, capacity=128):
        self._buffer = bytearray()

    def append_buffer(self, data):
        self._buffer += bytes(data)

    def write_uint8(self, value):
        self._buffer.append(int(value))

    def write_uint16(self, value):
        self._buffer += int(value).to_bytes(2, "big")

    def write_uint32(self, value):
        self._buffer += int(value).to_bytes(4, "big")

    def write_double(self, value):
        self._buffer += struct.pack(">d", float(value))

    def to_buffer(self):
        return bytes(self._buffer)

    appendBuffer = append_buffer
    writeUInt8 = write_uint8
    writeUInt16 = write_uint16
    writeUInt32 = write_uint32
    writeDouble = write_double
    toBuffer = to_buffer
