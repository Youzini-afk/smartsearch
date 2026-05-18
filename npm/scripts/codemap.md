# npm/scripts/

## Responsibility

Lifecycle and tooling scripts invoked by npm (`postinstall`, `test`, `version`) and ad-hoc release commands (`set-version`, `sync:python-version`, prerelease resolution). No application runtime code — these run at install/test/publish time only.

## Design

| Script | Purpose | Side-effect-only | Exportable |
|---|---|---|---|
| `postinstall.js` | Bootstrap Python venv + install package on `npm install` | Yes | No |
| `test.js` | Integration test runner (pytest + CLI smoke + pack) | Yes | No |
| `set-package-version.js` | One-shot: set version in package.json, lock, pyproject.toml | Yes | No |
| `sync-python-version.js` | One-way sync: package.json version → pyproject.toml | Yes | No |
| `resolve-prerelease-version.js` | Compute next prerelease version from npm registry | No | Yes (`resolvePrereleaseVersion`) |

Common patterns:
- **`packageRoot`**: Every script resolves the monorepo root as `path.resolve(__dirname, "..", "..")`.
- **`venvDir`**: Hardcoded `.smart-search-python` under package root (postinstall, test, bin all agree on this name).
- **`run()` / `capture()` helpers**: postinstall and test each define their own thin `spawnSync` wrappers with platform-appropriate defaults (`windowsHide`, `encoding`, `shell` on Win32).
- **Exit codes**: Non-zero on any failure; postinstall exits `1` (missing Python) or propagates child status; test propagates child exit; set-version exits `1` on missing arg/bad pyproject.

## Flow

### postinstall.js
```
findPython() → probe python3/python/py for >=3.10
  → if venv missing: python -m venv .smart-search-python
  → venv pip install <packageRoot>
```

### test.js
```
1. venv pip install -e .[dev]
2. venv pytest
3. node bin/smart-search.js --help (smoke test)
4. node bin/smart-search.js deep "深度搜索..." --format json → parse JSON, assert CJK preserved
5. npm pack --dry-run
```

### set-package-version.js
```
argv[2] → write version into package.json, package-lock.json, pyproject.toml
```

### sync-python-version.js
```
read package.json version → regex-replace ^version = ".*"$ in pyproject.toml
```

### resolve-prerelease-version.js
```
--package <name> --base <version> [--id beta] [--versions-json JSON]
  → query npm view <name> versions --json (or use --versions-json)
  → find highest <base>-<id>.N among published versions
  → also count legacy <base>-dev.* for backward compat
  → output next prerelease version string to stdout
```

## Integration

- **`package.json.scripts`**: `postinstall` → `postinstall.js`; `test` → `test.js`; `version` → `sync-python-version.js && git add …`; `set-version` → `set-package-version.js`; `sync:python-version` → `sync-python-version.js`.
- **`pyproject.toml`**: Written by `set-package-version.js` and `sync-python-version.js` using the regex `^version = ".*"$`.
- **`npm/bin/smart-search.js`**: Referenced by `test.js` for CLI smoke and UTF-8 round-trip tests.
- **npm registry**: Queried by `resolve-prerelease-version.js` via `npm view <pkg> versions --json`. Handles 404 (first publish) gracefully.
- **CI/release workflows**: `resolve-prerelease-version.js` is designed to be consumed both as CLI (`node … --package … --base …`) and as a library (`require(…).resolvePrereleaseVersion`).

## Modification Notes

- **Adding a new script**: Place it here, add the corresponding `package.json.scripts` entry, and follow the `packageRoot = path.resolve(__dirname, "..", "..")` convention.
- **Venv path**: The `.smart-search-python` name is duplicated across postinstall, test, and bin — do not change it in only one place.
- **Python version floor**: Hardcoded in `postinstall.js` probe (`sys.version_info >= (3, 10)`). Update if minimum Python changes.
- **Version regex in pyproject.toml**: Both `set-package-version.js` and `sync-python-version.js` use `^version = ".*"$` (multiline). If pyproject.toml formatting changes, both must be updated.
- **`resolve-prerelease-version.js` export**: The only script with `module.exports`. If adding shared utilities, follow this pattern rather than making other scripts exportable.
- **Test script dependencies**: `test.js` assumes the venv exists (runs `npm install` first). It also runs `npm pack --dry-run` which requires `npm_execpath` or `npm` on PATH.
- **Windows compatibility**: postinstall and test use `windowsHide: true`. The `pythonCandidates()` function in postinstall provides Windows-specific `py -3` fallback. Any new script spawning processes must preserve these patterns.
