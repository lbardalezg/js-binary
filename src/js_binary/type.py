"""The main ``Type`` class (mirror of js-binary's ``Type``)."""

from ._js import UNDEFINED, js_object_keys, to_js_string
from .data import Data
from .field import Field
from .read_state import ReadState
from .scalars import types

TYPE = {
    "UINT": "uint",
    "INT": "int",
    "FLOAT": "float",
    "STRING": "string",
    "BUFFER": "Buffer",
    "BOOLEAN": "boolean",
    "JSON": "json",
    "OID": "oid",
    "REGEX": "regex",
    "DATE": "date",
    "ARRAY": "[array]",
    "OBJECT": "{object}",
}

_BASIC_TYPES = frozenset(
    value for key, value in TYPE.items() if key not in ("ARRAY", "OBJECT")
)


class Type:
    TYPE = TYPE

    def __init__(self, type):
        if isinstance(type, str):
            if type not in _BASIC_TYPES:
                raise TypeError("Unknown basic type: " + type)
            self.type = type
        elif isinstance(type, (list, tuple)):
            if len(type) != 1:
                raise TypeError("Invalid array type, it must have exactly one element")
            self.type = TYPE["ARRAY"]
            self.sub_type = Type(type[0])
            self.subType = self.sub_type
        elif isinstance(type, dict):
            self.type = TYPE["OBJECT"]
            self.fields = [Field(name, type[name]) for name in js_object_keys(type)]
        else:
            raise TypeError("Invalid type: " + to_js_string(type))

    def encode(self, value):
        data = Data()
        self.write(value, data, "")
        return data.to_buffer()

    def decode(self, buffer):
        return self.read(ReadState(buffer))

    def write(self, value, data, path=""):
        if self.type == TYPE["ARRAY"]:
            return self._write_array(value, data, path, self.sub_type)
        if self.type != TYPE["OBJECT"]:
            return types[self.type].write(value, data, path)
        if value is None or not isinstance(value, dict):
            raise TypeError("Expected an object at " + path)
        for field in self.fields:
            subpath = path + "." + field.name if path else field.name
            subvalue = value.get(field.name, UNDEFINED)
            if field.optional:
                if subvalue is UNDEFINED or subvalue is None:
                    types["boolean"].write(False, data)
                    continue
                types["boolean"].write(True, data)
            if not field.array:
                field.type.write(subvalue, data, subpath)
            else:
                self._write_array(subvalue, data, subpath, field.type)

    def _write_array(self, value, data, path, type):
        if not isinstance(value, (list, tuple)):
            raise TypeError("Expected an Array at " + path)
        types["uint"].write(len(value), data)
        for index, item in enumerate(value):
            type.write(item, data, path + "." + str(index))

    def read(self, state):
        if self.type == TYPE["ARRAY"]:
            return self._read_array(self.sub_type, state)
        if self.type != TYPE["OBJECT"]:
            return types[self.type].read(state)
        result = {}
        for field in self.fields:
            if field.optional:
                if not types["boolean"].read(state):
                    result[field.name] = None
                    continue
            if field.array:
                result[field.name] = self._read_array(field.type, state)
            else:
                result[field.name] = field.type.read(state)
        return result

    def _read_array(self, type, state):
        length = types["uint"].read(state)
        result = []
        for _ in range(length):
            before = state._offset
            result.append(type.read(state))
            if state._offset == before:
                raise ValueError("Array element type consumes no bytes")
        return result

    def get_hash(self):
        data = Data()

        def hash_type(node, array, optional):
            first = ord(node.type[0]) & 0x3F
            data.write_uint8(first | (0x80 if array else 0) | (0x40 if optional else 0))
            if node.type == TYPE["ARRAY"]:
                hash_type(node.sub_type, False, False)
            elif node.type == TYPE["OBJECT"]:
                types["uint"].write(len(node.fields), data)
                for field in node.fields:
                    hash_type(field.type, field.array, field.optional)

        hash_type(self, False, False)
        return data.to_buffer()

    getHash = get_hash


Type.types = types
