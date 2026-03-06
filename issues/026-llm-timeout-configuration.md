# Add LLM Request Timeout Configuration

## Overview
Add explicit `request_timeout` parameters to all LLM client initializations (`ChatGoogleGenerativeAI`, `ChatOpenAI`) across the three LangChain adapters to prevent requests from hanging indefinitely.

## Problem Statement
The Gemini, OpenAI, and xAI LLM adapters create LangChain chat model instances without specifying `request_timeout`. If an LLM provider experiences latency or a network issue, requests will hang indefinitely, blocking async workers and degrading the entire application. LangChain 0.3.27 supports `request_timeout` on both `ChatGoogleGenerativeAI` and `ChatOpenAI`.

## Proposed Solution
Add per-function `request_timeout` values based on the expected workload of each function type. Each public function passes a timeout to `_get_llm()` via `**kwargs`, set to 4x the expected maximum duration for that call type. This prevents false timeouts on legitimately slow calls while still catching truly hung requests.

Expected max durations and resulting timeouts:
| Function | Used For | Expected Max | Timeout (4x) |
|----------|----------|-------------|--------------|
| `simple_call` | Basic text generation | ~30s | 120s |
| `chat_call` | Multi-turn conversation | ~30s | 120s |
| `call_with_tools` | Tool-augmented calls | ~45s | 180s |
| `structured_output` | Scene refinement (Pydantic parsing) | ~60s | 240s |
| `json_output` | Scene extraction, ranking, prompt generation (large context) | ~90s | 360s |

For `xai_api.py`, use 240s (4x ~60s) since it handles structured refinement-style calls.

## Codebase Research Summary

### LLM client instantiation sites:

**`backend/app/services/langchain/gemini_api.py`** — `_get_llm()` at lines 83-89:
- Creates `ChatGoogleGenerativeAI` with: `model`, `google_api_key`, `temperature`, `max_tokens`, `**kwargs`
- Called by 5 public functions: `simple_call`, `chat_call`, `call_with_tools`, `structured_output`, `json_output`
- Missing: `request_timeout`

**`backend/app/services/langchain/openai_api.py`** — `_get_llm()` at lines 86-93:
- Creates `ChatOpenAI` with: `model`, `openai_api_key`, `temperature`, `max_tokens`, `response_format`, `**kwargs`
- Called by 5 public functions: `simple_call`, `chat_call`, `call_with_tools`, `structured_output`, `json_output`
- Missing: `request_timeout`

**`backend/app/services/langchain/xai_api.py`** — `XAIAPI.__init__()` at lines 71-77:
- Creates `ChatOpenAI` with: `api_key`, `base_url`, `model`, `temperature`, `max_tokens`
- No `**kwargs` pass-through, no way for callers to set timeout
- Missing: `request_timeout`

### Dependencies (from `backend/pyproject.toml`):
- `langchain==0.3.27` — supports `request_timeout` on both model classes
- `langchain-google-genai==2.1.12`
- `openai==2.1.0`

### Existing retry logic:
- `gemini_api.py` and `openai_api.py` use `AsyncRetrying` (tenacity) with 5 attempts, exponential backoff (min=4s, max=10s)
- `xai_api.py` uses synchronous `retry_with_backoff` with 5 attempts
- Timeouts will cause retryable exceptions, working naturally with the existing retry logic

## Key Decisions
- **Per-function timeouts**: Each public function passes its own `request_timeout` to `_get_llm()` via kwargs, sized to 4x the expected max duration for that call type. Heavier calls (`json_output` with large context windows) get longer timeouts than lightweight calls (`simple_call`).
- **Generous margins**: 4x multiplier ensures timeouts only fire on truly hung requests, never on legitimately slow LLM responses during peak load or large context processing.
- **Hardcoded, not configurable**: Timeouts are hardcoded per-function. No environment variables — this avoids config surface area and the values are tied to call characteristics, not deployment details.
- **xai_api.py also included** since it has the same gap, even though it uses `ChatOpenAI` under the hood.

## Implementation Plan

### Phase 1: Add per-function timeouts to Gemini adapter
**Goal**: Each Gemini API function has a timeout proportional to its expected workload.

**Tasks**:
- In `backend/app/services/langchain/gemini_api.py`, pass `request_timeout` via kwargs in each public function's call to `_get_llm()`:
  - `simple_call()` (line 114): pass `request_timeout=120`
  - `chat_call()` (line 145): pass `request_timeout=120`
  - `call_with_tools()` (line 194): pass `request_timeout=180`
  - `structured_output()` (line 230): pass `request_timeout=240`
  - `json_output()` (lines 268-274): pass `request_timeout=360`
- Callers can still override via their own `**kwargs` since explicit kwargs take precedence

**Verification**:
- [ ] Each function passes its own `request_timeout` to `_get_llm()`
- [ ] Timeout values match the table: 120, 120, 180, 240, 360

### Phase 2: Add per-function timeouts to OpenAI adapter
**Goal**: Each OpenAI API function has a timeout proportional to its expected workload.

**Tasks**:
- In `backend/app/services/langchain/openai_api.py`, pass `request_timeout` via kwargs in each public function's call to `_get_llm()`:
  - `simple_call()` (line 118): pass `request_timeout=120`
  - `chat_call()` (line 149): pass `request_timeout=120`
  - `call_with_tools()` (line 198): pass `request_timeout=180`
  - `structured_output()` (line 234): pass `request_timeout=240`
  - `json_output()` (lines 273-279): pass `request_timeout=360`

**Verification**:
- [ ] Each function passes its own `request_timeout` to `_get_llm()`
- [ ] Timeout values match the table: 120, 120, 180, 240, 360

### Phase 3: Add timeout to xAI adapter
**Goal**: xAI/Grok API calls have explicit timeout protection.

**Tasks**:
- Add `request_timeout=240` to `ChatOpenAI()` instantiation in `XAIAPI.__init__()` at `backend/app/services/langchain/xai_api.py` lines 71-77

**Verification**:
- [ ] `ChatOpenAI` (xAI) receives `request_timeout=240`

### Phase 4: Verify existing tests pass
**Goal**: Confirm no regressions.

**Tasks**:
- Run `cd backend && uv run pytest` to ensure all existing tests pass (mocked LLM calls are unaffected by timeout config)
- Run `cd backend && uv run bash scripts/lint.sh` for lint/type checks

**Verification**:
- [ ] All tests pass
- [ ] Lint passes

## Files to Modify
| File | Action |
|------|--------|
| `backend/app/services/langchain/gemini_api.py` | Modify — add per-function `request_timeout` (120-360s) |
| `backend/app/services/langchain/openai_api.py` | Modify — add per-function `request_timeout` (120-360s) |
| `backend/app/services/langchain/xai_api.py` | Modify — add `request_timeout=240` to `__init__()` |

## Testing Strategy
- **Unit Tests**: Existing tests mock the LLM functions entirely, so timeout config doesn't affect them. No new tests needed — this is a configuration change, not behavioral.
- **Manual Verification**: Run a scene ranking or prompt generation against a live LLM and confirm it completes normally within the timeout window.

## Acceptance Criteria
- [ ] All three LLM adapters pass `request_timeout` to their LangChain client constructors
- [ ] Timeouts are per-function: `simple_call`/`chat_call` 120s, `call_with_tools` 180s, `structured_output` 240s, `json_output` 360s, xAI 240s
- [ ] `cd backend && uv run bash scripts/lint.sh` passes
- [ ] `cd backend && uv run pytest` passes
