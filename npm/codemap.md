# npm/

## Responsibility

Node.js wrapper layer that makes the Python `smart-search` CLI available as a global npm package (`@konbakuyomu/smart-search`). Handles packaging, installation lifecycle (venv bootstrap), CLI proxying, version synchronization, and release tooling.

## Design

- **Thin wrapper architecture**: No application logic lives here. Every file either proxies to the Python runtime or manipulates package metadata.
- **Embedded Python venv**: The postinstall script creates `.smart-search-python/` inside the package root and installs the bundled Python package into it. The CLI entry point then spawns that venv's interpreter.
- **Cross-platform awareness**: All path construction and Python discovery branch on `process.platform === "win32"` (e.g., `Scripts/python.exe` vs `bin/python`, `py -3` candidate on Windows).
- **Dual-package versioning**: `package.json` is the source of truth for version; `pyproject.toml` is kept in sync by scripts. This ensures a single `npm version` bump propagates everywhere.

## Flow

```
npm install -g @konbakuyomu/smart-search
  --> postinstall.js
      1. findPython() probes python3/python/py for >=3.10
      2. Creates .smart-search-python/ venv if missing
      3. pip install <packageRoot> into the venv

smart-search <args>
  --> bin/smart-search.js
      1. Locates venv python binary
      2. Spawns: python -m smart_search.cli <args>
      3. Inherits stdio; forwards exit code / signal

npm version <ver>
  --> sync-python-version.js (via "version" script)
      Reads package.json version -> writes pyproject.toml version

npm test
  --> test.js
      1. pip install -e .[dev] into venv
      2. pytest
      3. CLI --help smoke test
      4. UTF-8 round-trip: deep search with CJK args, parse JSON
      5. npm pack --dry-run
```

## Integration

- **Python package** (`src/smart_search/`): The actual CLI implementation. The npm layer installs it into a venv and delegates all command execution via `python -m smart_search.cli`.
- **package.json**: Declares `bin.smart-search` → `npm/bin/smart-search.js`; `scripts.postinstall` → `npm/scripts/postinstall.js`; `scripts.test` → `npm/scripts/test.js`; `scripts.version` → `npm/scripts/sync-python-version.js`.
- **pyproject.toml**: Python packaging config whose `version` field is kept in lockstep with `package.json` by sync/set-version scripts.
- **npm registry**: Published as `@konbakuyomu/smart-search`. The `files` whitelist in package.json includes `npm/`, `skills/`, `src/smart_search/`, and top-level metadata files.

## Modification Notes

- Adding a new npm lifecycle script requires an entry in `package.json.scripts` and a corresponding `.js` file in `npm/scripts/`.
- The venv directory name `.smart-search-python` is hardcoded in `postinstall.js`, `bin/smart-search.js`, and `test.js` — change it in all three if renaming.
- The Python version floor (`3.10`) is checked only in `postinstall.js` — if raised, update the probe string there.
- `resolve-prerelease-version.js` is the only script designed to be `require()`-able (exports `resolvePrereleaseVersion`). Others are side-effect-only entry points.
- Windows path differences (`Scripts/` vs `bin/`, `py -3` vs `python3`) must be preserved in any new script that touches the venv.
