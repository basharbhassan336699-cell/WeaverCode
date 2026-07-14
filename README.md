
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

# System command (after install)
weaver -i
weaver --status
weaver --key groq
```

---

## Built-in Tools (34 built-in + MCP)

| Category | Tools |
|----------|-------|
| **Files** | Read, Write, Edit, MultiEdit, Glob, Grep |
| **Execution** | Bash (sandboxed), PythonRun, PipInstall, Monitor |
| **Memory** | MemorySave, MemorySearch, MemoryDelete, MemoryList |
| **Tasks** | TaskCreate, TaskList, TaskUpdate |
| **Scheduling** | CronCreate, CronList, CronDelete |
| **Web** | WebFetch, WebSearch |
| **Git** | GitStatus, GitClone, GitCommit, GitPush |
| **Agents/Planning** | Agent (subagents), EnterPlanMode, ExitPlanMode |
| **Code** | LSP (diagnostics) |
| **System** | EnvSet, EnvGet, DirectoryList, AskUser |
| **External** | Any MCP server tool (`mcp__<server>__<tool>`) |

> Additional capabilities: a real **permission system** (asks before dangerous
> tools), **plan mode** (`--plan` — plans and asks approval before edits),
> **Bash sandbox** (blocks catastrophic commands), **lifecycle hooks**
> (`.claude/hooks.json`), **context compaction** for long chats, **token-level
> streaming with tools**, **slash commands** from `.claude/commands/`, plus
> **self-healing**: automatic retry on transient network errors and automatic
> **provider fallback** (`config/providers.json`) when the primary runs out of
> credit or fails.

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
│   │   └── registry.py    ← 44 built-in tools
│   ├── memory/
│   │   └── store.py       ← SQLite persistent memory
│   └── ui.py              ← Terminal UI with colors
├── prompts/
│   └── system.py          ← 6 specialized system prompts
├── .claude/commands/      ← 16 Claude Code commands
├── config/
│   ├── .env.example
│   └── requirements.txt
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
