# src/smart_search/

## Responsibility

Core package for Smart Search — a CLI-first, multi-provider search tool for AI agents with an optional cloud server runtime. Owns argument parsing, provider orchestration, configuration management, source extraction, output formatting, skill installation, health diagnostics, authenticated HTTP tool APIs, admin WebUI, encrypted provider credential storage, usage/audit records, and persistent Deep Research task execution.

## Design

**Singleton Config (`config.py`)** — `Config` is a process-wide singleton (`config = Config()`). Values resolve from env vars first, then `config.json` on disk, then hardcoded defaults. Secret masking (`_mask_api_key`) prevents credential leakage in output. Enum-validated properties (`validation_level`, `fallback_mode`, `minimum_profile`) raise `ValueError` on bad values. Config dir resolution supports `SMART_SEARCH_CONFIG_DIR` env override, Windows legacy path migration, and cwd fallback.

**Provider Layer (`providers/`)** — Each search provider implements a provider class (`XAIResponsesSearchProvider`, `OpenAICompatibleSearchProvider`, `ExaSearchProvider`, `ZhipuWebSearchProvider`, `Context7Provider`) with a `search()` method. Providers are instantiated per-request; no persistent state. The `service.py` module acts as the orchestrator, not the providers directory.

**Intent-Based Routing (`service.py`)** — Search queries are classified by intent signals (`docs_intent`, `zh_current_intent`, `fetch_intent`) which determine supplemental search paths. The routing decision is recorded in every result for traceability.

**Capability Gates (`service.py`)** — A "minimum profile" check (`standard` = main_search + docs_search + web_fetch) blocks search execution if any required capability lacks a configured provider. The `doctor` command validates this plus live connectivity.

**Fallback Chains** — Each capability has an ordered fallback chain (e.g., `main_search: xai-responses → openai-compatible`). The `--fallback off` flag disables fallback (first provider only). `provider_attempts` records every attempt for debugging.

**Source Extraction (`sources.py`)** — `split_answer_and_sources()` parses LLM output to separate answer text from citation sources. It handles markdown headings, `<details>` blocks, tail link blocks, function-call-style sources, and inline `[[N]](url)` citations. `sanitize_answer_text()` strips `<think>` blocks and leading AI policy refusals.

**Output Formatting (`cli.py`)** — Three render modes: `json` (raw data), `markdown` (rich tables/sections), `content` (compact plain text). All output is encoding-safe (`_stdout_safe`, `_json_stdout_safe`). Exit codes map error types: 0=ok, 2=parameter, 3=config, 4=network, 5=runtime.

**Skill Installer (`skill_installer.py`)** — Installs the bundled `smart-search-cli` skill into AI tool directories (`.codex/skills`, `.claude/skills`, etc.). Uses `importlib.resources` for packaged installs, falls back to filesystem search for dev installs.

**Logging (`logger.py`)** — Standard `logging.getLogger("smart_search")`. File logging is opt-in via `SMART_SEARCH_LOG_TO_FILE` or `SMART_SEARCH_DEBUG`. Daily log files under the configured `log_dir`.

**Cloud Foundation (`storage/`, `auth/`, `security/`, `runtime/`)** — SQLAlchemy models/repositories support SQLite and PostgreSQL deployments for tenants, users, API tokens, provider credentials/configs, tool usage, audit events, and task state. API tokens are HMAC-hashed; provider credentials are encrypted with `SMART_SEARCH_MASTER_KEY`; audit details are sanitized. `storage.db` reads `SMART_SEARCH_DATABASE_URL`, then Zeabur's `POSTGRES_CONNECTION_STRING`, then generic `DATABASE_URL`, and normalizes bare `postgresql://` / `postgres://` URLs to `postgresql+psycopg://`.

**Server Layer (`server/`)** — `create_app()` builds a FastAPI application with `/api/tools/*` endpoints, `/api/tasks/*` task endpoints, `/admin/*` mounted WebUI/API, `/health`, root redirect to admin, and optional MCP mounting behind `SMART_SEARCH_ENABLE_MCP=true`. Bearer auth is request-scoped and scope-gated. Container deployments should bind `0.0.0.0:${PORT:-8000}`.

