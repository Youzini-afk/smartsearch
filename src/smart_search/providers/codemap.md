# src/smart_search/providers/

## Responsibility

Provides the search-provider abstraction layer for Smart Search. Each provider encapsulates a distinct external search or LLM API, exposing a uniform `search()` interface while preserving provider-specific capabilities through additional methods. The module is responsible for:

- Defining the `BaseSearchProvider` ABC and `SearchResult` data class as the contract
- Implementing concrete providers: OpenAI-compatible chat completions, xAI Responses API, Exa neural search, Context7 library/docs search, and Zhipu web search
- Handling HTTP transport, retry logic, error normalization, and response parsing for each upstream API

## Design

### Base abstraction

- **`BaseSearchProvider`** (ABC in `base.py`) — requires `api_url`, `api_key`; declares two abstract methods: `search(query, max_results)` → `List[SearchResult]` and `get_provider_name()` → `str`.
- **`SearchResult`** — simple data holder with `title`, `url`, `snippet`, `source`, `published_date` and a `to_dict()` serializer.

> **Deviation**: Concrete providers return `str` (JSON) from `search()` rather than `List[SearchResult]`. Only `OpenAICompatibleSearchProvider.search()` returns `List[SearchResult]` (matching the base signature). The other four providers return raw JSON strings. This is a known interface inconsistency.

### Provider-specific patterns

| Provider | Class | Return type | API style | Key extra methods |
|---|---|---|---|---|
| OpenAI-compatible | `OpenAICompatibleSearchProvider` | `List[SearchResult]` / `str` | Chat completions (`/chat/completions`) | `fetch()`, `describe_url()`, `rank_sources()`, streaming support |
| xAI Responses | `XAIResponsesSearchProvider` | `str` | Responses API (`/responses`) | — |
| Exa | `ExaSearchProvider` | `str` | REST POST (`/search`, `/findSimilar`) | `find_similar()` |
| Context7 | `Context7Provider` | `str` | REST GET (`/api/v2/search`, `/api/v2/context`) | `library()`, `docs()` |
| Zhipu | `ZhipuWebSearchProvider` | `str` | REST POST (`/paas/v4/web_search`) | — |

### Retry infrastructure

All providers share the same retry pattern via `tenacity.AsyncRetrying`:
- **Retryable exceptions**: `httpx.TimeoutException`, `httpx.NetworkError`, `httpx.ConnectError`, and HTTP status codes `{408, 429, 500, 502, 503, 504}`.
- **Config-driven**: `config.retry_max_attempts`, `config.retry_multiplier`, `config.retry_max_wait`.
- **`_WaitWithRetryAfter`** (in `openai_compatible.py`) — extends exponential backoff with `Retry-After` header parsing for 429 responses; shared by `xai_responses.py`.
- **`_is_retryable_exception()`** — duplicated in `context7.py`, `exa.py`, `zhipu.py`, and `openai_compatible.py` (slight variation: openai_compatible also checks `httpx.RemoteProtocolError`).

### Error normalization

- `ExaSearchProvider` and `ZhipuWebSearchProvider` define `_error_payload()` helpers that classify errors (`rate_limited`, `auth_error`, `timeout`, `network_error`, `parameter_error`, `runtime_error`) and include them in JSON output.
- `OpenAICompatibleSearchProvider` and `XAIResponsesSearchProvider` propagate exceptions via retry; callers handle errors upstream.

### Citation extraction

- `OpenAICompatibleSearchProvider` — extracts citations from `data.citations`, `choices[].message.citations` (supports both string URLs and `{url, title}` dicts). Deduplicates by URL. Appends `sources([...])` block to content.
- `XAIResponsesSearchProvider` — extracts `url_citation` annotations from `output[].content[].annotations`. Same dedup and `sources()` suffix pattern.

### Response format handling

- `OpenAICompatibleSearchProvider` — handles both JSON and SSE streaming responses. `_parse_completion_response()` falls back to SSE parsing if body starts with `data:`. `_parse_streaming_response()` processes SSE `data:` lines, with a fallback to parsing the full buffered body as JSON.
- All other providers expect JSON responses only.

## Flow

### OpenAI-compatible / xAI Responses (LLM-powered search)

