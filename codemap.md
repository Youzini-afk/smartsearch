# Repository Atlas: smartsearch

## Project Responsibility

Smart Search is a CLI-first, multi-provider web research/search tool for AI agents and terminal users. The runtime is a Python package (`smart_search`) distributed directly as a Python console script and through a thin npm wrapper (`@konbakuyomu/smart-search`). It provides live search, docs/library lookup, URL fetch/description, diagnostics, skill installation, and offline Deep Research planning.

## System Entry Points

- `src/smart_search/cli.py`: Python CLI parser, command dispatch, output formatting, setup wizard, and process exit-code mapping.
- `src/smart_search/service.py`: Core orchestration for provider routing, fallback chains, validation, diagnostics, and Deep Research planning.
- `src/smart_search/config.py`: Runtime configuration singleton; reads env vars, config JSON, defaults, and exposes provider settings.
- `src/smart_search/providers/`: External API adapters for xAI Responses, OpenAI-compatible chat completions, Exa, Context7, and Zhipu.
- `npm/bin/smart-search.js`: npm executable that launches `python -m smart_search.cli` from the package-managed virtualenv.
- `package.json`: npm package metadata, bin registration, lifecycle scripts, publish whitelist, and version source of truth.
- `pyproject.toml`: Python package metadata, dependencies, package data, and `smart-search = smart_search.cli:main` console script.

## Runtime Model

1. User installs the npm package or Python package.
2. npm installs create `.smart-search-python/` under the package root and install the local Python package into that virtualenv.
3. The `smart-search` command resolves to either the Python console script or `npm/bin/smart-search.js`.
4. CLI arguments are parsed by `cli.py`, then dispatched to async service functions.
5. `service.py` reads config, validates required capabilities, builds providers, applies intent routing and fallback, and returns structured results.
6. `cli.py` renders output as JSON, markdown, or compact content and maps failures to stable exit codes.

## Directory Map

| Directory | Responsibility Summary | Detailed Map |
|---|---|---|
| `src/` | Python source root containing the installable `smart_search` package. | [View Map](src/codemap.md) |
| `src/smart_search/` | Core CLI application: parsing, orchestration, configuration, source extraction, skill installation, logging, and utilities. | [View Map](src/smart_search/codemap.md) |
| `src/smart_search/providers/` | Provider abstraction layer and concrete external API adapters. | [View Map](src/smart_search/providers/codemap.md) |
| `npm/` | Node.js wrapper/distribution layer that bootstraps Python and proxies CLI execution. | [View Map](npm/codemap.md) |
| `npm/bin/` | npm executable shim for launching the Python CLI from the embedded virtualenv. | [View Map](npm/bin/codemap.md) |
| `npm/scripts/` | npm lifecycle, test, version-sync, and prerelease helper scripts. | [View Map](npm/scripts/codemap.md) |
| `tests/` | Pytest suite covering CLI, service orchestration, provider behavior, config overrides, regression, smoke, and release workflow. | Tests are intentionally excluded from codemap generation. |
| `skills/` | Source skill assets mirrored into package data for AI-agent integration. | Packaged via `pyproject.toml` and installed by `skill_installer.py`. |

## Key Architectural Constraints

- `service.py` is the highest-risk modification point: it combines routing, provider fallback, diagnostics, smoke behavior, and Deep Research planning.
- Provider contracts are loose: the abstract base suggests `List[SearchResult]`, while several concrete providers return JSON strings or provider-specific payloads.
- Fallback semantics are product behavior. Capability-specific chains should not be changed casually.
- Minimum profile validation intentionally fails closed unless configured off; defaults require main search, docs search, and web fetch capability.
- Extra sources are discovery candidates and should not be silently promoted to verified evidence.
- npm and Python packaging are coupled; keep `package.json`, `package-lock.json`, `pyproject.toml`, npm scripts, and release workflow in sync.
- User-facing output/docs are bilingual in places, so CLI/help/docs changes may need English and Chinese updates.

## Recommended Modification Entry Points

- Search behavior or routing: start with `src/smart_search/service.py`, then update `tests/test_service.py`.
- CLI commands/flags/output: start with `src/smart_search/cli.py`, then update `tests/test_cli.py`.
- New provider: add adapter under `src/smart_search/providers/`, wire config in `config.py`, route in `service.py`, and add provider/service tests.
- Source/citation formatting: edit `src/smart_search/sources.py` and `tests/test_sources.py`.
- Deep Research behavior: edit the offline planner in `service.py`; ensure tests preserve the no-live-provider-call expectation.
- Install/release behavior: inspect `package.json`, `pyproject.toml`, `npm/bin/smart-search.js`, `npm/scripts/`, `.github/workflows/publish-npm.yml`, and `tests/test_release_workflow.py`.
