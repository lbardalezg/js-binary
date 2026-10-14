# AGENTS.md

Short notes for future contributors and agents working on this repository.

## Project layout

- `src/js_binary/` — the library itself (src layout). Do not place tests or tooling here.
- `tests/` — pytest suite (`testpaths = ["tests"]` in `pyproject.toml`).
- `tools/` — developer-only Node harness that regenerates the cross-compatibility
  fixtures. Its `node_modules/` is git-ignored and installed on demand; library
  users never need Node.

## Run tests

```sh
pip install -e ".[dev]"
pytest
```

## Regenerate cross-compat fixtures

The fixtures that verify byte-for-byte compatibility with the JavaScript library are
committed to the repository. Node is only needed to regenerate them (developer-only,
optional — not required to run the test suite or to use the library).

```sh
cmd /c "npm install"        # inside tools/ (installs the original js-binary from npm)
node tools/generate_fixtures.mjs
```

Run `npm install` from within `tools/` first so the harness can resolve the original
`js-binary` dependency.

## Notes

- Packaging is hatchling-based; see `pyproject.toml`.
- CI runs the test suite across Python 3.9–3.13; publishing to PyPI uses Trusted
  Publishing (OIDC) via `.github/workflows/publish.yml`.
