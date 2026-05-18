# Repository Atlas: smartsearch

## Project Responsibility

Smart Search is a CLI-first, multi-provider web research/search tool for AI agents and terminal users, now with an optional cloud server layer. The runtime is a Python package (`smart_search`) distributed directly as a Python console script and through a thin npm wrapper (`@konbakuyomu/smart-search`). It provides live search, docs/library lookup, URL fetch/description, diagnostics, skill installation, offline Deep Research planning, authenticated HTTP tool APIs, an admin WebUI, and a persistent Deep Research task runner.

## System Entry Points

- `src/smart_search/cli.py`: Python CLI parser, command dispatch, output formatting, setup wizard, and process exit-code mapping.
- `src/smart_search/service.py`: Core orchestration for provider routing, fallback chains, validation, diagnostics, and Deep Research planning.
- `src/smart_search/server/app.py`: FastAPI app factory for authenticated cloud tool APIs, admin WebUI/API, task APIs, health, root redirect to admin, and optional MCP mounting.
- `src/smart_search/admin/routes.py`: Jinja2 admin console and JSON APIs for token, provider credential/config, usage, audit, system, and task management. Login page supports API key and password auth (SMART_SEARCH_ADMIN_PASSWORD / _PASSWORD_HASH). HTML pages redirect to /admin/login on unauthenticated access.
- `src/smart_search/tasks/worker.py`: DB-backed worker entry point (`smart-search-worker`) for persistent Deep Research task execution.
- `src/smart_search/config.py`: Runtime configuration singleton; reads env vars, config JSON, defaults, and exposes provider settings.
- `src/smart_search/providers/`: External API adapters for xAI Responses, OpenAI-compatible chat completions, Exa, Context7, and Zhipu.
- `npm/bin/smart-search.js`: npm executable that launches `python -m smart_search.cli` from the package-managed virtualenv.
- `package.json`: npm package metadata, bin registration, lifecycle scripts, publish whitelist, and version source of truth.
- `pyproject.toml`: Python package metadata, dependencies, package data, and console scripts (`smart-search`, `smart-search-worker`).
- `Dockerfile`: Container entry point for Zeabur/container deployments; runs the FastAPI app on `${PORT:-8000}`.
- `.dockerignore`: Excludes local envs, caches, node modules, agent metadata, logs, and SQLite files from container builds.

## Runtime Model

1. User installs the npm package or Python package.
2. npm installs create `.smart-search-python/` under the package root and install the local Python package into that virtualenv.
3. The `smart-search` command resolves to either the Python console script or `npm/bin/smart-search.js`.
4. CLI arguments are parsed by `cli.py`, then dispatched to async service functions.
5. `service.py` reads config, validates required capabilities, builds providers, applies intent routing and fallback, and returns structured results.
6. `cli.py` renders output as JSON, markdown, or compact content and maps failures to stable exit codes.

## Cloud Runtime Model

1. `create_app()` initializes the SQLAlchemy-backed cloud schema (SQLite default, PostgreSQL optional) and exposes `/health`, `/api/tools/*`, `/api/tasks/*`, and `/admin/*`.
2. Bearer tokens are verified from the `api_tokens` table; scopes gate tool, deep-task, and admin operations.
3. Provider credentials are encrypted in the database and can be managed/revealed through the admin console; MCP/API access tokens are hash-verified and only displayed once on creation.
4. Tool HTTP endpoints record `tool_invocations` and `audit_events` with sanitized metadata.
5. Deep Research cloud execution is task-based: `/api/tasks/deep_start` creates a `task_run` + DAG nodes, and `smart-search-worker` processes queued tasks asynchronously.

## Directory Map

| Directory | Responsibility Summary | Detailed Map |
|---|---|---|
| `src/` | Python source root containing the installable `smart_search` package. | [View Map](src/codemap.md) |
| `src/smart_search/` | Core CLI application: parsing, orchestration, configuration, source extraction, skill installation, logging, and utilities. | [View Map](src/smart_search/codemap.md) |
| `src/smart_search/providers/` | Provider abstraction layer and concrete external API adapters. | [View Map](src/smart_search/providers/codemap.md) |
| `src/smart_search/server/` | FastAPI cloud server, authenticated HTTP tool API, task API, and optional MCP integration. | See `src/smart_search/codemap.md`. |
| `src/smart_search/admin/` | Jinja2 admin WebUI/API for API keys, provider credentials/configs, usage, audit, system, and tasks. | See `src/smart_search/codemap.md`. |
| `src/smart_search/storage/` | SQLAlchemy models/repositories for cloud auth, credentials, usage, audit, and task state. | See `src/smart_search/codemap.md`. |
| `src/smart_search/tasks/` | DB-backed task queue, Deep Research DAG builder, and worker process. | See `src/smart_search/codemap.md`. |
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
- Cloud mode must avoid global per-user state: authenticate each request, construct a request/task context, keep tenant IDs on all DB reads, and never log raw Authorization/provider secrets.
- Server tool endpoints currently adapt the existing service layer; DB-backed provider credentials are available for management/resolution and should be wired through provider-injection seams before claiming fully tenant-scoped provider execution.
- User-facing output/docs are bilingual in places, so CLI/help/docs changes may need English and Chinese updates.

## Recommended Modification Entry Points

- Search behavior or routing: start with `src/smart_search/service.py`, then update `tests/test_service.py`.
- CLI commands/flags/output: start with `src/smart_search/cli.py`, then update `tests/test_cli.py`.
- New provider: add adapter under `src/smart_search/providers/`, wire config in `config.py`, route in `service.py`, and add provider/service tests.
- Source/citation formatting: edit `src/smart_search/sources.py` and `tests/test_sources.py`.
- Deep Research behavior: edit the offline planner in `service.py`; ensure tests preserve the no-live-provider-call expectation.
- Cloud server/admin behavior: edit `src/smart_search/server/`, `src/smart_search/admin/`, `src/smart_search/storage/`, and corresponding `tests/test_server_tools.py`, `tests/test_admin_webui.py`, `tests/test_tasks.py`.
- Persistent Deep Research tasks: edit `src/smart_search/tasks/` and task models/repositories; `smart-search-worker` processes queued DB tasks.
- Install/release behavior: inspect `package.json`, `pyproject.toml`, `npm/bin/smart-search.js`, `npm/scripts/`, `.github/workflows/publish-npm.yml`, and `tests/test_release_workflow.py`.