```
caller → search(query, platform?)
  → build payload (system prompt + user query + time context + platform hint)
  → _execute_*_with_retry(headers, payload)
    → httpx POST to /chat/completions or /responses
    → tenacity retry on retryable exceptions
    → parse response (JSON or SSE) / extract citations
  → return content string (with optional sources suffix)
```

### Exa (neural search)

```
caller → search(query, num_results, search_type, filters...)
  → build JSON payload (query, type=neural/keyword, contents, domain filters)
  → _request_with_retry(endpoint, headers, payload)
    → httpx POST to /search
    → tenacity retry
  → _normalize_result() per item
  → return JSON {ok, query, results, total, elapsed_ms}
```

### Context7 (library/docs search)

```
caller → library(name, query) or docs(library_id, query)
  → build GET URL with query params
  → _get_with_retry(endpoint)
    → httpx GET with retry
  → _normalize_library() per item (library) or extract snippets (docs)
  → return JSON {ok, query, results/code_snippets/info_snippets, elapsed_ms}
```

### Zhipu (web search)

```
caller → search(query, count, search_engine, filters...)
  → build JSON payload (search_query capped at 70 chars, engine, intent, recency)
  → _request_with_retry(endpoint, headers, payload)
    → httpx POST to /paas/v4/web_search
    → tenacity retry
  → _normalize_result() per item
  → return JSON {ok, query, provider, results, total, search_intent, elapsed_ms}
```

## Integration

### Inbound dependencies (what the providers module imports)

- **`..config`** (`config`) — retry settings (`retry_max_attempts`, `retry_multiplier`, `retry_max_wait`), SSL verify flag, debug flag, model name defaults.
- **`..logger`** (`log_info`) — structured async logging; all providers pass `ctx` through for MCP context.
- **`..utils`** (`search_prompt`, `fetch_prompt`, `url_describe_prompt`, `rank_sources_prompt`) — system prompt templates used by OpenAI-compatible and xAI providers.

### Outbound (what consumes providers)

- **`__init__.py`** re-exports all five provider classes and `BaseSearchProvider`/`SearchResult`.
- Upstream orchestration (likely in `src/smart_search/server.py` or similar MCP server module) instantiates providers from config values and routes tool calls to the appropriate provider's `search()` (and `library()`, `docs()`, `find_similar()`, etc.) methods.

### Cross-provider sharing

- `xai_responses.py` imports `_WaitWithRetryAfter`, `_is_retryable_exception`, and `get_local_time_info` from `openai_compatible.py`.
- All providers independently define their own `_is_retryable_exception()` (code duplication across `context7.py`, `exa.py`, `zhipu.py`).

## Modification Notes

- **Return type inconsistency**: The base class declares `search()` → `List[SearchResult]`, but four of five concrete implementations return `str` (JSON). If the base contract is ever enforced, Context7, Exa, xAI, and Zhipu will need adapter wrappers or the base signature needs updating.
- **Duplicated retry helpers**: `_is_retryable_exception()` is copy-pasted in four files with minor variations (openai_compatible includes `RemoteProtocolError`; zhipu omits 429 from retryable codes). Consider moving a shared version into `base.py` or a `retry_utils.py` helper.
- **Adding a new provider**: Subclass `BaseSearchProvider`, implement `search()` and `get_provider_name()`, add retry via `tenacity` following the existing pattern, then register in `__init__.py` and wire into the server's provider factory.
- **Citation handling divergence**: Only OpenAI-compatible and xAI Responses providers extract and append citation data. Exa, Context7, and Zhipu return provider-specific JSON shapes without a unified citation format. If cross-provider citation normalization is needed, consider a shared `normalize_citations()` in `base.py`.
- **Context7 is GET-only**: Unlike all other providers that POST JSON bodies, Context7 uses GET with query-string parameters. This affects caching and URL-length limits for long queries.
- **Zhipu query truncation**: `search_query` is silently sliced to 70 characters (`query[:70]`). Long queries may produce unexpected results.
- **SSL verification**: OpenAI-compatible and xAI providers respect `config.ssl_verify_enabled` with a one-time warning; Exa, Context7, and Zhipu do not honor this setting.
