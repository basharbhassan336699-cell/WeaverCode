# WeaverCode — Command Line Reference (all systems) 🕸️

Two command-line tools:

1. **`weaver-cli.py`** — the **management** tool (install / run / update / fix).
2. **`weaver.py`** — the **agent** itself (run a task, interactive chat, web).

Both use only Python's standard library for management, so they run on
**Android (Termux), Windows, macOS and Linux** — anywhere Python 3.8+ runs.

---

## 0) Install from scratch — one command

On a brand-new device (downloads WeaverCode, installs deps, starts, prints URL):

```bash
# Termux / Linux / macOS
curl -fsSL https://raw.githubusercontent.com/basharbhassan336699-cell/WeaverCode/main/install.sh | bash
```
```powershell
# Windows (PowerShell)
irm https://raw.githubusercontent.com/basharbhassan336699-cell/WeaverCode/main/install.ps1 | iex
```

It installs a global `weaver` command, so afterwards you can run `weaver start`,
`weaver stop`, `weaver restore`, `weaver key <API_KEY>`, `weaver help` from anywhere.

---

## 1) Management commands — `weaver-cli.py`

Run with `python weaver-cli.py <command>`, or the launcher for your system:

| System | How to run |
|---|---|
| Termux / Linux / macOS | `./weaver <command>` |
| Windows (cmd) | `weaver <command>` |
| Windows (PowerShell) | `.\weaver.ps1 <command>` |

After `install`, the `weaver` command works from anywhere (POSIX).

### Setup
| Command | What it does |
|---|---|
| `install` | Install dependencies, create `~/.weaver` dirs, `config/.env`, and a global `weaver` command |

### Run & control
| Command | What it does |
|---|---|
| `start` · `up` · `web` | Start the dashboard + daemon in the background and **print the login URL** |
| `stop` · `down` | Stop all WeaverCode servers |
| `restart` · `restore` | Restart — **use after closing the device or terminal** |
| `status` | Show what's running + URL + provider/model/key |
| `url` | Print the web login URL(s) |
| `open` | Print the URL and open it in a browser |
| `logs [N]` | Show the last N lines of the server log (default 40) |
| `banner` · `hello` | Show the WeaverCode hero banner (Hello / WEAVER CODE + artwork) |

### Update
| Command | What it does |
|---|---|
| `update [branch]` | Pull latest code (keeps your `.env`), update deps, restart, verify |

### Provider / key / model
| Command | What it does |
|---|---|
| `provider <name>` | Switch provider (openrouter/groq/deepseek/anthropic/openai/…) |
| `key <API_KEY>` | Set the API key (auto-detects the provider from the key prefix) |
| `model <name>` | Set the model |

### Troubleshooting
| Command | What it does |
|---|---|
| `doctor` · `diagnose` | Health checks: Python, git, deps, `.env`, key, provider reachability, port |
| `fix` | Auto-fix common problems (dirs, `.env`, stuck port, deps, stale flags) |

### Info
| Command | What it does |
|---|---|
| `version` | WeaverCode version + platform |
| `help` | Show help |

---

## 2) Agent commands — `weaver.py`

Run a task directly, chat interactively, or launch the web dashboard.

```bash
python weaver.py "your task here"
python weaver.py -i                       # interactive chat
python weaver.py --bg                     # web dashboard in the background
```

