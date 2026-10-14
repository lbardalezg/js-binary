// Generates cross-compatibility fixtures for a Python port of `js-binary`.
//
// It uses the ORIGINAL npm library `js-binary@1.2.0` (installed locally in
// tools/node_modules) to encode/decode a curated + seeded-random set of cases
// and writes tests/fixtures/conformance.json in a deterministic, tagged form.
//
// Determinism: no Math.random / Date.now / wall clock is used anywhere; the
// random sweeps use a fixed-seed LCG. Running this file twice produces a
// byte-identical output file.
//
// Tagged value format (recursive). A JSON object is a tag ONLY if it has a
// "$type" key, otherwise it is a plain object:
//   Buffer   -> {"$type":"buffer","hex":"<lowercase hex>"}
//   Date     -> {"$type":"date","ms":<integer ms>}
//   RegExp   -> {"$type":"regex","source":"<source>","flags":"<g|i|m subset in .flags order>"}
//   oid      -> {"$type":"oid","hex":"<24 hex, case preserved>"}
//   undefined-> {"$type":"undefined"}
//   null     -> null
//   boolean  -> boolean
//   number   -> number                       (finite, not negative zero)
//   string   -> string                       (not a 24-char hex string)
//   Array    -> [tagged...]
//   object   -> { key: tagged }
// JSON cannot represent NaN/Infinity/-Infinity/-0, so those floats use the
// minimal extension {"$type":"number","value":"NaN"|"Infinity"|"-Infinity"|"-0"}.

import { createRequire } from 'node:module'
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const jsBinary = require('js-binary')
const pkg = require('js-binary/package.json')
const { Type } = jsBinary

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const OUT_PATH = join(ROOT, 'tests', 'fixtures', 'conformance.json')

// ---------------------------------------------------------------------------
// Tagging helpers
// ---------------------------------------------------------------------------

const HEX24 = /^[0-9a-fA-F]{24}$/

function numberToTagged(n) {
	if (Number.isNaN(n)) return { $type: 'number', value: 'NaN' }
	if (n === Infinity) return { $type: 'number', value: 'Infinity' }
	if (n === -Infinity) return { $type: 'number', value: '-Infinity' }
	if (Object.is(n, -0)) return { $type: 'number', value: '-0' }
	return n
}

function regexFlags(r) {
	let f = ''
	if (r.global) f += 'g'
	if (r.ignoreCase) f += 'i'
	if (r.multiline) f += 'm'
	return f
}

// real JS value -> tagged form
function toTagged(v) {
	if (v === undefined) return { $type: 'undefined' }
	if (v === null) return null

	const t = typeof v
	if (t === 'boolean') return v
	if (t === 'number') return numberToTagged(v)
	if (t === 'string') {
		if (HEX24.test(v)) return { $type: 'oid', hex: v }
		return v
	}

	if (Buffer.isBuffer(v)) return { $type: 'buffer', hex: v.toString('hex') }
	if (v instanceof Date) return { $type: 'date', ms: v.getTime() }
	if (v instanceof RegExp) return { $type: 'regex', source: v.source, flags: regexFlags(v) }

	if (Array.isArray(v)) return v.map(toTagged)

	if (t === 'object') {
		const out = {}
		for (const k of Object.keys(v)) out[k] = toTagged(v[k])
		return out
	}

	throw new Error('Cannot tag value of type ' + t)
}

// tagged form -> real JS value (real Buffer/Date/RegExp instances)
function fromTagged(t) {
	if (t === null) return null
	if (Array.isArray(t)) return t.map(fromTagged)

	if (t && typeof t === 'object' && typeof t.$type === 'string') {
		switch (t.$type) {
		case 'undefined': return undefined
		case 'buffer': return Buffer.from(t.hex, 'hex')
		case 'date': return new Date(t.ms)
		case 'regex': return new RegExp(t.source, t.flags)
		case 'oid': return t.hex
		case 'number': return specialNumber(t.value)
		default: throw new Error('Unknown tag: ' + t.$type)
		}
	}

	if (t && typeof t === 'object') {
		const out = {}
		for (const k of Object.keys(t)) out[k] = fromTagged(t[k])
		return out
	}

	// number, string, boolean
	return t
}

function specialNumber(value) {
	switch (value) {
	case 'NaN': return NaN
	case 'Infinity': return Infinity
	case '-Infinity': return -Infinity
	case '-0': return -0
	default: throw new Error('Unknown special number: ' + value)
	}
}