**Admin Console (`admin/`)** — Productized Jinja2 console with sidebar layout, analytics dashboard, usage charts, separated provider credential management and dedicated capability configuration (`/admin/config`), token management, audit views, system status, and task controls. Login page supports API key and password auth (SMART_SEARCH_ADMIN_PASSWORD / _PASSWORD_HASH). HTML pages redirect to `/admin/login` on unauthenticated access; API endpoints return 401/403. Provider key reveal is POST-only, audited, and cache-disabled. i18n (`admin/i18n.py`) provides zh-CN (default) / en locale support via `?lang=`, cookie, or Accept-Language; JSON APIs are unaffected by locale.

**Persistent Tasks (`tasks/`)** — DB-backed queue, Deep Research DAG builder, and `TaskWorker` execute queued task runs. `smart-search-worker` is the worker console script. Current default node execution is safe/stubbed for tests and designed for future live execution seams.

## Flow

### Search Flow
1. `cli.main()` → `build_parser()` → `_run_async(args)`
2. `service.search(query, ...)` validates minimum profile → checks `validation_level` / `fallback_mode`
3. Builds `_main_search_provider_configs()` from configured providers
4. Iterates fallback chain calling `search_provider.search(query, platform)` until success
5. In parallel: Tavily/Firecrawl extra sources via `asyncio.gather`
6. If `validation_level` is `balanced`/`strict`: runs supplemental paths (`docs_search`, `web_search`, `web_fetch`) based on intent
7. `split_answer_and_sources()` extracts answer + sources from primary result
8. `merge_sources()` deduplicates across primary + extra + supplemental
9. Returns dict with `ok`, `content`, `sources`, `provider_attempts`, `routing_decision`

### Setup Flow
1. `cli._run_setup(args)` collects values from CLI flags or interactive prompts
2. `_run_guided_setup_prompts()` walks 3 required capabilities + optional enhancements (zh/en bilingual)
3. For each key, `service.config_set(key, value)` → `config.set_config_value()` → writes `config.json`
4. If skill targets selected → `install_skill_targets()` copies skill files to `~/.<tool>/skills/smart-search-cli/`

### Doctor Flow
1. `service.doctor()` loads config info, then runs connection tests against each provider
2. Main search providers get chat-completion + models-endpoint tests
3. Peripheral providers get targeted API calls
4. Computes `capability_status` + `minimum_profile_ok`
5. Returns comprehensive dict consumed by `_format_doctor_markdown()`

### Deep Research Flow
1. `service.build_deep_research_plan(query, budget)` — offline planner, no live API calls
2. Classifies intent signals (recency, docs, locale, claim risk, complexity)
3. Decomposes into sub-questions with required capabilities
4. Generates concrete CLI commands (`smart-search search ...`, `smart-search fetch ...`) with output paths
5. Returns plan with `steps`, `decomposition`, `capability_plan`, `gap_check` rules

### Cloud Tool Flow
1. `server.app.create_app()` creates DB/session state and mounts tool/admin/task routers.
2. `dependencies.require_bearer()` verifies `Authorization: Bearer ...` against `api_tokens`, constructs `ToolContext`, and route-specific scopes gate access.
3. `server.tools.dispatch_*()` calls existing `service.py` functions, records sanitized tool invocation metadata and audit events, then returns the service result.
4. Admin routes under `/admin` use admin-scoped tokens, password-signed session cookies, or an httponly admin cookie. HTML pages redirect unauthenticated users to `/admin/login`; JSON API returns 401/403. i18n defaults to zh-CN; `?lang=` sets a `ss_admin_locale` cookie and redirects; JSON APIs are locale-independent.
5. Admin analytics (`storage.repositories.get_admin_analytics`, `get_task_analytics`, `get_provider_groups`) aggregates tool invocations, task state, and provider config for dashboard/usage/provider views without external chart dependencies.
6. `/admin/config` uses `runtime.capabilities` to show true effective runtime config separately from DB-backed capability override drafts. Current cloud tool execution still delegates to `service.py`/`config.py`, so stored overrides are marked as not yet wired into execution.

