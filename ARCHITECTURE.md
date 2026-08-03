# 🕸️ WeaverCode — Architecture

WeaverCode is a **provider-agnostic autonomous coding agent** (in the spirit of
Claude Code) that runs on Android/Termux, Linux, Windows and macOS. It talks to
**any** OpenAI-compatible model through swappable API keys, ships a web
dashboard and a cross-platform CLI, and depends on almost nothing beyond the
Python standard library.

This document explains how the pieces fit together. For the feature-by-feature
history see [`docs/CHANGELOG.md`](docs/CHANGELOG.md); for commands and
environment variables see [`docs/CLI.md`](docs/CLI.md).

---

## 1. High-level picture

```
                ┌──────────────────────────────────────────────┐
   user  ─────► │  Interfaces                                   │
                │   • weaver.py            (terminal REPL/agent) │
                │   • weaver_cli.py        (install/manage CLI)  │
                │   • web/server.py + app  (dashboard + SSE)     │
                └───────────────┬──────────────────────────────┘
                                │  prompt + history
                                ▼
                ┌──────────────────────────────────────────────┐
                │  core/engine/query_engine.py  (the agent loop)│
                │   plan → call provider → run tools → repeat    │
                └───────┬───────────────┬───────────────┬───────┘
                        │               │               │
          provider.py   │   registry.py │    store.py    │  events.py
        (any LLM API)   ▼   (46 tools)  ▼  (SQLite memory)▼ (SSE bus)
                ┌───────────┐   ┌───────────┐   ┌───────────┐
                │  Model    │   │  Tools    │   │  Memory   │
                └───────────┘   └───────────┘   └───────────┘
```

The **golden rule**: nothing assumes the model is Claude/GPT/etc. Every request
goes through `core/engine/provider.py` using `WEAVER_MODEL`, `WEAVER_API_KEY`
and `WEAVER_BASE_URL` from the environment. Provider auth/headers live in one
place and are treated as load-bearing — changes there can break every backend.

---

## 2. Repository layout

```
WeaverCode/
├── weaver.py              # terminal agent entry point (weavercode command)
├── weaver_cli.py          # management CLI: install/start/stop/backup/… (weaver command)
├── core/
│   ├── engine/
│   │   ├── provider.py     # LLM transport: complete() / stream() / stream_events()
│   │   └── query_engine.py # the agent loop, tool dispatch, streaming, plans
│   ├── tools/registry.py   # all built-in tools (files, bash, git, web, memory, …)
│   ├── memory/store.py     # SQLite persistence (conversations, facts, sessions, FTS5)
│   ├── index/symbols.py    # code symbol index (ast for Python, regex for JS/TS)
│   ├── backup.py           # portable backup/export of memory + sessions
│   ├── sandbox.py          # optional proot isolation + verify/auto-fix
│   ├── permissions.py      # optional allow/deny/ask rules
│   └── ui.py, banner.py, cost.py, oplog.py, …  # presentation & bookkeeping
├── providers/              # provider presets (base URLs, default models, key prefixes)
├── background/
│   ├── daemon.py           # task queue that runs engine.run() and emits SSE events
│   └── events.py           # EventType enum + WeaverEvent + the singleton EventBus
├── web/
│   ├── server.py           # stdlib ThreadingHTTPServer + /events (SSE) + auth
│   └── static/ (app.js, style.css), templates/
├── config/                 # .env.example, requirements.txt, settings-*.json, mcp.json
├── plugins/                # bundled plugins (security-guidance, pr-review-toolkit, …)
├── prompts/                # system prompts
├── docs/                   # CHANGELOG, CLI reference, specs
└── tests/                  # pytest suite
```

---

## 3. The agent loop (`core/engine/query_engine.py`)

`QueryEngine.run()` is the heart of WeaverCode. One "turn" is:

1. **Assemble context** — system prompt + relevant memory + conversation history,
   bounded to the context window (`_bound_context`).
2. **Call the provider** — via `_complete_or_stream()`, which either streams
   token-by-token (`WEAVER_STREAM=1`, using `provider.stream_events()`) or does a
   plain `provider.complete()`. **Any streaming error falls back to
   `complete()`**, so streaming can never break a backend.
3. **Dispatch tool calls** — the model may request tools; the registry executes
   them (sequentially, honoring permissions), and results feed the next round.
4. **Emit progress** — via callbacks (`on_text`, `on_tool`, `on_permission`,
   `on_plan`, `on_narration`, `on_token`) that interfaces translate into UI.
5. **Repeat** until the model returns a final answer or a limit is reached.
6. **Persist** the exchange to memory.

`stream_run()` is a generator variant used where a streaming interface is
desired directly.

### Provider abstraction (`provider.py`)
Exposes `complete()`, `stream()` and `stream_events()` (which yields
`{type: text|tool_calls|done}` chunks). It is OpenAI-compatible and normalizes
across backends (Anthropic, OpenAI, OpenRouter, DeepSeek, Together, Groq,
Ollama, …). **This file owns authentication; treat it as critical.**

---

## 4. Tools (`core/tools/registry.py`)