// ---------------------------------------------------------------------------
// Seeded deterministic random generators (LCG, never Math.random)
// ---------------------------------------------------------------------------

function makeLcg(seed) {
	let state = seed >>> 0
	return function next() {
		state = (Math.imul(state, 1664525) + 1013904223) >>> 0
		return state
	}
}

function randomUint53(next) {
	const hi = next() % 0x4000000 // 2^26
	const lo = next() % 0x8000000 // 2^27
	return hi * 0x8000000 + lo // in [0, 2^53 - 1]
}

function randomInt53(next) {
	const u = randomUint53(next)
	if (u !== 0 && next() % 2 === 1) return -u
	return u
}

function randomFiniteFloat(next) {
	const sign = next() % 2 === 0 ? 1 : -1
	const mant = next() / 0x100000000 // [0, 1)
	const exp = (next() % 601) - 300 // [-300, 300]
	let v = sign * mant * Math.pow(10, exp)
	if (!Number.isFinite(v)) v = 0
	return v
}

const STRING_ALPHABET = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,!?-'

function randomString(next) {
	const len = next() % 21
	let s = ''
	for (let i = 0; i < len; i++) s += STRING_ALPHABET[next() % STRING_ALPHABET.length]
	// Never emit a 24-char hex string: it would be tagged as an oid.
	if (HEX24.test(s)) s += 'z'
	return s
}

function randomObjectsArray(next, n) {
	const arr = []
	for (let i = 0; i < n; i++) {
		arr.push({ id: randomUint53(next), name: randomString(next), score: randomFiniteFloat(next) })
	}
	return arr
}

// ---------------------------------------------------------------------------
// Case collection
// ---------------------------------------------------------------------------

const cases = []
const skipped = []
const seenNames = new Set()

function addCase(name, schema, realValue) {
	if (seenNames.has(name)) throw new Error('Duplicate case name: ' + name)
	seenNames.add(name)

	// Build the encoding input the spec-mandated way: real -> tagged -> real.
	const taggedInput = toTagged(realValue)
	const encodeValue = fromTagged(taggedInput)

	let type
	let encoded
	let decodedReal
	try {
		type = new Type(schema)
		encoded = type.encode(encodeValue)
		decodedReal = type.decode(Buffer.from(encoded))
	} catch (err) {
		skipped.push({ name, schema, error: err && err.message ? err.message : String(err) })
		return
	}

	let hash
	try {
		hash = type.getHash()
	} catch (err) {
		skipped.push({ name, schema, error: 'getHash: ' + (err && err.message ? err.message : String(err)) })
		return
	}

	cases.push({
		name,
		schema,
		value: toTagged(encodeValue),
		encoded: encoded.toString('hex'),
		decoded: toTagged(decodedReal),
		hash: hash.toString('hex'),
	})
}

// --- scalar types -----------------------------------------------------------

addCase('scalar/uint', 'uint', 42)
addCase('scalar/int', 'int', -42)
addCase('scalar/float', 'float', 1.5)
addCase('scalar/string', 'string', 'hello')
addCase('scalar/buffer', 'Buffer', Buffer.from([0x00, 0x01, 0xfe, 0xff]))
addCase('scalar/boolean', 'boolean', true)
addCase('scalar/json', 'json', { a: 1, b: [true, null, 'x'] })
addCase('scalar/oid', 'oid', '0123456789abcdefabcdef01')
addCase('scalar/regex', 'regex', /ab+c/gi)
addCase('scalar/date', 'date', new Date(1700000000123))

// --- uint boundaries --------------------------------------------------------

const UINT_BOUNDS = [
	0, 1, 127, 128, 16383, 16384,
	536870911, 536870912,
	9007199254740991, 9007199254740992,
]
UINT_BOUNDS.forEach((v, i) => addCase('uint/bound/' + i + '_' + v, 'uint', v))
addCase('uint/bound-sweep', ['uint'], UINT_BOUNDS.slice())

// --- int boundaries ---------------------------------------------------------

const INT_BOUNDS = [
	-64, 63, -65, 64, -8192, 8191, -8193, 8192,
	-268435456, 268435455, -268435457, 268435456,
	-9007199254740992, 9007199254740992,
]
INT_BOUNDS.forEach((v, i) => addCase('int/bound/' + i + '_' + String(v).replace('-', 'neg'), 'int', v))
addCase('int/bound-sweep', ['int'], INT_BOUNDS.slice())

// --- float values -----------------------------------------------------------

