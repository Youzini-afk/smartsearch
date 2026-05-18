# npm/bin/

## Responsibility

Contains the npm executable shim for the `smart-search` binary. Its only job is to locate the package-managed Python virtualenv and delegate execution to the Python CLI module.

## Design

- **Thin process proxy**: `smart-search.js` contains no product logic; it forwards `process.argv.slice(2)` to `python -m smart_search.cli`.
- **Package-root-relative runtime**: resolves `packageRoot` as two directories above the bin file, then expects `.smart-search-python/` below it.
- **Cross-platform Python pathing**: uses `Scripts/python.exe` on Windows and `bin/python` elsewhere.
- **UTF-8 defaults**: sets `PYTHONIOENCODING=utf-8` and `PYTHONUTF8=1` unless already provided.
- **Stable runtime failure code**: exits `5` when the virtualenv Python cannot be found or child spawn fails.

## Flow

1. npm invokes `npm/bin/smart-search.js` via the `bin.smart-search` entry in `package.json`.
2. Script resolves `.smart-search-python` and validates the platform-specific Python executable exists.
3. Spawns `python -m smart_search.cli ...args` with inherited stdio and cwd from `INIT_CWD` or `process.cwd()`.
4. Forwards child exit code or signal to the wrapper process.

## Integration

- Created/maintained by `npm/scripts/postinstall.js`, which bootstraps `.smart-search-python/`.
- Tested by `npm/scripts/test.js` via help and UTF-8 smoke checks.
- Depends on `src/smart_search/cli.py` being installed in the virtualenv.
- Registered as the public npm command by `package.json`.