Tools are the agent's hands. Each `Tool` has a name, description, JSON-Schema
parameters, an implementation function, and a `requires_permission` flag.
`ToolRegistry` registers the built-ins and can also register MCP tools
dynamically. Categories:

- **Files**: Read, Write, WriteBinary, Edit, MultiEdit, Glob, Grep, ExtractArchive
- **Execution**: Bash (+ BashOutput/KillShell), PythonRun, PipInstall, Monitor
- **Memory**: MemorySave/Search/Delete/List
- **Code intelligence**: LSP (syntax check), **SymbolIndex** (symbol lookup)
- **Git & GitHub**: GitStatus/Clone/Commit/Push, GitHub* (via `gh`)
- **Web**: WebFetch, WebSearch, Screenshot
- **Orchestration**: Agent (subagent), TodoWrite, TaskCreate/List/Update, Cron*
- **Control**: EnterPlanMode/ExitPlanMode, Skill, NotebookEdit

`to_schema(compact=…)` produces the OpenAI tool schema sent to the model
(`WEAVER_COMPACT_TOOLS=1` roughly halves tool-schema tokens).

---

## 5. Memory (`core/memory/store.py`)

A single SQLite database (`~/.weaver/memory.db`, override with `WEAVER_DB_PATH`):

- `conversations` — every prompt/response, with FTS5 (`conversations_fts`) kept in
  sync by triggers, so `get_relevant()` does real full-text retrieval (with a
  `LIKE` fallback when FTS5 isn't compiled in).
- `facts` — durable key/value knowledge the agent chooses to keep.
- `patterns` — recurring usage patterns.
- `sessions` — full conversations, so `--resume` and the dashboard can reopen them.

**Backup/export** (`core/backup.py`) bundles a *consistent* copy of this DB (via
the sqlite backup API) plus a version-independent `export.json` and a manifest
into a portable `.tar.gz`. Restore snapshots the current DB first, so a restore
can never silently lose data. Exposed as `weaver backup` / `backups` /
`restore-backup`.

---

## 6. Code symbol index (`core/index/symbols.py`)

To work efficiently on large codebases, WeaverCode can build a lightweight
**symbol index**: functions, classes and methods with file + line number.

- **Python** is parsed with the stdlib `ast` in a single parent-aware pass
  (methods vs. free functions are classified correctly, nothing double-counted).
- **JS/TS, Go, Rust, Java** are parsed with tolerant regexes (functions,
  classes, structs, interfaces, traits, enums).
- Noise directories (`node_modules`, `.venv`, `__pycache__`, …) and oversized
  files are skipped; the index is cached under `~/.weaver/cache`. An
  **incremental** rebuild re-parses only files whose mtime changed and drops
  deleted ones, so refreshes stay fast on large trees.

The `SymbolIndex` tool exposes `build` / `find` / `outline`, giving the model
jump-to-definition without re-scanning the tree each time. The same index is
available from the terminal via `weaver symbols …`.

---

## 7. Web dashboard (`web/` + `background/`)

- `web/server.py` is a stdlib `ThreadingHTTPServer`. It binds to `127.0.0.1` by
  default; exposing it to a network requires `WEAVER_WEB_TOKEN` (enforced only for
  non-local clients via cookie / `X-Weaver-Token` / `?token=`, compared with
  `hmac.compare_digest`).
- `background/daemon.py` runs a task queue: it calls `engine.run()` and turns the
  callbacks into **Server-Sent Events** on a shared `EventBus`
  (`background/events.py`). Event types include THINKING, TOOL_START/END,
  ACTION_BLOCK, NARRATION, **TOKEN** (live streaming), RESPONSE, DONE, ERROR.
- `web/static/app.js` connects to `/events`, renders the conversation (with a
  markdown renderer and RTL/LTR auto-detection), and — when streaming is on —
  builds the assistant bubble token-by-token with a blinking caret.

---

## 8. Cross-cutting concerns

- **Sandbox & self-verification** (`core/sandbox.py`): optional proot isolation
  (`WEAVER_SANDBOX=1`) and, after writing code, structure + logic checks
  (`py_compile`, `ruff`, `node --check`, `pytest`) with an auto-fix loop
  (`WEAVER_AUTO_VERIFY=1`).
- **Permissions** (`core/permissions.py`): optional file/command allow-deny-ask
  rules from `config/settings-*.json`. With no settings file the behavior stays
  "ask" — nothing changes.
- **Sessions, hooks, skills, plugins, MCP**: see the feature notes in
  `CLAUDE.md` and `docs/CHANGELOG.md`.

### Design principles
1. **Provider independence** — never hardcode a vendor; go through `provider.py`.
2. **Opt-in, default-off** — new behaviors (streaming, sandbox, auto-verify,
   permissions) must not change existing behavior unless explicitly enabled.
3. **Stdlib-first** — the CLI, web server, backup and index need no third-party
   packages, so WeaverCode installs and runs anywhere Python 3.8+ runs.
4. **Verify before "done"** — code changes are checked with real tests
   (`python -m pytest tests/`) before being declared complete.