const FLOATS = [
	['zero', 0],
	['neg-zero', -0],
	['0.1', 0.1],
	['neg-0.1', -0.1],
	['1.5', 1.5],
	['1e21', 1e21],
	['1e-7', 1e-7],
	['1e-6', 1e-6],
	['1e20', 1e20],
	['pi', Math.PI],
	['NaN', NaN],
	['Infinity', Infinity],
	['-Infinity', -Infinity],
	['max-value', Number.MAX_VALUE],
	['min-value', Number.MIN_VALUE],
	['2^53', 9007199254740992],
]
FLOATS.forEach(([label, v]) => addCase('float/' + label, 'float', v))

// --- strings ----------------------------------------------------------------

addCase('string/empty', 'string', '')
addCase('string/ascii', 'string', 'The quick brown fox jumps over the lazy dog')
addCase('string/accented', 'string', 'caf\u00e9 na\u00efve r\u00e9sum\u00e9 se\u00f1or')
addCase('string/emoji-surrogate-pair', 'string', 'emoji: \u{1F600}\u{1F680}\u{1F1E7}\u{1F1F7}')
addCase('string/cjk', 'string', '\u4f60\u597d\u4e16\u754c \u3053\u3093\u306b\u3061\u306f \uc548\ub155\ud558\uc138\uc694')

// --- buffers ----------------------------------------------------------------

addCase('buffer/empty', 'Buffer', Buffer.alloc(0))
addCase('buffer/single-zero', 'Buffer', Buffer.from([0x00]))
addCase('buffer/all-bytes', 'Buffer', Buffer.from(Array.from({ length: 256 }, (_, i) => i)))
addCase('buffer/utf8-bytes', 'Buffer', Buffer.from('h\u00e9llo \ud83d\ude00', 'utf8'))

// --- booleans ---------------------------------------------------------------

addCase('boolean/true', 'boolean', true)
addCase('boolean/false', 'boolean', false)

// --- json -------------------------------------------------------------------

addCase('json/scalar-number', 'json', 3.25)
addCase('json/scalar-string', 'json', 'plain')
addCase('json/scalar-null', 'json', null)
addCase('json/scalar-array', 'json', [1, 'two', false, null])
addCase('json/empty-object', 'json', {})
addCase('json/empty-array', 'json', [])
addCase('json/nested', 'json', {
	nulls: [null, null],
	unicode: 'h\u00e9llo \u4f60\u597d \ud83d\ude00',
	one: 1.0,
	big: 1e21,
	negzero: -0,
	flags: [true, false],
	nested: { a: { b: [1, 2, { c: 3.5 }] } },
})
addCase('json/object-wrapper', { j: 'json' }, { j: { plain: 'object', list: [1, 2, 3], deep: { k: null } } })

// --- oid --------------------------------------------------------------------

addCase('oid/lowercase', 'oid', '0123456789abcdefabcdef01')
addCase('oid/uppercase', 'oid', '0123456789ABCDEFABCDEF01')
addCase('oid/all-zero', 'oid', '000000000000000000000000')
addCase('oid/all-f', 'oid', 'ffffffffffffffffffffffff')

// --- regex ------------------------------------------------------------------

const REGEX_SOURCES = ['a(b+)c[0-9]', '^\\d+\\.\\d+$', '[/\\\\]', '(?:x|y)*', 'foo|bar', '']
const REGEX_FLAGS = ['', 'g', 'i', 'm', 'gi', 'gim']
let regexN = 0
for (const src of REGEX_SOURCES) {
	for (const fl of REGEX_FLAGS) {
		addCase('regex/' + regexN + '_flags-' + (fl || 'none'), 'regex', new RegExp(src, fl))
		regexN++
	}
}

// --- date -------------------------------------------------------------------

addCase('date/epoch', 'date', new Date(0))
addCase('date/with-ms', 'date', new Date(1700000000123))
addCase('date/large-valid', 'date', new Date(8640000000000000))

// --- structural / compound --------------------------------------------------

addCase('object/nested-simple', { a: { b: { c: 'int' } } }, { a: { b: { c: 7 } } })
addCase('object/nested-deep', { a: { b: { c: { d: { e: ['int'] } } } } }, { a: { b: { c: { d: { e: [1, 2, 3] } } } } })

