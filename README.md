# smart-search

[简体中文](README.zh-CN.md) | English

CLI-first, skill-driven web research for AI agents and terminal users. `smart-search` gives AI tools one reproducible command layer for live search, source discovery, page fetching, site mapping, provider diagnostics, and offline Deep Research planning.

<p>
  <a href="https://linux.do">
    <img src="https://img.shields.io/badge/LinuxDo-community-1f6feb" alt="LinuxDo">
  </a>
  <a href="https://www.npmjs.com/package/@konbakuyomu/smart-search">
    <img src="https://img.shields.io/npm/v/@konbakuyomu/smart-search?label=npm%20latest" alt="npm latest">
  </a>
</p>

Thanks to the [LinuxDo](https://linux.do) community for the discussions that shaped the CLI + Skills workflow.

![Star History Chart](https://api.star-history.com/svg?repos=konbakuyomu/smartsearch&type=Date)

## What It Is

`smart-search` started as a normal CLI that AI agents can call through a skill, and it now also includes an optional cloud server/admin/task runtime:

```powershell
smart-search search "latest OpenAI Responses API changes" --format json
smart-search fetch "https://example.com/article" --format markdown
smart-search deep "Compare Responses API web_search with Chat Completions search" --format json
```

The architecture has three layers:

| Layer | Responsibility |
| --- | --- |
| CLI executor | Runs deterministic commands, provider routing, fallback, JSON/Markdown output, local config, smoke/regression checks |
| Skill / AI orchestration | Infers user intent, chooses normal search vs Deep Research, executes planned CLI steps, writes final source-backed answers |
| Cloud server | FastAPI tool API, API key auth, admin WebUI, encrypted provider config, usage/audit, persistent Deep Research tasks |

Default `smart-search search` stays fast and live. `smart-search deep` is the explicit offline Deep Research planner. It does not call providers, run `doctor`, or fetch pages by default; it emits a `research_plan` that an AI agent or user can execute step by step.

## Cloud Server, Admin UI, and Tasks

The cloud runtime is intended for private/shared deployments where you distribute API keys to friends or teammates.

### Install server extras

Core server dependencies are included in the Python package. PostgreSQL and MCP are optional extras:

```powershell
pip install "smart-search[postgres,mcp]"
```

Important environment variables:

```text
SMART_SEARCH_DATABASE_URL=sqlite:///smart-search-cloud.db
SMART_SEARCH_MASTER_KEY=<stable encryption key for provider credentials>
SMART_SEARCH_TOKEN_SECRET=<stable HMAC secret for API token hashes>
SMART_SEARCH_ADMIN_PASSWORD=<admin login password (or use _HASH below)>
SMART_SEARCH_ADMIN_PASSWORD_HASH=<sha256:hex or pbkdf2_sha256:salt:hex>
SMART_SEARCH_ENABLE_MCP=false
```

SQLite is the default lightweight backend. PostgreSQL is recommended for production or multiple workers.

### Run the cloud API

```powershell
uvicorn smart_search.server.app:create_app --factory --host 0.0.0.0 --port 8000
```

### Zeabur deployment

This repository includes a `Dockerfile` tuned for Zeabur and other container platforms. Deploy the repository as a Docker service and use two Zeabur services when you want background Deep Research execution:

| Zeabur service | Start command | Notes |
| --- | --- | --- |
| Web/API | default Docker `CMD` | Runs `uvicorn smart_search.server.app:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}`. Set health check path to `/health`. |
| Worker | `smart-search-worker` | Use the same image and environment variables as the web service. It processes queued `/api/tasks/deep_start` jobs. |

Recommended Zeabur environment variables:

```text
SMART_SEARCH_DATABASE_URL=${POSTGRES_CONNECTION_STRING}
SMART_SEARCH_MASTER_KEY=<stable random secret>
SMART_SEARCH_TOKEN_SECRET=<stable random secret>
SMART_SEARCH_ADMIN_PASSWORD=<initial admin password>
SMART_SEARCH_ADMIN_COOKIE_SECURE=true
SMART_SEARCH_ENABLE_MCP=false
```

`SMART_SEARCH_DATABASE_URL` is still the canonical variable. For Zeabur convenience the server also accepts `POSTGRES_CONNECTION_STRING` as a fallback, and then `DATABASE_URL` as a final generic fallback.

Bare PostgreSQL URLs such as `postgresql://...` and `postgres://...` are automatically normalized to SQLAlchemy's `postgresql+psycopg://...` driver form used by the Docker image.

PostgreSQL is recommended on Zeabur. If you choose SQLite, point `SMART_SEARCH_DATABASE_URL` at a file inside a Zeabur Volume, for example `sqlite:////data/smart-search-cloud.db`, and mount `/data` persistently. Without a volume, SQLite data will be lost on rebuild/redeploy.

After the web service is live, visiting the root domain `/` redirects to the admin login page or dashboard. The public health endpoint is:

```text
GET /health
```

Authenticated HTTP tool endpoints:

```text
POST /api/tools/search
POST /api/tools/fetch_url
POST /api/tools/map_site
POST /api/tools/docs_search
POST /api/tools/web_search
POST /api/tools/deep_plan
POST /api/tools/doctor
```

All tool calls use `Authorization: Bearer <smart-search-api-token>` and write usage/audit records. MCP mounting is optional and disabled by default; enable it only after configuring your transport/auth expectations:

```text
SMART_SEARCH_ENABLE_MCP=true
```

### Admin WebUI

The admin console is mounted under:

```text
/admin/dashboard
/admin/tokens
/admin/providers
/admin/usage
/admin/audit
/admin/tasks
/admin/system
```

Accessing `/` or `/admin` in a browser automatically redirects to the dashboard if logged in, or to the login page if not.

#### Login

The admin login page (`/admin/login`) supports two authentication methods:

- **API Key login**: enter an API token with `admin` scope. The browser receives an httponly `ss_admin_session` cookie and redirects to the dashboard.
- **Password login**: enter the admin password configured via `SMART_SEARCH_ADMIN_PASSWORD` (plaintext) or `SMART_SEARCH_ADMIN_PASSWORD_HASH` (preferred). The hash format supports `sha256:<hex>` and `pbkdf2_sha256:<salt>:<hex>`. A signed session cookie is set on success.

Login failures show a generic error. Passwords and keys are never logged.

#### Logout

`/admin/logout` clears the session cookie and returns to the login page.

#### Session and auth

Both login methods set the same `ss_admin_session` httponly cookie. HTML pages redirect unauthenticated users to `/admin/login?next=<path>`; JSON API endpoints return 401/403 as appropriate.

The console can:

- create/disable service API tokens;
- configure encrypted provider credentials and provider routing configs;
- reveal/copy provider keys through an audited POST-only endpoint;
- view usage, audit logs, system status, and Deep Research tasks.

API access tokens are shown only once at creation. Provider keys are encrypted in the DB and can be revealed by an admin for copying.

### Persistent Deep Research Tasks

Start a queued task:

```text
POST /api/tasks/deep_start
```

Task APIs include status, events, result, pause, resume, cancel, retry node, and redo node. Run the worker separately:

```powershell
smart-search-worker
```

The current task runner persists DAG state and supports remote controls. Default node execution is conservative/stub-friendly for safe testing and future live execution refinement.

## Install

Stable channel:

```powershell
npm install -g @konbakuyomu/smart-search@latest
smart-search --version
smart-search setup
```

Test channel:

```powershell
npm install -g @konbakuyomu/smart-search@next
smart-search --version
```

The npm package creates an isolated Python runtime during install. You still use the single `smart-search` command.

Prerequisites:

- Node.js / npm.
- Python 3.10 or newer available as `python`, `python3`, or `py -3` on Windows.

## Quick Start

1. Configure providers:

```powershell
smart-search setup
smart-search doctor --format json
```

2. Run a normal live search:

```powershell
smart-search search "today's important AI news" --validation balanced --extra-sources 2 --format json
```

3. Fetch exact page evidence:

```powershell
smart-search fetch "https://example.com/source" --format markdown --output evidence.md
```

4. Plan Deep Research:

```powershell
smart-search deep "Deep research recent Bitcoin market movement" --budget standard --format json
```

5. Install the skill for AI tools when setup prompts you, or explicitly:

```powershell
smart-search setup --non-interactive --install-skills codex,claude,cursor,hermes
```

Skill installation writes the bundled `smart-search-cli` skill into user-level tool directories such as
`~/.codex/skills`, `~/.claude/skills`, `~/.cursor/skills`, and `~/.hermes/skills`. It does not initialize
Trellis, hooks, agents, or commands. `--skills-root PATH` is only an advanced override for portable or test installs.

## Current Architecture

| Capability | Main commands | Providers | Role |
| --- | --- | --- | --- |
| `main_search` | `search` | xAI Responses, OpenAI-compatible Chat Completions | Broad answer generation and synthesis |
| `docs_search` | `exa-search`, `context7-library`, `context7-docs` | Exa, Context7 | Official docs, SDKs, APIs, framework/library evidence |
| `web_search` | `zhipu-search`, intent-routed reinforcement inside `search` | Zhipu, Tavily, Firecrawl | Chinese, domestic, current, domain-filtered, or supplementary web discovery |
| `web_fetch` | `fetch` | Tavily, Firecrawl | Exact URL content extraction for evidence |
| `site_map` | `map` | Tavily | Site/documentation structure discovery |
| `deep_planner` | `deep` / `dr` | Local planner only | Offline plan generation; no provider call by default |

Fallback is same-capability only:

| Capability | Fallback chain |
| --- | --- |
| `main_search` | xAI Responses -> OpenAI-compatible |
| `docs_search` | Exa -> Context7 |
| `web_search` | Zhipu -> Tavily -> Firecrawl |
| `web_fetch` | Tavily -> Firecrawl |

The CLI exposes observability fields such as `routing_decision`, `provider_attempts`, `providers_used`, `fallback_used`, `primary_sources`, `extra_sources`, and `source_warning`.

`extra_sources` are discovery candidates. For high-risk claims, news, policy, finance, health, selection decisions, and serious reviews, fetch key pages first and cite fetched text rather than treating a broad search answer as proof.

## Deep Research

Use normal search when you want a fast answer:

```powershell
smart-search search "React useEffect cleanup docs" --format json
```

Use Deep Research when you want planning, decomposition, cross-checking, or strict evidence:

```powershell
smart-search deep "OpenAI Responses API web_search vs Chat Completions search: which should I use?" --budget deep --format json
smart-search dr "https://example.com/source" --format json
```

Deep Research output includes:

- `mode="deep_research"` and `query_mode="deep"`;
- `intent_signals`, such as recency, docs/API intent, known URL, claim risk, source authority, and cross-validation need;
- `decomposition`, with 1-6 subquestions depending on budget and difficulty;
- `capability_plan`, choosing from existing CLI blocks;
- `steps[]`, each with `tool`, `purpose`, `command`, `output_path`, and `subquestion_id`;
- `evidence_policy="fetch_before_claim"`;
- `gap_check`, which fetches missing evidence or downgrades unsupported claims.
- `usage_boundary`, which explains that `search` is live, `deep` is offline planning, and execution happens through planned commands.

Deep Research is not a fixed topic recipe system. Market research, product comparison, technical docs, news or policy, claim verification, and URL-first prompts are examples of user language, not required schema enums.

Allowed planned tools are:

```text
search, exa-search, exa-similar, zhipu-search, context7-library, context7-docs, fetch, map
```

`doctor` is preflight, not a research step. `smart-search deep` itself is offline; live research starts when an agent or user executes `steps[].command`.

Good user-facing smoke prompts:

```powershell
smart-search deep "深度搜索一下最近的比特币行情" --format json
smart-search deep "OpenAI Responses API web_search 和 Chat Completions 联网搜索怎么选" --budget deep --format json
smart-search deep "帮我核验这个说法是真是假：某某工具已经完全替代 Tavily 做 AI 搜索了" --format json
smart-search deep "https://example.com/source" --format json
```

## Provider And API Key Guide

Use `smart-search setup` for normal configuration. Environment variables remain supported for CI and advanced users.

| Provider / route | Used for | Main config keys | Official docs | Key / dashboard |
| --- | --- | --- | --- | --- |
| xAI Responses API | Primary live search with `web_search,x_search` tools | `XAI_API_KEY`, `XAI_API_URL`, `XAI_MODEL`, `XAI_TOOLS` | [docs.x.ai](https://docs.x.ai/docs) | [xAI API keys](https://console.x.ai/team/default/api-keys) |
| OpenAI-compatible Chat Completions | Primary search through OpenAI or a compatible relay; no xAI search tools are sent here | `OPENAI_COMPATIBLE_API_URL`, `OPENAI_COMPATIBLE_API_KEY`, `OPENAI_COMPATIBLE_MODEL` | [OpenAI platform docs](https://platform.openai.com/docs) | [OpenAI API keys](https://platform.openai.com/api-keys) or your relay provider |
| Exa | Low-noise official docs, API, paper, product, trusted-page discovery | `EXA_API_KEY` | [Exa docs](https://docs.exa.ai/) | [Exa API keys](https://dashboard.exa.ai/api-keys) |
| Context7 | SDK, library, framework, and API documentation fallback | `CONTEXT7_API_KEY`, `CONTEXT7_BASE_URL` | [Context7 docs](https://context7.com/docs) | [Context7](https://context7.com/) |
| Zhipu Web Search API | Chinese, domestic, current, or domain-filtered web discovery | `ZHIPU_API_KEY`, `ZHIPU_API_URL`, `ZHIPU_SEARCH_ENGINE` | [Zhipu web search docs](https://docs.bigmodel.cn/cn/guide/tools/web-search) | [Zhipu API keys](https://open.bigmodel.cn/usercenter/apikeys) |
| Tavily | Extra web sources, URL fetch, and site map | `TAVILY_API_URL`, `TAVILY_API_KEY` | [Tavily docs](https://docs.tavily.com/) | [Tavily app](https://app.tavily.com/home) |
| Firecrawl | Fetch fallback and supplementary web sources | `FIRECRAWL_API_URL`, `FIRECRAWL_API_KEY` | [Firecrawl docs](https://docs.firecrawl.dev/) | [Firecrawl API keys](https://www.firecrawl.dev/app/api-keys) |

Important boundaries:

- xAI official live search uses the Responses API `/responses` route through `XAI_*`. Compatible relays and gateways use Chat Completions `/chat/completions` through `OPENAI_COMPATIBLE_*`.
- Legacy `SMART_SEARCH_API_URL`, `SMART_SEARCH_API_KEY`, `SMART_SEARCH_API_MODE`, `SMART_SEARCH_MODEL`, and `SMART_SEARCH_XAI_TOOLS` are not supported config keys. Use `XAI_*` or `OPENAI_COMPATIBLE_*` explicitly.
- Do not force xAI `web_search` / `x_search` tools or legacy `search_parameters` into the OpenAI-compatible Chat Completions route.
- Zhipu support is the Web Search API route, not Zhipu Chat Completions `tools=[web_search]`, not Search Agent, and not the MCP Server.
- `ZHIPU_SEARCH_ENGINE` defaults to `search_std`. Supported official values include `search_std`, `search_pro`, `search_pro_sogou`, and `search_pro_quark`; custom values remain allowed for future services.
- `TAVILY_API_URL` affects Tavily only. It does not proxy Zhipu. For Tavily Hikari / pooled endpoints, use `https://<host>/api/tavily`; setup normalizes root-host or `/mcp` inputs to that REST base.
- `FIRECRAWL_API_URL` defaults to `https://api.firecrawl.dev/v2`.

Non-interactive setup example:

```powershell
smart-search setup --non-interactive `
  --xai-api-key "your-xai-key" `
  --xai-model "grok-4-fast" `
  --openai-compatible-api-url "https://api.openai.com/v1" `
  --openai-compatible-api-key "your-openai-or-relay-key" `
  --openai-compatible-model "gpt-4.1" `
  --validation-level "balanced" `
  --fallback-mode "auto" `
  --minimum-profile "standard" `
  --exa-key "your-exa-key" `
  --context7-key "your-context7-key" `
  --zhipu-key "your-zhipu-key" `
  --zhipu-api-url "https://open.bigmodel.cn/api" `
  --zhipu-search-engine "search_pro_sogou" `
  --tavily-api-url "https://api.tavily.com" `
  --tavily-key "your-tavily-key" `
  --firecrawl-api-url "https://api.firecrawl.dev/v2" `
  --firecrawl-key "your-firecrawl-key"
```

Minimum profile defaults to `standard`, requiring at least:

- one `main_search` provider: xAI Responses or OpenAI-compatible;
- one `docs_search` provider: Exa or Context7;
- one `web_fetch` provider: Tavily or Firecrawl.

Missing required capabilities fail closed with a configuration error. Use `SMART_SEARCH_MINIMUM_PROFILE=off` only for local experiments.

Local config path:

- Windows default: `%LOCALAPPDATA%\smart-search\config.json`.
- Linux/macOS default: `~/.config/smart-search/config.json`.
- `SMART_SEARCH_CONFIG_DIR` is an advanced override for CI, containers, sandboxes, or portable installs.
- Earlier Windows source builds defaulted to `~\.config\smart-search\config.json`, while some installs were already pinned to `%LOCALAPPDATA%\smart-search` through `SMART_SEARCH_CONFIG_DIR`. If the new Windows default file is missing but the old home config exists, Smart Search reads the old file as `legacy_windows_home` so upgrades do not lose configuration. `doctor` reports the active path, default path, old home path, `SMART_SEARCH_CONFIG_DIR`, and whether that override merely matches the current default.

Provider timeouts:

- `TAVILY_TIMEOUT_SECONDS` controls the Tavily `doctor` connectivity check timeout and defaults to `30`.
- Raise it for slower Tavily Hikari / pooled / community endpoints before treating the provider as unhealthy.

## Commands

| Command | Alias | Purpose |
| --- | --- | --- |
| `search` | `s` | Fast live search and broad synthesis |
| `deep` | `dr` | Offline Deep Research plan |
| `fetch` | `f` | Fetch one URL as JSON, Markdown, or content |
| `map` | `m` | Map a website structure |
| `exa-search` | `exa`, `x` | Exa source discovery |
| `exa-similar` | `xs` | Similar pages from one URL |
| `zhipu-search` | `z`, `zp` | Zhipu Web Search API |
| `context7-library` | `c7`, `ctx7` | Resolve Context7 library candidates |
| `context7-docs` | `c7d`, `c7docs`, `ctx7-docs` | Fetch Context7 docs |
| `doctor` | `d` | Masked config and connectivity check |
| `setup` | `init` | Interactive or scripted setup |
| `config` | `cfg` | Local config read/write |
| `model` | `mdl` | Show explicit provider model settings; use `config set XAI_MODEL` or `OPENAI_COMPATIBLE_MODEL` to change them |
| `smoke` | `sm` | Provider routing smoke tests |
| `regression` | `reg` | Offline regression checks |

Useful examples:

```powershell
smart-search search "query" --validation balanced --extra-sources 3 --timeout 90 --format json --output result.json
smart-search search "nba report" --format content
smart-search exa-search "OpenAI Responses API documentation" --include-domains platform.openai.com developers.openai.com --num-results 5 --include-text --format json
smart-search context7-library "react" "hooks" --format json
smart-search context7-docs "/facebook/react" "useEffect cleanup" --format json
smart-search zhipu-search "today China AI news" --search-engine search_pro_sogou --count 5 --format json
smart-search exa-similar "https://example.com/source" --num-results 5 --format json
smart-search fetch "https://example.com/source" --format markdown --output page.md
smart-search map "https://docs.example.com" --instructions "Find API reference pages" --max-depth 1 --limit 50 --format json
smart-search doctor --format markdown
smart-search smoke --mock --format json
smart-search regression
```

## Output And Evidence Policy

Use JSON for agents and scripts:

```powershell
smart-search search "query" --format json
smart-search doctor --format json
```

Use Markdown for human-readable reports, detailed diagnostics, source lists, and fetched page text:

```powershell
smart-search doctor --format markdown
smart-search smoke --mock --format markdown
smart-search exa-search "OpenAI Responses API documentation" --format markdown
smart-search fetch "https://example.com" --format markdown
```

Use `content` for compact terminal reading:

```powershell
smart-search search "nba report" --format content
smart-search doctor --format content
```

`content` is intentionally brief. Use `doctor --format markdown` for human troubleshooting and `doctor --format json` for the complete machine-readable contract.

Save multi-source evidence under a stable folder:

```powershell
smart-search exa-search "Reuters Iran Hormuz latest" --format json --output C:\tmp\smart-search-evidence\iran-hormuz\01-exa.json
smart-search fetch "https://example.com/source" --format markdown --output C:\tmp\smart-search-evidence\iran-hormuz\02-fetch.md
```

For claim-level evidence:

1. Discover candidate URLs with `search`, `exa-search`, `zhipu-search`, or `exa-similar`.
2. Fetch exact URLs with `fetch`.
3. Cite fetched text in the final answer.
4. Unsupported key claims must be fetched or downgraded to unverified candidates.

## Troubleshooting

If `doctor` reports `config_error`:

```powershell
smart-search setup
smart-search config list --format json
smart-search doctor --format markdown
```

If search is slow:

- reduce `--extra-sources`;
- split broad questions into smaller queries;
- use `exa-search` or `zhipu-search` for source discovery, then `fetch` key pages.

If installed CLI health is uncertain:

```powershell
smart-search --help
smart-search --version
smart-search regression
smart-search smoke --mock --format json
```

On Windows npm/mise installs, verify non-ASCII JSON piping:

```powershell
smart-search deep "深度搜索一下最近的比特币行情" --format json | ConvertFrom-Json
```

## Development

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m smart_search.cli regression
.\.venv\Scripts\python.exe -m smart_search.cli smoke --mock --format json
npm test
npm pack --dry-run
```

## Release lanes

Stable releases use Git tags and npm `latest`:

```powershell
git tag v0.1.12
git push origin v0.1.12
```

Test releases use npm prereleases and do not move `latest`. A push to `main` publishes the next `<package.json version>-beta.N` version under npm dist-tag `next`; `N` resets for each stable base version. To avoid publishing an unwanted beta for a stable bump, the `chore(release): bump version to X.Y.Z` branch commit is skipped by the workflow and the matching `vX.Y.Z` tag publishes npm `latest`. For example, after `0.1.10-beta.1` and `0.1.10-beta.2`, the next `main` publish is `0.1.10-beta.3`.

GitHub Actions also supports manual backfill for historical test builds through `workflow_dispatch`. Use an explicit `target_ref` plus an exact version such as `0.1.9-beta.1`, and publish it with a non-`latest` tag such as `backfill`. npm versions are immutable: old `*-dev.*` packages cannot be renamed in place, only superseded by new `*-beta.N` packages and optionally deprecated later with npm owner credentials.

Release closeout checklist:

1. Verify the registry and tags before changing anything: `npm view @konbakuyomu/smart-search versions --json`, `npm view @konbakuyomu/smart-search dist-tags --json`, and `gh release list --repo konbakuyomu/smartsearch --limit 100`.
2. For historical beta backfill, publish the replacement `*-beta.N` package through Actions with `create_github_release=false` if the workflow token cannot create releases, then create the missing GitHub prerelease locally with `gh release create vX.Y.Z-beta.N --target <commit> --prerelease --latest=false`.
3. Treat npm `E409` during parallel backfills as a registry concurrency failure, not a version-design failure. Re-run the affected version serially after checking whether the package already exists.
4. Do a machine-readable gap check: expected beta versions minus npm versions must be empty, and expected `v*beta*` releases minus GitHub prereleases must be empty.
5. Install the selected test build explicitly, for example `mise use -g "npm:@konbakuyomu/smart-search@0.1.10-beta.3" -y --pin`, then run `mise reshim`, `where.exe smart-search`, `smart-search --version`, `smart-search regression`, `smart-search smoke --mock --format json`, and a non-ASCII JSON pipe such as `smart-search deep "深度搜索一下最近的比特币行情" --format json | ConvertFrom-Json`.

## License

MIT
