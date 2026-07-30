# WeaverCode — Command Line (all systems) 🕸️

One management command that works on **Android (Termux), Windows, macOS and
Linux**. It only uses Python's standard library, so it runs anywhere Python
3.8+ runs.

## Run it

```bash
python weaver-cli.py <command>
```

Or use the launcher for your system (from the project folder):

- Termux / Linux / macOS: `./weaver <command>`
- Windows (cmd): `weaver <command>`
- Windows (PowerShell): `.\weaver.ps1 <command>`

After `install`, the `weaver` command is available from anywhere (POSIX).

## Commands

| Command | What it does |
|---|---|
| `install` | Install dependencies, create `~/.weaver` dirs, `config/.env`, and a global `weaver` command |
| `start` · `up` · `web` | Start the dashboard + daemon in the background and **print the login URL** |
| `stop` · `down` | Stop all WeaverCode servers |
| `restart` · `restore` | Restart — **use this after closing the device or terminal** |
| `status` | Show what's running + the web URL + provider/model/key |
| `url` | Print the web login URL(s) |
| `open` | Print the URL and open it in a browser |
| `update [branch]` | Pull latest code (keeps your `.env`), update deps, restart, verify |
| `provider <name>` | Switch AI provider (openrouter/groq/deepseek/anthropic/openai/…) |
| `key <API_KEY>` | Set the API key (auto-detects the provider from the key prefix) |
| `model <name>` | Set the model |
| `doctor` · `diagnose` | Health checks (Python, git, deps, `.env`, key, provider reachability, port) |
| `fix` | Auto-fix common problems (missing dirs/`.env`, stuck port, missing deps, stale flags) |
| `logs [N]` | Show the last N lines of the server log |
| `version` | Print the WeaverCode version and platform |
| `help` | Show help |

## Typical flow

```bash
python weaver-cli.py install            # first time
python weaver-cli.py key sk-...          # set your API key
python weaver-cli.py start               # → prints http://127.0.0.1:8080
# ...open the URL in your browser...

# after closing the device/terminal, bring it back:
python weaver-cli.py restore

# something wrong?
python weaver-cli.py doctor              # find problems
python weaver-cli.py fix                 # fix common ones

# get the newest version:
python weaver-cli.py update
```

## Environment

- `WEAVER_WEB_PORT` (default `8080`) — dashboard port.
- `WEAVER_WEB_HOST` (default `0.0.0.0`) — set to `127.0.0.1` to limit access to this device.