const OPT_SCHEMA = { a: 'int', 'b?': 'string' }
addCase('optional/present-value', OPT_SCHEMA, { a: 1, b: 'present' })
addCase('optional/present-null', OPT_SCHEMA, { a: 1, b: null })
addCase('optional/absent', OPT_SCHEMA, { a: 1 })
addCase('optional/absent-undefined', OPT_SCHEMA, { a: 1, b: undefined })
addCase('optional/present-empty-string', { 'b?': 'string' }, { b: '' })
addCase('optional/present-zero', { 'n?': 'uint' }, { n: 0 })

const OPTARR_SCHEMA = { n: 'uint', 'items?': ['int'] }
addCase('optional/array-present', OPTARR_SCHEMA, { n: 3, items: [1, 2, 3] })
addCase('optional/array-null', OPTARR_SCHEMA, { n: 0, items: null })
addCase('optional/array-absent', OPTARR_SCHEMA, { n: 0 })

addCase('array/of-int', { list: ['int'] }, { list: [-1, 0, 1, 2] })
addCase('array/of-string', { list: ['string'] }, { list: ['a', '', 'c'] })
addCase('array/of-object', { items: [{ x: 'int', y: 'string' }] }, { items: [{ x: 1, y: 'one' }, { x: 2, y: 'two' }] })
addCase('array/empty', { list: ['int'] }, { list: [] })
addCase('array/top-level-int', ['int'], [5, -5, 0])
addCase('array/top-level-string', ['string'], ['x', 'y'])
addCase('array/top-level-buffer', ['Buffer'], [Buffer.from([1, 2]), Buffer.alloc(0)])

const COMBO_SCHEMA = {
	u: 'uint',
	i: 'int',
	f: 'float',
	s: 'string',
	b: 'Buffer',
	bool: 'boolean',
	j: 'json',
	o: 'oid',
	re: 'regex',
	d: 'date',
	'optStr?': 'string',
	nums: ['int'],
	recs: [{ k: 'string', v: 'float' }],
	'optArr?': ['uint'],
}
const comboValue = {
	u: 12345,
	i: -54321,
	f: 3.5,
	s: 'combo',
	b: Buffer.from([0xde, 0xad, 0xbe, 0xef]),
	bool: false,
	j: { nested: [1, null, 'x'], z: 1e21 },
	o: '0123456789abcdefabcdef01',
	re: /x(y)?/gim,
	d: new Date(1700000000123),
	nums: [1, -2, 3],
	recs: [{ k: 'a', v: 0.5 }, { k: 'b', v: -1e-7 }],
}
addCase('combined/all-types', COMBO_SCHEMA, comboValue)
addCase('combined/all-types-optional-present', COMBO_SCHEMA, Object.assign({}, comboValue, { optStr: 'opt', optArr: [7, 8] }))
addCase('combined/all-types-optional-undefined', COMBO_SCHEMA, Object.assign({}, comboValue, { optStr: undefined, optArr: undefined }))

// --- seeded random sweeps (deterministic) -----------------------------------

const rng = makeLcg(0x12345678)

const randUints = []
for (let i = 0; i < 300; i++) randUints.push(randomUint53(rng))
addCase('random/uint-300', ['uint'], randUints)

const randInts = []
for (let i = 0; i < 300; i++) randInts.push(randomInt53(rng))
addCase('random/int-300', ['int'], randInts)

const randFloats = []
for (let i = 0; i < 200; i++) randFloats.push(randomFiniteFloat(rng))
addCase('random/float-200', ['float'], randFloats)

const randStrings = []
for (let i = 0; i < 100; i++) randStrings.push(randomString(rng))
addCase('random/string-100', ['string'], randStrings)

const RAND_OBJ_SCHEMA = [{ id: 'uint', name: 'string', score: 'float' }]
addCase('random/objects-1', RAND_OBJ_SCHEMA, randomObjectsArray(rng, 5 + (rng() % 16)))
addCase('random/objects-2', RAND_OBJ_SCHEMA, randomObjectsArray(rng, 5 + (rng() % 16)))

// ---------------------------------------------------------------------------
// Write output
// ---------------------------------------------------------------------------

const fixture = {
	meta: { js_binary_version: pkg.version, node: process.version },
	cases,
}

mkdirSync(dirname(OUT_PATH), { recursive: true })
writeFileSync(OUT_PATH, JSON.stringify(fixture, null, 2) + '\n', 'utf8')

console.log('js-binary ' + pkg.version + ' on ' + process.version)
console.log('Wrote ' + cases.length + ' cases to ' + OUT_PATH)
if (skipped.length) {
	console.log('Skipped ' + skipped.length + ' case(s):')
	for (const s of skipped) console.log('  - ' + s.name + ': ' + s.error)
}