| Flag | What it does |
|---|---|
| `<prompt>` | The task to run (positional) |
| `--mode <m>` | Agent mode: `main` · `coding` · `project` · `security` · `autonomous` · `analysis` |
| `--interactive` · `-i` | Interactive chat mode |
| `--stream` | Streaming mode |
| `--plan` | Plan mode: plans and asks before any change |
| `--background` · `--bg` · `-b` | Web dashboard + background (http://localhost:8080) |
| `--web` · `-w` | Web dashboard in the foreground only |
| `--daemon` | Run the background daemon without the web UI |
| `--model <name>` | Model (overrides `WEAVER_MODEL`) |
| `--key <key>` | API key (overrides `WEAVER_API_KEY`) |
| `--url <url>` | API base URL (overrides `WEAVER_BASE_URL`) |
| `--yes` · `-y` | Auto-approve all tools without asking (careful) |
| `--resume [SESSION]` · `-r` | Resume a session (no value = interactive picker) |
| `--rename <NAME>` | Name the current session |
| `--sessions` | List saved sessions |
| `--add-dir <DIR>` | Add an extra working directory (repeatable) |
| `--work-dir <DIR>` · `-C` | Agent working directory (default: current folder) |
| `--init` | Analyze the project and generate a `CLAUDE.md` |
| `--print-system` | Print the actual system prompt sent to the model |
| `--version` · `-v` | Show version and exit |

### Interactive slash commands (inside `weaver.py -i`)
| Command | What it does |
|---|---|
| `/help` · `/commands` | List all commands |
| `/model [name]` · `/models` | Show/choose the model / list models |
| `/key <k>` | Set the API key |
| `/provider <name>` | Switch provider |
| `/mode <m>` | Switch agent mode |
| `/mcp` | List MCP servers |
| `/agents` | List available agents |
| `/add-dir <path>` | Add a working directory |
| `/init` | Generate a `CLAUDE.md` for the project |
| `/context` · `/messages` | Show context / message history |
| `/compact` | Summarize the conversation to save context |
| `/rewind` | Undo to a previous checkpoint |
| `/clear` | Clear the conversation |
| `/stats` · `/cost` | Show usage / token cost |
| `/vim` | Toggle vim editing mode |
| `exit` · `quit` | Leave interactive mode |

---

## 3) Environment variables

Set these in `config/.env` (or your shell). Only the common ones are listed;
defaults are shown in brackets.

### Provider (core)
| Variable | Meaning |
|---|---|
| `WEAVER_API_KEY` | Your provider API key |
| `WEAVER_BASE_URL` | Provider base URL (e.g. `https://openrouter.ai/api/v1`) |
| `WEAVER_MODEL` | Model name |
| `WEAVER_MAX_TOKENS` | Max output tokens `[model default]` |
| `WEAVER_TEMPERATURE` | Sampling temperature `[0.7]` |
| `WEAVER_EFFORT` | Effort preset (faster ↔ smarter) `[auto]` |

### Fallback provider (used if the main one fails)
| Variable | Meaning |
|---|---|
| `WEAVER_FALLBACK_API_KEY` · `WEAVER_FALLBACK_BASE_URL` · `WEAVER_FALLBACK_MODEL` | Backup provider |

### Web dashboard
| Variable | Meaning |
|---|---|
| `WEAVER_WEB_PORT` | Dashboard port `[8080]` |
| `WEAVER_WEB_HOST` | Bind host `[127.0.0.1]` (this device only) · set `0.0.0.0` to allow your network |
| `WEAVER_WEB_TOKEN` | Access token for the dashboard, enforced for **non-local** clients — set it when exposing to your network. Open with `http://<ip>:8080/?token=<token>` |

### Behavior & safety
| Variable | Meaning |
|---|---|
| `WEAVER_ASK_PERMISSION` | Ask before sensitive tools (Bash/write/push) `[0]` |
| `WEAVER_AUTO_APPROVE` | Approve every tool without asking `[0]` |
| `WEAVER_PLAN_MODE` | Start in plan mode `[0]` |
| `WEAVER_MAX_TURNS` | Max agent turns per task `[20]` |
| `WEAVER_LOOP_LIMIT` | Stop if a tool repeats with no progress `[8]` (0 = off) |
| `WEAVER_TASK_BUDGET` | Time budget per task, seconds `[1800]` (0 = off) |
| `WEAVER_TIMEOUT` | Per-request timeout, seconds `[120]` |
| `WEAVER_RETRIES` | Provider retries `[2]` |
| `WEAVER_REQUEST_DELAY` | Delay between requests, seconds `[0.0]` |
| `WEAVER_CONTEXT_WINDOW` | Context window size `[200000]` |
| `WEAVER_PROMPT_CACHE` | Enable prompt caching `[0]` |
| `WEAVER_SANDBOX` | Run Bash in an isolated proot sandbox `[0]` (needs `proot`) |
| `WEAVER_SANDBOX_TIMEOUT` | Sandbox command timeout, seconds `[30]` |
| `WEAVER_AUTO_VERIFY` | After writing code: check syntax (`py_compile`), real-bug lint (`ruff` if present), JS syntax (`node --check`), logic (`pytest` if tests exist), and **auto-fix errors** — inside the sandbox if enabled `[0]` |
| `WEAVER_AUTO_FIX_MAX` | Max auto-fix attempts `[2]` |

### Paths, tools & integrations
| Variable | Meaning |
|---|---|
| `WEAVER_DB_PATH` | Memory database path `[~/.weaver/memory.db]` |
| `WEAVER_WORK_DIR` · `WEAVER_ADD_DIRS` | Working directory / extra dirs |
| `WEAVER_OUTPUTS` | Where generated files go |
| `WEAVER_CHROMIUM` | Path to Chromium (for the Screenshot tool) |
| `WEAVER_GITHUB_TOKEN` · `GITHUB_TOKEN` | GitHub token (activity + push) |
| `GITHUB_OAUTH_CLIENT_ID` · `GITHUB_OAUTH_CLIENT_SECRET` | One-tap GitHub OAuth app |
| `WEAVER_NO_RESTART` | `1` = `update` won't restart the server |

---

## Typical flow

```bash
python weaver-cli.py install            # first time
python weaver-cli.py key sk-...          # set your API key (auto-detects provider)
python weaver-cli.py start               # → prints http://127.0.0.1:8080
# ...open the URL in your browser...

python weaver-cli.py restore             # after closing the device/terminal
python weaver-cli.py doctor              # find problems
python weaver-cli.py fix                 # fix common ones
python weaver-cli.py update              # get the newest version
```
