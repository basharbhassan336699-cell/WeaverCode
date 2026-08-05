# 🕸️ Contributing to WeaverCode

Thanks for your interest in WeaverCode — a provider-agnostic autonomous coding
agent. This guide covers how to set up, make changes safely, and get them
merged. For the big picture read [`ARCHITECTURE.md`](ARCHITECTURE.md); for the
project conventions read [`CLAUDE.md`](CLAUDE.md).

---

## Getting started

Requirements: **Python 3.8+** (3.10+ recommended), `git`, and optionally `node`
(for JS syntax checks) and `ruff` (for linting).

```bash
git clone https://github.com/basharbhassan336699-cell/WeaverCode
cd WeaverCode
python weaver-cli.py install      # creates ~/.weaver dirs, installs deps, makes config/.env
python weaver-cli.py key <API_KEY>   # set your provider key (or edit config/.env)
python weaver-cli.py start        # launch the dashboard, prints the URL
```

On Termux, dependency installs may need `pip install --break-system-packages`
(the CLI already tries this automatically).

---

## Ground rules (please read)

These are hard constraints for the project — a change that violates them will be
sent back:

1. **Never break the provider connection.** `core/engine/provider.py` owns
   authentication, headers and the request format for every backend. Don't
   change its auth/key/header logic unless that is explicitly the task.
2. **Never commit secrets.** `config/.env` is git-ignored and holds real API
   keys. Document new variables in `config/.env.example`, never in `.env`.
3. **New features are opt-in and default-off.** Anything that changes agent
   behavior (streaming, sandbox, auto-verify, permissions, …) must be gated
   behind an env var or flag so existing behavior is unchanged out of the box.
4. **Stdlib-first.** The CLI, web server, backup and index avoid third-party
   packages so WeaverCode runs anywhere. Add a dependency only when necessary,
   and add it to `config/requirements.txt` and `pyproject.toml`.
5. **UI text is English** (both the terminal and the web dashboard); the agent
   replies in whatever language the user writes in.

---

## Making a change

1. **Branch** off the current default branch.
2. **Match the surrounding style.** Python: 4-space indent, type hints where the
   file already uses them, docstrings (the codebase uses bilingual Arabic +
   English comments — keep that style in files that already have it). Prefer the
   dedicated file/search idioms over shelling out.
3. **Keep changes focused.** Touch only what the task needs; don't reformat
   unrelated code.
4. **Document env vars & commands** you add in `config/.env.example` and
   `docs/CLI.md`.
5. **Record notable changes** in `docs/CHANGELOG.md` and bump the version in
   `core/ui.py` (`WEAVER_VERSION`) and `pyproject.toml` together.

### Adding a tool
Register it in `core/tools/registry.py` with a clear name, description and
JSON-Schema parameters, set `requires_permission=True` for anything that writes,
executes or reaches the network, and implement the `_your_tool` method. Add a
test.

### Adding a provider
Add a preset (base URL, default model, key prefix) under `providers/` — do not
special-case it in the engine.

---

## Verifying your work (required)

WeaverCode's own rule is: **don't say "done" until a real test has run.**

```bash
# 1) syntax check every Python file you created/modified
python3 -m py_compile path/to/file.py

# 2) run the full test suite (must stay green)
python3 -m pytest tests/ -q

# 3) for JS changes
node --check web/static/app.js
```

Please add tests for new behavior under `tests/` (the suite uses `pytest`;
`tests/conftest.py` isolates the memory DB to a temp file, so tests never touch
your real `~/.weaver`). Follow the existing files as templates.

Before committing, clean transient state:

```bash
rm -f config/.env ~/.weaver/cancel.flag ~/.weaver/web.pid
```

---

## Commit & pull request

- Write clear, descriptive commit messages (a concise subject line, then a body
  explaining *why*).
- Open a pull request against the default branch describing what changed and how
  you verified it (paste the test summary).
- Keep the diff reviewable; split large work into logical commits.

## Reporting bugs & ideas

Open a GitHub issue with steps to reproduce, your platform (Termux/Linux/
Windows/macOS), Python version, and the provider/model you're using (never paste
your API key). Feature ideas are welcome too — describe the use case.

Thank you for helping make WeaverCode better! 🕸️
