from js_binary import Data, Field, ReadState, Type, types

import pytest


def test_type_enum_and_types_export():
    assert Type.TYPE["UINT"] == "uint"
    assert Type.TYPE["ARRAY"] == "[array]"
    assert Type.TYPE["OBJECT"] == "{object}"
    assert set(types) == {"uint", "int", "float", "string", "Buffer", "boolean",
                          "json", "oid", "regex", "date"}
    assert Type.types is types


def test_unknown_basic_type():
    with pytest.raises(TypeError) as excinfo:
        Type("foo")
    assert str(excinfo.value) == "Unknown basic type: foo"


def test_invalid_array_type():
    with pytest.raises(TypeError) as excinfo:
        Type([])
    assert str(excinfo.value) == "Invalid array type, it must have exactly one element"


@pytest.mark.parametrize("value,shown", [(5, "5"), (None, "null")])
def test_invalid_type(value, shown):
    with pytest.raises(TypeError) as excinfo:
        Type(value)
    assert str(excinfo.value) == "Invalid type: " + shown


def test_array_of_ints_roundtrip():
    schema = Type(["int"])
    assert schema.decode(schema.encode([1, -2, 3])) == [1, -2, 3]
    assert schema.decode(schema.encode([])) == []


def test_array_encoding_uses_uint_length():
    assert Type(["uint"]).encode([1, 2, 3]).hex() == "03010203"


def test_nested_object_roundtrip():
    schema = Type({"a": {"b": "int", "d": {"e": "int"}}})
    value = {"a": {"b": 1, "d": {"e": 2}}}
    assert schema.decode(schema.encode(value)) == value


def test_optional_fields():
    schema = Type({"a": "int", "b?": "int", "c?": {"d": "int"}})
    assert schema.decode(schema.encode({"a": 1})) == {"a": 1, "b": None, "c": None}
    full = {"a": 1, "b": 2, "c": {"d": 3}}
    assert schema.decode(schema.encode(full)) == full


def test_optional_presence_flag_byte():
    schema = Type({"a?": "boolean"})
    assert schema.encode({"a": True}).hex() == "0101"
    assert schema.encode({"a": False}).hex() == "0100"


def test_missing_optional_none_and_absent_are_equal():
    schema = Type({"a?": "int"})
    assert schema.encode({}) == schema.encode({"a": None})


def test_array_field_and_array_of_objects():
    schema = Type({"items": [{"v": "int", "f": "string"}]})
    value = {"items": [{"v": 1, "f": "a"}, {"v": 2, "f": "b"}]}
    assert schema.decode(schema.encode(value)) == value


def test_expected_object_error():
    with pytest.raises(TypeError) as excinfo:
        Type({"a": "int"}).encode(5)
    assert str(excinfo.value) == "Expected an object at "


def test_expected_array_error():
    with pytest.raises(TypeError) as excinfo:
        Type(["int"]).encode(5)
    assert str(excinfo.value) == "Expected an Array at "


def test_missing_required_field_message():
    with pytest.raises(TypeError) as excinfo:
        Type({"a": "uint"}).encode({})
    assert str(excinfo.value) == "Expected unsigned integer at a, got undefined"


def test_nested_error_path():
    with pytest.raises(TypeError) as excinfo:
        Type({"a": {"b": "uint"}}).encode({"a": {"b": -1}})
    assert str(excinfo.value) == "Expected unsigned integer at a.b, got -1"


def test_array_error_path():
    with pytest.raises(TypeError) as excinfo:
        Type(["uint"]).encode([1, -1])
    assert str(excinfo.value) == "Expected unsigned integer at .1, got -1"


def test_array_of_object_error_path():
    with pytest.raises(TypeError) as excinfo:
        Type([{"a": "uint"}]).encode([{"a": -1}])
    assert str(excinfo.value) == "Expected unsigned integer at .0.a, got -1"


@pytest.mark.parametrize("schema,expected", [
    ("uint", "35"),
    ("int", "29"),
    ("float", "26"),
    ("string", "33"),
    ("Buffer", "02"),
    ("boolean", "22"),
    ("json", "2a"),
    ("oid", "2f"),
    ("regex", "32"),
    ("date", "24"),
    (["int"], "1b29"),
])
def test_get_hash(schema, expected):
    assert Type(schema).get_hash().hex() == expected
    assert Type(schema).getHash().hex() == expected


def test_get_hash_ignores_field_names():
    assert Type({"a": "int"}).get_hash() == Type({"b": "int"}).get_hash()


def test_get_hash_distinguishes_types():
    assert Type({"a": "int"}).get_hash() != Type({"a": "uint"}).get_hash()


def test_field_attributes():
    field = Field("name?", ["int"])
    assert field.name == "name"
    assert field.optional is True
    assert field.array is True
    assert isinstance(field.type, Type)


def test_data_and_read_state_low_level():
    data = Data()
    data.write_uint8(0x7f)
    data.writeUInt16(0x8080)
    data.write_uint32(0xC0004000)
    data.write_double(1.5)
    assert data.to_buffer().hex() == "7f8080c0004000" + "3ff8000000000000"

    state = ReadState(bytes.fromhex("7f8080c0004000"))
    assert state.read_uint8() == 0x7F
    assert state.readUInt16() == 0x8080
    assert state.read_uint32() == 0xC0004000
    assert state.has_ended()


def test_low_level_write_and_read():
    schema = Type({"a": "uint", "b": "string"})
    data = Data()
    schema.write({"a": 7, "b": "hi"}, data, "")
    assert schema.read(ReadState(data.to_buffer())) == {"a": 7, "b": "hi"}


def test_top_level_scalar_type_write_path_is_empty():
    with pytest.raises(TypeError) as excinfo:
        Type("uint").write(-1, Data(), "")
    assert str(excinfo.value) == "Expected unsigned integer at , got -1"


def test_field_order_matches_js_object_keys():
    schema = Type({"b": "int", "2": "int", "1": "int"})
    assert [field.name for field in schema.fields] == ["1", "2", "b"]
    assert schema.encode({"b": 1, "2": 2, "1": 3}).hex() == "030201"


def test_decode_rejects_non_buffer():
    with pytest.raises(TypeError) as excinfo:
        Type("boolean").decode(5)
    assert str(excinfo.value) == "Expected a bytes-like buffer, got 5"


def test_array_of_zero_byte_elements_is_rejected():
    data = Data()
    types["uint"].write(3, data)
    with pytest.raises(ValueError) as excinfo:
        Type([{}]).decode(data.to_buffer())
    assert str(excinfo.value) == "Array element type consumes no bytes"