### Persistent Deep Task Flow
1. `POST /api/tasks/deep_start` enqueues a `task_run` and DAG nodes through `DBBackedQueue.enqueue_deep_research()`.
2. `smart-search-worker` claims queued tasks, executes ready nodes, records attempts/events/artifacts, and marks the task completed/failed.
3. `/api/tasks/{id}/status`, `/events`, `/result`, and admin `/admin/tasks` expose progress and controls.

## Integration

- **External APIs**: xAI Responses, OpenAI-compatible chat-completions, Exa, Context7, Zhipu, Tavily, Firecrawl — all via `httpx.AsyncClient`
- **Config file**: JSON at `~/.config/smart-search/config.json` (or `LOCALAPPDATA/smart-search/config.json` on Windows); env vars override file values
- **AI Tool Skills**: Installs skill files into `.codex/skills/`, `.claude/skills/`, `.cursor/skills/`, etc., to make AI agents prefer `smart-search` CLI
- **CLI Entry Point**: `main()` → registered as `smart-search` console script; argparse with subcommands and aliases
- **Cloud Entry Points**: `smart_search.server.app:create_app` for ASGI hosting; `smart-search-worker` for queued task execution
- **Cloud DB**: `SMART_SEARCH_DATABASE_URL` defaults to SQLite (`smart-search-cloud.db`); PostgreSQL is supported via the `postgres` optional dependency. Zeabur deployments can use `${POSTGRES_CONNECTION_STRING}` directly or rely on the fallback.
- **Testing**: `smoke --mock` exercises routing/fallback logic without network; `smoke --live` hits real APIs; `doctor` validates connectivity; `regression` runs pytest suite

## Modification Notes

- **Adding a new provider**: Create a class in `providers/` implementing `search()` and `get_provider_name()`. Add its config keys to `Config._CONFIG_KEYS` and properties in `config.py`. Register it in the relevant fallback chain in `service.py` (`MAIN_SEARCH_FALLBACK_CHAIN` or the capability-specific chains in `get_capability_status()`). Add CLI subcommand in `cli.py`.
- **Adding config keys**: Add to `Config._CONFIG_KEYS`, add a property, update `get_config_info()` for doctor output, add to setup prompts in `cli.py` (both guided and advanced modes).
- **Changing fallback order**: Edit the chain lists in `service.py` (`MAIN_SEARCH_FALLBACK_CHAIN` and the hardcoded chains in `get_capability_status()` and `_setup_status_from_values()`).
- **Source extraction changes**: Modify `sources.py` — the priority order is function-call → heading → details block → tail link block. Add new regex patterns to the module-level compiled patterns.
- **Output format changes**: Add rendering logic in `cli.py` `_format_markdown()` and `_format_content()`. Both must handle all command types.
- **Deep research changes**: `build_deep_research_plan()` is a pure function — modify intent classifiers, decomposition logic, or step generation. Budget trimming (`quick`/`standard`/`deep`) is applied at the end.
- **Cloud tool API changes**: Add schemas in `server/schemas.py`, auth/scopes in `server/dependencies.py`, dispatch logic in `server/tools.py`, and tests in `tests/test_server_tools.py`.
- **Admin console changes**: Add routes/templates under `admin/`; use POST for secret reveal/mutations and record audit events for credential/token operations. Do not invent runtime defaults in Jinja/JS; add/adjust capability metadata in `runtime/capabilities.py` and make UI copy explicit when DB-backed overrides are stored-only.
- **Task runner changes**: Modify task models/repositories plus `tasks/queue.py`, `tasks/deep.py`, and `tasks/worker.py`; preserve SQLite compatibility and cover API/worker behavior in `tests/test_tasks.py`.
- **Skill targets**: Add `SkillTarget` entries to `SKILL_TARGETS` tuple in `skill_installer.py` and any aliases to `_TARGET_ALIASES`.
- **Minimum profile changes**: Edit `_ALLOWED_MINIMUM_PROFILES` in `config.py` and `validate_minimum_profile()` / `_minimum_profile_result()` in `service.py`. The required capabilities list is in `_minimum_profile_result()`.
