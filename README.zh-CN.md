# smart-search

简体中文 | [English](README.md)

`smart-search` 是一个给 AI 助手和命令行用户使用的 CLI-first 网页研究工具。它把普通联网搜索、来源发现、网页正文抓取、站点 map、配置检查和 Deep Research 规划统一成一个可复现的命令层。

<p>
  <a href="https://linux.do">
    <img src="https://img.shields.io/badge/LinuxDo-community-1f6feb" alt="LinuxDo">
  </a>
  <a href="https://www.npmjs.com/package/@konbakuyomu/smart-search">
    <img src="https://img.shields.io/npm/v/@konbakuyomu/smart-search?label=npm%20latest" alt="npm latest">
  </a>
</p>

感谢真诚、友善、团结、专业的 [LinuxDo](https://linux.do) 社区。本项目的 CLI + Skills 路线和开源推广说明均来自社区交流与启发。

![Star History Chart](https://api.star-history.com/svg?repos=konbakuyomu/smartsearch&type=Date)

## 它到底是什么

它最初是一个普通命令行工具，AI 工具通过 `smart-search-cli` skill 调它，脚本和终端用户也可以直接调它；现在也包含可选云端 Server / 管理台 / 任务运行时：

```powershell
smart-search search "今天 OpenAI Responses API 有什么新变化" --format json
smart-search fetch "https://example.com/article" --format markdown
smart-search deep "OpenAI Responses API web_search 和 Chat Completions 联网搜索怎么选" --format json
```

当前架构分三层：

| 层 | 负责什么 |
| --- | --- |
| CLI 执行层 | 稳定执行命令、provider 路由、同能力兜底、JSON/Markdown 输出、本机配置、smoke/regression |
| Skill / AI 编排层 | 判断用户意图，决定普通搜索还是 Deep Research，按计划执行 CLI 积木，最后写出有来源支撑的回答 |
| 云端服务层 | FastAPI 工具 API、API Key 鉴权、管理 WebUI、加密 provider 配置、调用统计/审计、持久 Deep Research 任务 |

`smart-search search` 保持快速、直接联网。`smart-search deep` 是显式 Deep Research 离线规划入口：默认不联网、不跑 provider、不抓网页，只输出 `research_plan`。真正联网发生在 AI 或用户继续执行 `steps[].command` 的时候。

## 云端 Server、管理台和任务系统

云端运行时适合私有/半私有部署：你可以创建多个服务 API Key 分发给朋友或团队成员，并在 WebUI 里管理 provider key、调用统计、审计和 Deep Research 任务。

### 安装云端依赖

核心 Server 依赖包含在 Python 包中。PostgreSQL 和 MCP 是可选 extras：

```powershell
pip install "smart-search[postgres,mcp]"
```

关键环境变量：

```text
SMART_SEARCH_DATABASE_URL=sqlite:///smart-search-cloud.db
SMART_SEARCH_MASTER_KEY=<稳定的 provider credential 加密密钥>
SMART_SEARCH_TOKEN_SECRET=<稳定的 API token HMAC 密钥>
SMART_SEARCH_ENABLE_MCP=false
```

SQLite 是默认轻量后端；正式多人部署或多 worker 建议使用 PostgreSQL。

### 启动云端 API

```powershell
uvicorn smart_search.server.app:create_app --factory --host 0.0.0.0 --port 8000
```

认证 HTTP 工具接口：

```text
POST /api/tools/search
POST /api/tools/fetch_url
POST /api/tools/map_site
POST /api/tools/docs_search
POST /api/tools/web_search
POST /api/tools/deep_plan
POST /api/tools/doctor
```

所有接口使用：

```text
Authorization: Bearer <smart-search-api-token>
```

并写入调用统计和审计。MCP 挂载默认关闭，需要时再显式开启：

```text
SMART_SEARCH_ENABLE_MCP=true
```

### 管理 WebUI

管理台路径：

```text
/admin/dashboard
/admin/tokens
/admin/providers
/admin/usage
/admin/audit
/admin/tasks
/admin/system
```

使用带 `admin` scope 的 API token。浏览器场景可以通过 `?token=...` 设置 httponly 管理 cookie。管理台支持：

- 创建/禁用服务 API token；
- 配置加密存储的 provider credentials 和 provider configs；
- 通过带审计记录的 POST reveal/copy provider key；
- 查看 usage、audit、system health 和 Deep Research tasks。

服务 API token 只在创建时显示一次。Provider key 加密存入数据库，管理员可按需 reveal 复制。

### 持久 Deep Research 任务

启动队列任务：

```text
POST /api/tasks/deep_start
```

任务 API 支持 status、events、result、pause、resume、cancel、retry node、redo node。单独启动 worker：

```powershell
smart-search-worker
```

当前任务系统会持久化 DAG 状态并支持远程控制；默认 node executor 保守、便于测试，后续可以接入更完整的 live execution。

## 安装

稳定版：

```powershell
npm install -g @konbakuyomu/smart-search@latest
smart-search --version
smart-search setup
```

测试版：

```powershell
npm install -g @konbakuyomu/smart-search@next
smart-search --version
```

npm 包安装时会自动创建隔离的 Python 运行环境。你平时只需要使用 `smart-search` 这个命令。

前置条件：

- 已安装 Node.js / npm。
- 已安装 Python 3.10 或更新版本，并且终端里能运行 `python`、`python3` 或 Windows 的 `py -3`。

## 快速开始

1. 配置 provider：

```powershell
smart-search setup
smart-search doctor --format json
```

2. 普通快速搜索：

```powershell
smart-search search "今天有什么值得关注的 AI 新闻？" --validation balanced --extra-sources 2 --format json
```

3. 抓取关键网页正文：

```powershell
smart-search fetch "https://example.com/source" --format markdown --output evidence.md
```

4. 生成 Deep Research 计划：

```powershell
smart-search deep "深度搜索一下最近的比特币行情" --budget standard --format json
```

5. 把 skill 安装给 AI 工具：

```powershell
smart-search setup --non-interactive --install-skills codex,claude,cursor,hermes
```

Skill 安装会把内置 `smart-search-cli` 写入用户级工具目录，例如 `~/.codex/skills`、
`~/.claude/skills`、`~/.cursor/skills`、`~/.hermes/skills`。它不会初始化 Trellis、hooks、
agents 或 commands。`--skills-root PATH` 只适合便携安装或测试时高级覆盖根目录。

## 当前架构

| 能力 | 主要命令 | Provider | 负责什么 |
| --- | --- | --- | --- |
| `main_search` | `search` | xAI Responses、OpenAI-compatible Chat Completions | 综合回答、快速搜索、初步总结 |
| `docs_search` | `exa-search`、`context7-library`、`context7-docs` | Exa、Context7 | 官方文档、SDK、API、框架/库文档 |
| `web_search` | `zhipu-search`、`search` 内部意图补强 | 智谱、Tavily、Firecrawl | 中文、国内、时效、域名过滤、补充来源 |
| `web_fetch` | `fetch` | Tavily、Firecrawl | 已知 URL 正文抓取、证据提取 |
| `site_map` | `map` | Tavily | 文档站、产品站、目录型站点结构 |
| `deep_planner` | `deep` / `dr` | 本地 planner | 离线生成 Deep Research 计划，不默认联网 |

同能力兜底关系：

| 能力 | 兜底链 |
| --- | --- |
| `main_search` | xAI Responses -> OpenAI-compatible |
| `docs_search` | Exa -> Context7 |
| `web_search` | 智谱 -> Tavily -> Firecrawl |
| `web_fetch` | Tavily -> Firecrawl |

这里有一个重要边界：兜底只在同一类能力里发生。不会用 Context7 去查普通新闻，也不会用 Firecrawl 假装做文档语义检索。

输出里会保留可观测字段：

| 字段 | 作用 |
| --- | --- |
| `routing_decision` | 为什么触发了某些补强路径 |
| `provider_attempts` | 每个 provider 的尝试结果 |
| `providers_used` | 最终用到哪些 provider |
| `fallback_used` | 是否触发同能力兜底 |
| `primary_sources` | 主搜索回答里带出的来源 |
| `extra_sources` | Tavily / Firecrawl 等额外发现的候选来源 |
| `source_warning` | 来源和回答之间可能存在的证据边界提醒 |

`extra_sources` 只是候选来源，不等于自动事实校验。新闻、政策、财经、医疗、严肃评测、工具选型等高风险问题，建议先发现来源，再 `fetch` 关键网页正文，最后只基于抓到的正文写结论。

## Deep Research 深度搜索

普通问题用：

```powershell
smart-search search "React useEffect cleanup 文档" --format json
```

需要深度搜索、拆解、核验、选型、严肃评测、多来源交叉验证时用：

```powershell
smart-search deep "OpenAI Responses API web_search 和 Chat Completions 联网搜索怎么选" --budget deep --format json
smart-search dr "https://example.com/source" --format json
```

Deep Research 不是固定题材配方。行情、选型、技术文档、新闻政策、真假核验、用户给 URL 这些只是用户语言示例，不是 schema 枚举。它会先抽取 `intent_signals`，再生成 `decomposition` 和 `capability_plan`。

计划里会包含：

- `mode="deep_research"` 和 `query_mode="deep"`；
- `intent_signals`：是否强时效、是否 docs/API、是否给 URL、是否高风险、是否需要权威来源、是否需要交叉验证；
- `decomposition`：复杂问题拆成 1-6 个子问题；
- `capability_plan`：选择需要的能力；
- `steps[]`：每一步的 `tool`、`purpose`、`command`、`output_path`、`subquestion_id`；
- `evidence_policy="fetch_before_claim"`；
- `gap_check`：关键结论没有正文证据就继续抓，或者降级成未验证候选。
- `usage_boundary`：说明 `search` 是直接联网，`deep` 是离线规划，真正执行发生在计划命令里。

Deep Research 只允许组合现有 CLI 积木：

```text
search, exa-search, exa-similar, zhipu-search, context7-library, context7-docs, fetch, map
```

`doctor` 是 preflight 配置预检，不是 research step。`smart-search deep` 这一步本身是离线 planner；后续执行计划里的 `steps[].command` 时才会联网。

换句话说，`doctor` 只是配置预检；它帮助 AI 判断当前 provider 是否可用，但不算 Deep Research 的取证步骤。

可以用这些标准问题测试是否进入深搜模式：

```powershell
smart-search deep "深度搜索一下最近的比特币行情" --format json
smart-search deep "OpenAI Responses API web_search 和 Chat Completions 联网搜索怎么选" --budget deep --format json
smart-search deep "帮我核验这个说法是真是假：某某工具已经完全替代 Tavily 做 AI 搜索了" --format json
smart-search deep "https://example.com/source" --format json
```

看到输出里有 `mode=deep_research`、`decomposition`、多步 `steps`、`evidence_policy=fetch_before_claim`、`preflight.executed_by_deep_command=false`，就说明已经进入 Deep Research 计划模式。

## API 和 Key 申请入口

普通用户优先用 `smart-search setup` 配置。环境变量仍然支持 CI 和高级用户。

| Provider / 路线 | 用途 | 主要配置项 | 官方文档 | Key / 控制台 |
| --- | --- | --- | --- | --- |
| xAI Responses API | 主搜索，走 `web_search,x_search` 工具 | `XAI_API_KEY`、`XAI_API_URL`、`XAI_MODEL`、`XAI_TOOLS` | [docs.x.ai](https://docs.x.ai/docs) | [xAI API keys](https://console.x.ai/team/default/api-keys) |
| OpenAI-compatible Chat Completions | 主搜索，适合 OpenAI 官方或兼容中转；这里不会发送 xAI search tools | `OPENAI_COMPATIBLE_API_URL`、`OPENAI_COMPATIBLE_API_KEY`、`OPENAI_COMPATIBLE_MODEL` | [OpenAI platform docs](https://platform.openai.com/docs) | [OpenAI API keys](https://platform.openai.com/api-keys) 或你的兼容服务商 |
| Exa | 官方文档、API、论文、产品页、可信网页的低噪声发现 | `EXA_API_KEY` | [Exa docs](https://docs.exa.ai/) | [Exa API keys](https://dashboard.exa.ai/api-keys) |
| Context7 | SDK、库、框架、API 文档兜底 | `CONTEXT7_API_KEY`、`CONTEXT7_BASE_URL` | [Context7 docs](https://context7.com/docs) | [Context7](https://context7.com/) |
| 智谱 Web Search API | 中文、国内、时效、域名过滤类来源发现 | `ZHIPU_API_KEY`、`ZHIPU_API_URL`、`ZHIPU_SEARCH_ENGINE` | [智谱联网搜索文档](https://docs.bigmodel.cn/cn/guide/tools/web-search) | [智谱 API keys](https://open.bigmodel.cn/usercenter/apikeys) |
| Tavily | 额外来源、URL fetch、站点 map | `TAVILY_API_URL`、`TAVILY_API_KEY` | [Tavily docs](https://docs.tavily.com/) | [Tavily app](https://app.tavily.com/home) |
| Firecrawl | fetch 兜底、补充网页来源 | `FIRECRAWL_API_URL`、`FIRECRAWL_API_KEY` | [Firecrawl docs](https://docs.firecrawl.dev/) | [Firecrawl API keys](https://www.firecrawl.dev/app/api-keys) |

几个容易混淆的点：

- xAI 官方联网搜索路线是 Responses API `/responses`，只通过 `XAI_*` 配置。兼容中转/网关走 Chat Completions `/chat/completions`，只通过 `OPENAI_COMPATIBLE_*` 配置。
- 旧的 `SMART_SEARCH_API_URL`、`SMART_SEARCH_API_KEY`、`SMART_SEARCH_API_MODE`、`SMART_SEARCH_MODEL`、`SMART_SEARCH_XAI_TOOLS` 不再是受支持配置项。请显式使用 `XAI_*` 或 `OPENAI_COMPATIBLE_*`。
- 不要给 OpenAI-compatible Chat Completions 中转强塞 xAI 的 `web_search` / `x_search` 工具或旧 `search_parameters`。
- 当前项目里的智谱是 Web Search API，不是 Chat Completions `tools=[web_search]`，不是 Search Agent，也不是 MCP Server。
- `ZHIPU_SEARCH_ENGINE` 默认是 `search_std`。官方值包括 `search_std`、`search_pro`、`search_pro_sogou`、`search_pro_quark`；`config set` 仍允许自定义值，方便官方以后新增服务。
- `TAVILY_API_URL` 只影响 Tavily，不会代理智谱。Tavily Hikari / 号池用 `https://<host>/api/tavily`；setup 会把根域名或 `/mcp` 输入规范化成这个 REST base。
- `FIRECRAWL_API_URL` 默认是 `https://api.firecrawl.dev/v2`。

非交互配置示例：

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

默认最低配置是 `SMART_SEARCH_MINIMUM_PROFILE=standard`，至少需要：

- `main_search`：xAI Responses 或 OpenAI-compatible 二选一；
- `docs_search`：Exa 或 Context7 二选一；
- `web_fetch`：Tavily 或 Firecrawl 二选一。

缺少任一最低能力时，`doctor` 和 `search` 会 fail closed 并返回缺失 capability。`SMART_SEARCH_MINIMUM_PROFILE=off` 只建议本地实验使用。

本机配置文件位置：

- Windows 默认：`%LOCALAPPDATA%\smart-search\config.json`。
- Linux/macOS 默认：`~/.config/smart-search/config.json`。
- `SMART_SEARCH_CONFIG_DIR` 是高级覆盖项，适合 CI、容器、沙箱或便携安装。
- 更早的 Windows 源码默认路径曾是 `~\.config\smart-search\config.json`，但有些安装会通过 `SMART_SEARCH_CONFIG_DIR` 提前固定到 `%LOCALAPPDATA%\smart-search`。如果新版默认位置还没有配置，但旧 home 路径存在配置，Smart Search 会以 `legacy_windows_home` 方式继续读取旧配置，避免升级后配置丢失；`doctor` 会同时报告当前生效路径、默认路径、旧 home 路径、`SMART_SEARCH_CONFIG_DIR` 的值，以及这个覆盖项是不是只是等于当前默认路径。

常用环境变量：

| 变量 | 用途 |
| --- | --- |
| `XAI_API_KEY` | xAI Responses provider key |
| `XAI_API_URL` | xAI API 地址，默认 `https://api.x.ai/v1` |
| `XAI_MODEL` | xAI 模型名 |
| `XAI_TOOLS` | xAI Responses 工具列表，通常 `web_search,x_search` |
| `OPENAI_COMPATIBLE_API_URL` | OpenAI-compatible `/v1` base URL |
| `OPENAI_COMPATIBLE_API_KEY` | OpenAI-compatible key |
| `OPENAI_COMPATIBLE_MODEL` | 兼容模型名 |
| `EXA_API_KEY` | Exa key |
| `CONTEXT7_API_KEY` | Context7 key |
| `ZHIPU_API_KEY` | 智谱 Web Search key |
| `ZHIPU_API_URL` | 智谱 API 地址，默认 `https://open.bigmodel.cn/api` |
| `ZHIPU_SEARCH_ENGINE` | 智谱搜索服务，例如 `search_pro_sogou` |
| `TAVILY_API_URL` | Tavily REST base |
| `TAVILY_API_KEY` | Tavily key |
| `TAVILY_TIMEOUT_SECONDS` | Tavily 连通性检查超时，默认 `30`；公益站/号池较慢时可调大 |
| `FIRECRAWL_API_URL` | Firecrawl REST base |
| `FIRECRAWL_API_KEY` | Firecrawl key |
| `SMART_SEARCH_VALIDATION_LEVEL` | `fast`、`balanced`、`strict` |
| `SMART_SEARCH_FALLBACK_MODE` | `auto` 或 `off` |
| `SMART_SEARCH_CONFIG_DIR` | 指定本机配置和日志根目录 |

## 常用命令

| 命令 | 简写 | 用途 |
| --- | --- | --- |
| `search` | `s` | 快速联网搜索和综合回答 |
| `deep` | `dr` | Deep Research 离线计划 |
| `fetch` | `f` | 抓一个 URL 正文 |
| `map` | `m` | 读取站点结构 |
| `exa-search` | `exa`、`x` | Exa 来源发现 |
| `exa-similar` | `xs` | 从一个 URL 找相似页面 |
| `zhipu-search` | `z`、`zp` | 智谱 Web Search API |
| `context7-library` | `c7`、`ctx7` | 查 Context7 库候选 |
| `context7-docs` | `c7d`、`c7docs`、`ctx7-docs` | 抓 Context7 文档 |
| `doctor` | `d` | 配置和连通性检查 |
| `setup` | `init` | 配置向导 |
| `config` | `cfg` | 本机配置读写 |
| `model` | `mdl` | 查看显式 provider 模型；修改请用 `config set XAI_MODEL` 或 `OPENAI_COMPATIBLE_MODEL` |
| `smoke` | `sm` | provider 路由冒烟测试 |
| `regression` | `reg` | 离线回归测试 |

示例：

```powershell
smart-search search "query" --validation balanced --extra-sources 3 --timeout 90 --format json --output result.json
smart-search search "nba战报" --format content
smart-search exa-search "OpenAI Responses API documentation" --include-domains platform.openai.com developers.openai.com --num-results 5 --include-text --format json
smart-search context7-library "react" "hooks" --format json
smart-search context7-docs "/facebook/react" "useEffect cleanup" --format json
smart-search zhipu-search "今天国内 AI 新闻" --search-engine search_pro_sogou --count 5 --format json
smart-search exa-similar "https://example.com/source" --num-results 5 --format json
smart-search fetch "https://example.com/source" --format markdown --output page.md
smart-search map "https://docs.example.com" --instructions "Find API reference pages" --max-depth 1 --limit 50 --format json
smart-search doctor --format markdown
smart-search smoke --mock --format json
smart-search regression
```

## 输出和证据策略

AI 和脚本解析优先用 JSON：

```powershell
smart-search search "query" --format json
smart-search doctor --format json
```

给人看连接状态、详细排障报告、冒烟结果、来源列表、网页正文时用 Markdown：

```powershell
smart-search doctor --format markdown
smart-search smoke --mock --format markdown
smart-search exa-search "OpenAI Responses API documentation" --format markdown
smart-search fetch "https://example.com" --format markdown
```

终端快速扫正文或摘要用 content：

```powershell
smart-search search "nba战报" --format content
smart-search doctor --format content
```

`content` 刻意保持很短，只适合快速看结论。完整排障给人看用 `doctor --format markdown`，给脚本和 AI 解析用 `doctor --format json`。

多来源研究建议保存证据文件：

```powershell
smart-search exa-search "Reuters Iran Hormuz latest" --format json --output C:\tmp\smart-search-evidence\iran-hormuz\01-exa.json
smart-search fetch "https://example.com/source" --format markdown --output C:\tmp\smart-search-evidence\iran-hormuz\02-fetch.md
```

写 claim-level 结论时建议流程：

1. 用 `search`、`exa-search`、`zhipu-search` 或 `exa-similar` 找候选 URL。
2. 用 `fetch` 抓关键 URL 正文。
3. 最终回答只引用 fetch 正文能支撑的事实。
4. 没有 fetch 的来源标为未验证候选。

## 排障

如果 `doctor` 返回 `config_error`：

```powershell
smart-search setup
smart-search config list --format json
smart-search doctor --format markdown
```

如果搜索慢：

- 降低 `--extra-sources`；
- 把大问题拆成多个小问题；
- 先用 `exa-search` 或 `zhipu-search` 找来源，再 `fetch` 关键网页。

如果想确认安装是否正常：

```powershell
smart-search --help
smart-search --version
smart-search regression
smart-search smoke --mock --format json
```

Windows npm/mise 安装后建议验证中文 JSON 管道：

```powershell
smart-search deep "深度搜索一下最近的比特币行情" --format json | ConvertFrom-Json
```

## 开发验证

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m smart_search.cli regression
.\.venv\Scripts\python.exe -m smart_search.cli smoke --mock --format json
npm test
npm pack --dry-run
```

## 发布通道

稳定版走 Git tag 和 npm `latest`：

```powershell
git tag v0.1.12
git push origin v0.1.12
```

测试版不移动 `latest`。推送到 `main` 会发布下一个 `<package.json version>-beta.N` 到 npm `next`，并且 `N` 按每个稳定版本重新从 1 开始。例如 `0.1.10-beta.1`、`0.1.10-beta.2` 之后是 `0.1.10-beta.3`。

已发布 npm 版本不可变。旧的 `*-dev.*` 包不能原地改名，只能发布新的 `*-beta.N` 替代。

发布收尾检查：

1. 先读 `npm view @konbakuyomu/smart-search versions --json`、`npm view @konbakuyomu/smart-search dist-tags --json`、`gh release list --repo konbakuyomu/smartsearch --limit 100`。
2. beta 发布必须保持 `latest` 不动，只移动 `next` 或指定的非 latest tag。
3. 遇到 npm `E409`，先查版本是否已经发布，再串行重跑对应版本。
4. 最后安装指定版本并运行 `smart-search --version`、`smart-search regression`、`smart-search smoke --mock --format json`。
5. Windows npm/mise 包装层额外跑中文 JSON 管道：`smart-search deep "深度搜索一下最近的比特币行情" --format json | ConvertFrom-Json`。

## License

MIT
