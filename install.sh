#!/usr/bin/env bash
# ============================================================================
#  WeaverCode — one-command installer 🕸️   (Termux / Linux / macOS)
#  From a brand-new device to a running dashboard, in ONE command:
#
#     curl -fsSL https://raw.githubusercontent.com/basharbhassan336699-cell/WeaverCode/main/install.sh | bash
#
#  It installs prerequisites, downloads WeaverCode, installs its dependencies,
#  starts the dashboard, and prints the login URL. Re-running it updates.
# ============================================================================
set -u

REPO="${WEAVER_REPO:-https://github.com/basharbhassan336699-cell/WeaverCode}"
DIR="${WEAVER_DIR:-$HOME/WeaverCode}"
BRANCH="${WEAVER_BRANCH:-main}"
OR='\033[38;2;198;113;33m'; GN='\033[32m'; RD='\033[31m'; RS='\033[0m'
say(){ printf "${OR}🕸️${RS}  %s\n" "$1"; }
ok(){  printf "  ${GN}✓${RS} %s\n" "$1"; }
die(){ printf "  ${RD}✗${RS} %s\n" "$1"; exit 1; }

say "Installing WeaverCode…"

# ── 1) prerequisites (Termux installs them automatically) ───────────────────
if [ -d /data/data/com.termux/files/usr ] && command -v pkg >/dev/null 2>&1; then
  say "Termux detected — installing python + git…"
  yes | pkg install -y python git >/dev/null 2>&1 || pkg install -y python git
fi
command -v git >/dev/null 2>&1 || die "git is not installed. Install git, then re-run."
PY="$(command -v python3 || command -v python)"
[ -n "$PY" ] || die "Python 3.8+ is not installed. Install Python, then re-run."
ok "Prerequisites ready ($($PY --version 2>&1))"

# ── 2) download or update WeaverCode ────────────────────────────────────────
if [ -d "$DIR/.git" ]; then
  say "Updating existing install at $DIR …"
  git -C "$DIR" fetch origin "$BRANCH" >/dev/null 2>&1
  git -C "$DIR" pull --ff-only origin "$BRANCH" >/dev/null 2>&1 || true
  ok "Updated"
else
  say "Downloading WeaverCode to $DIR …"
  git clone --depth 1 -b "$BRANCH" "$REPO" "$DIR" 2>/dev/null \
    || git clone --depth 1 "$REPO" "$DIR" \
    || die "Could not download WeaverCode (check your internet connection)."
  ok "Downloaded"
fi
cd "$DIR" || die "Could not enter $DIR"

# ── 3) dependencies + setup (delegates to the cross-platform CLI) ───────────
"$PY" weaver-cli.py install || true

# ── 4) make 'weaver' available from anywhere ────────────────────────────────
BINDIR="$HOME/.local/bin"
for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
  [ -f "$rc" ] || continue
  grep -q '.local/bin' "$rc" 2>/dev/null || \
    printf '\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$rc"
done
export PATH="$BINDIR:$PATH"

# ── 5) start the dashboard and show the URL ─────────────────────────────────
say "Starting the dashboard…"
"$PY" weaver-cli.py start || true

echo
say "Done! WeaverCode is installed at: $DIR"
echo "  From now on you can use the 'weaver' command from anywhere:"
echo "     weaver start        # start + print the URL"
echo "     weaver stop         # stop"
echo "     weaver restore      # restart after closing the device/terminal"
echo "     weaver key <API_KEY>   # set your API key"
echo "     weaver doctor       # find problems    ·    weaver fix   # fix them"
echo "     weaver help         # all commands"
echo
echo "  (If 'weaver' is not found yet, run:  source ~/.bashrc   — or reopen the terminal.)"
echo "  Open the printed URL above in your browser, then set your API key in Settings."
