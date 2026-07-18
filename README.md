
markdown
<div align="center">

<img src="assets/icon_store_dark.png" width="160" alt="WeaverCode"/>

# 🕸️ WeaverCode

**وكيل برمجي ذكي ومستقل — يعمل مع أي نموذج AI من أي شركة**

[

![Python](https://img.shields.io/badge/Python-3.10+-blue?style=flat-square&logo=python)

](https://python.org)
[

![License](https://img.shields.io/badge/License-MIT-orange?style=flat-square)

](LICENSE)
[

![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Android%2FTermux-green?style=flat-square)

](https://termux.dev)
[

![Models](https://img.shields.io/badge/Models-Any%20OpenAI--Compatible-purple?style=flat-square)

](config/.env.example)

*An independent AI coding agent — no vendor lock-in*

</div>

---

## What is WeaverCode?

WeaverCode is a terminal-based AI coding agent that reads your code, edits files, runs commands, and manages your projects — all through natural language.

**The key difference:** it doesn't belong to any company. Plug in any API key from any provider and it works.

```

You → WeaverCode → [Any AI Model] → Result
```

---

## Supported Providers

| Provider | Default Model | Free? |
|----------|--------------|-------|
| **OpenRouter** | claude-sonnet-4-6 | Partial |
| **Groq** | llama-3.3-70b-versatile | ✅ Yes |
| **DeepSeek** | deepseek-chat | Very cheap |
| **Anthropic** | claude-sonnet-4-6 | ❌ |
| **OpenAI** | gpt-4o | ❌ |
| **Ollama** | llama3.2 | ✅ Local |

---

## Quick Start

```bash
# Clone
git clone https://github.com/basharbhassan336699-cell/WeaverCode
cd WeaverCode

# Install
pip install -r config/requirements.txt --break-system-packages

# Configure
cp config/.env.example config/.env
nano config/.env    # Add your API key

# Run
python3 weaver.py "Your task here"
```

### Android / Termux
```bash
bash scripts/install_termux.sh
```

### 🌐 Web Dashboard + Background Mode
```bash
python3 weaver.py --background   # لوحة ويب + خلفية → http://localhost:8080
python3 weaver.py --web          # لوحة الويب فقط
```
واجهة متجاوبة (dark/light/system) على كل الأجهزة: بثّ حيّ للأحداث، إدارة المهام
والمحادثات والإعدادات وGitHub، و**تحميل الملفات بلا حدّ حجم** (1GB فأكثر).

---

## Usage

```bash
# Single task
python3 weaver.py "Read README.md and summarize it"

# Interactive mode
python3 weaver.py --interactive

# Specialized modes
python3 weaver.py --mode coding "Review provider.py"
python3 weaver.py --mode security "Scan project for vulnerabilities"
python3 weaver.py --mode analysis "Analyze this codebase"

# Switch model on the fly
python3 weaver.py --model "llama-3.3-70b-versatile" \
                  --url "https://api.groq.com/openai/v1" \
                  --key "gsk_..." "Your task"

# Multi-workspace + generate CLAUDE.md
python3 weaver.py --add-dir ../shared-lib --interactive
python3 weaver.py --init          # analyze project → CLAUDE.md

# System command (after install)
weaver -i
weaver --status
weaver --key groq
```

---

## Built-in Tools (43 built-in + MCP)

| Category | Tools |
|----------|-------|
| **Files** | Read (images/PDF aware), Write, Edit, MultiEdit, Glob, Grep, NotebookEdit |
| **Execution** | Bash (sandboxed + background), BashOutput, KillShell, PythonRun, PipInstall, Monitor |
| **Memory** | MemorySave, MemorySearch, MemoryDelete, MemoryList |
| **Tasks** | TaskCreate, TaskList, TaskUpdate, TodoWrite (live) |
| **Scheduling** | CronCreate, CronList, CronDelete |
| **Web** | WebFetch, WebSearch |
| **Git** | GitStatus, GitClone, GitCommit, GitPush |
| **Agents/Planning** | Agent (subagents), EnterPlanMode, ExitPlanMode |
| **Code** | LSP (diagnostics) |
| **System** | EnvSet, EnvGet, DirectoryList, AskUser, Skill |
| **External** | Any MCP server tool, resource & prompt (`mcp__<server>__<tool>`) |

> Additional capabilities: a real **permission system** (asks before dangerous
> tools), **plan mode** (`--plan` — plans and asks approval before edits),
> **Bash sandbox** (blocks catastrophic commands), **lifecycle hooks**
> (`.claude/hooks.json`), **context compaction** for long chats, **token-level
> streaming with tools**, **slash commands** from `.claude/commands/`, plus
> **self-healing**: automatic retry on transient network errors and automatic
> **provider fallback** (`config/providers.json`) when the primary runs out of
> credit or fails.

---

## Claude Code Parity Features ✨

WeaverCode mirrors the core experience of Claude Code — all provider-agnostic,
none of it touching your API-key setup:

| Feature | What it does |
|---------|--------------|
| **Images / PDF Read** | `Read` detects images & PDFs and encodes them into vision content blocks (Anthropic/OpenAI shape) |
| **NotebookEdit** | Edit / insert / delete cells in Jupyter `.ipynb` notebooks |
| **Live TodoWrite** | A live task checklist (☐ pending · ▶ in-progress · ☑ done) |
| **Diff preview** | Shows a colored unified diff *before* every Write/Edit/MultiEdit |
| **@-mentions** | Write `@path/to/file` in a prompt to inline that file's contents |
| **MCP resources & prompts** | Beyond tools — `resources/read` + `prompts/get`, shown in `/mcp` |
| **Multi-workspace** | `--add-dir` / `/add-dir` — Glob & Grep search across all roots |
| **Checkpoint & rewind** | Snapshots files before each edit; `/rewind`, `/rewind N`, `/rewind list` |
| **Background bash** | `Bash(run_in_background)` + `BashOutput` / `KillShell` |
| **/init** | Analyzes the project and generates a `CLAUDE.md` (`/init` or `--init`) |
| **Nested CLAUDE.md** | Loads `CLAUDE.md` from root, ancestors & subdirectories into context |
| **Cost & tokens** | Real per-model USD cost + token accounting from provider `usage` (`/cost`) |
| **Vim mode** | `WEAVER_VIM=1` or `/vim` — vi editing keys in the prompt |
| **VS Code extension** | `ide/vscode/` — run tasks, chat, explain files from the editor |

### Interactive slash commands

```
/cost        Show USD cost + tokens used         /add-dir <p>  Add a workspace dir
/context     Context size + window fill bar       /rewind       Undo last edit
/clear       Clear conversation & cost            /init         Generate CLAUDE.md
/compact     Summarize the conversation           /agents       List available agents
/model       Pick model from a live list          /mcp          MCP servers/resources
/vim         Toggle Vim input mode                /plan         Toggle plan mode
```

---

## Claude Code Commands

```
/weaver-install     First-time full setup
/weaver-start       Resume after device reboot ✨
/weaver-status      Full system health check
/weaver-run         Run with specific mode or model
/weaver-save        Save work and push to GitHub
/weaver-update      Pull latest updates from GitHub
/weaver-key         Change API key or provider
/weaver-memory      Manage persistent memory
/weaver-fix         Auto-fix common problems
/weaver-help        Show all commands
```

---

## Project Structure

```
WeaverCode/
├── weaver.py              ← Entry point
├── CLAUDE.md              ← Project memory for Claude Code
├── assets/                ← Icons (15 files)
├── core/
│   ├── engine/
│   │   ├── provider.py    ← Universal API connector
│   │   └── query_engine.py← Agentic loop
│   ├── tools/
│   │   └── registry.py    ← 43 built-in tools
│   ├── memory/
│   │   └── store.py       ← SQLite persistent memory
│   ├── cost.py            ← USD cost + token tracking
│   ├── checkpoint.py      ← Snapshot & rewind
│   ├── claude_md.py       ← Nested CLAUDE.md loader
│   ├── mentions.py        ← @file expansion
│   ├── diff_preview.py    ← Pre-edit diff preview
│   ├── multimodal.py      ← Image/PDF encoding
│   └── ui.py              ← Terminal UI with colors
├── prompts/
│   └── system.py          ← 6 specialized system prompts
├── ide/vscode/            ← VS Code extension
├── .claude/commands/      ← 16 Claude Code commands
├── config/
│   ├── .env.example
│   └── requirements.txt
├── tests/                 ← 129 tests
└── scripts/
    ├── weaver.sh          ← System-level command
    ├── expand_tools.py    ← Install missing tools
    ├── init_github.sh     ← Push to GitHub
    └── install_termux.sh  ← Android/Termux setup
```

---

## Operating Modes

| Mode | Use Case |
|------|----------|
| `main` | General purpose (default) |
| `coding` | Code review and writing |
| `project` | Project management |
| `security` | Security scanning |
| `autonomous` | Unsupervised long tasks |
| `analysis` | Deep analysis and research |

---

## Environment Variables

```bash
WEAVER_API_KEY=your_key_here
WEAVER_BASE_URL=https://openrouter.ai/api/v1
WEAVER_MODEL=anthropic/claude-sonnet-4-6
WEAVER_MAX_TOKENS=8192
WEAVER_TEMPERATURE=0.7
WEAVER_DB_PATH=~/.weaver/memory.db

# Optional (new features)
WEAVER_VIM=1                     # Vim input mode
WEAVER_PRICE_INPUT=3.0           # Override $/1M input tokens
WEAVER_PRICE_OUTPUT=15.0         # Override $/1M output tokens
WEAVER_ADD_DIRS=/path/a:/path/b  # Extra workspace dirs (colon-separated)
WEAVER_CONTEXT_WINDOW=200000     # Context window size for /context
```

---

## Brand Colors

- 🟠 Orange: `#C67121` — Web color  
- ⚫ Dark: `#0F0F19` — Background

---

## Developer

**Bashar** — UAE  
Built entirely through natural language with Claude.

---

<div align="center">
<img src="assets/icon_internal_64.png" width="36"/>
<br/>
<sub>🕸️ WeaverCode — Weaves code like a spider weaves its web</sub>
</div>
```
