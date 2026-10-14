# js-binary (Python)

Encode/decode to js-binary's custom binary format: much more compact and faster than JSON/BSON.

This is an independent, **unofficial** Python port of the npm [`js-binary`](https://github.com/sitegui/js-binary) package **v1.2.0** (MIT), with **100% binary-format compatibility**. It is not affiliated with, sponsored by, or endorsed by the original author. The distribution name is `js-binary`; the import package is `js_binary`.

Like the original, it is analogous to `JSON.stringify` / `JSON.parse`, but encodes to a compact custom binary format. The format carries no type information, so you must define a schema to encode/decode. A nice side effect is free input validation against the schema. It is well suited to very regular data, like API input/output.

## Install

```sh
pip install js-binary
```

## Usage

```python
from js_binary import Type

user = {
    "name": {
        "first": "Guilherme",
        "last": "Souza",
    },
    "pass": bytes.fromhex("042697a30b2dafbdf91bf66bdacdcba8"),
    "creationDate": 1397251352504,  # 2014-04-11T21:22:32.504Z, milliseconds since epoch
    "active": True,
    "achievements": [3, 14, 15, 92, 65, 35],
}

schema = Type({
    "name": {
        "first": "string",
        "last": "string",
    },
    "pass": "Buffer",
    "creationDate": "date",
    "active": "boolean",
    "achievements": ["uint"],
    "optionalField?": "int",
})

encoded = schema.encode(user)

decoded = schema.decode(encoded)
```

## Available types

### Basic types

* `uint`: unsigned integer (between 0 and 2^53)
* `int`: signed integer (between -2^53 and 2^53)
* `float`: a 64-bit floating-point (the JavaScript number type)
* `string`: a utf-8 string
* `Buffer`: a byte buffer
* `boolean`: a boolean
* `json`: any data supported by the JSON format
* `oid`: a mongodb ObjectId (24-char hex string on decode)
* `regex`: a regular expression
* `date`: a date/time value

### Compound types

A compound type is an object with (optional) fields. Those fields may be arrays, but with the restriction that every element has the same data schema.

Examples:

* Nested fields: `{"a": {"b": "int", "d": {"e": "int"}}}`
* Optional fields: `{"a": "int", "b?": "int", "c?": {"d": "int"}}`
* Array fields: `{"a": ["int"]}`
* All together now: `{"a?": [{"b?": "int"}]}`

### Array type

An array type in which every element has the same data schema.

* Int array: `["int"]`
* Object array: `[{"v": "int", "f": "string"}]`

### Optional fields

Optional fields are named with a trailing `?`, for example `"optionalField?"`. The empty value is `None` (equivalent to JS `undefined` / `null`).

## Type mapping (JS -> Python)

| JS (`js-binary`) | Python                                              |
| ---------------- | --------------------------------------------------- |
| `Buffer`         | `bytes`                                             |
| `Date`           | `datetime.datetime` (UTC-aware on decode; encode accepts a `datetime` or int milliseconds) |
| `RegExp`         | `js_binary.Regex` (has `.source` and `.flags`)      |
| `oid`            | 24-char hex `str`                                   |
| object           | `dict`                                              |
| array            | `list`                                              |
| json             | native Python types                                 |
| boolean          | `bool`                                              |
| uint / int       | `int`                                               |
| float            | `float`                                             |

## API

Public names: `js_binary.Type`, `js_binary.Data`, `js_binary.Field`, `js_binary.ReadState`, `js_binary.types`, `js_binary.Regex`.

`Type` exposes the methods `encode`, `decode`, `write`, `read`, and `get_hash` (alias `getHash`), plus the class attribute `Type.TYPE`.

Low-level classes expose snake_case methods with camelCase aliases (for example `get_hash` / `getHash`) to ease porting from the JavaScript API.

## Notes / deviations

* An unknown basic type raises `TypeError('Unknown basic type: ...')`.
* `None` is the "empty" value for optional fields (equivalent to JS `undefined` / `null`).
* Reading past the end of a buffer raises `IndexError`.
* Error messages replicate the original library's messages.
* `date` decodes to a UTC-aware `datetime.datetime`. JavaScript dates span roughly ±8.64e15 ms, beyond Python's `datetime` range; such out-of-range values decode to an `int` of milliseconds instead (never lost), and can be re-encoded as-is.
* `regex` round-trips losslessly as `js_binary.Regex`. Decoding does not attempt to compile it with Python's `re`, since JS and Python regex syntaxes differ.
* Arrays whose element type consumes no bytes (e.g. `[{}]`) raise `ValueError('Array element type consumes no bytes')` on decode; otherwise the declared length could drive unbounded allocation from a tiny payload. The original only bounds this at 2^32 elements.
* `Type.decode` requires a bytes-like argument; any other type raises `TypeError`.

## License

MIT. See [LICENSE](LICENSE). This is an unofficial Python port; the original JavaScript project is [`sitegui/js-binary`](https://github.com/sitegui/js-binary) (MIT).
