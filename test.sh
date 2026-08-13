#!/usr/bin/env bash
# End-to-end: drives tabcolor.sh against a throwaway tmux server and reads the
# option back. Also checks the iTerm2 OSC branch via a fake tty.
set -euo pipefail
cd "$(dirname "$0")"

sock=$(mktemp -u "${TMPDIR:-/tmp}/tabcolor-test.XXXXXX")
tmux -S "$sock" new-session -d -s t
trap 'tmux -S "$sock" kill-server 2>/dev/null || true' EXIT
pane=$(tmux -S "$sock" list-panes -t t -F '#{pane_id}')

run() { TMUX="$sock,0,0" TMUX_PANE="$pane" ./hooks/tabcolor.sh "$1"; }
style() { tmux -S "$sock" show-options -wqv -t "$pane" window-status-current-style; }

for state in busy:4a9eff attention:ff9f0a idle:30d158; do
  run "${state%%:*}"
  [[ $(style) == "bg=#${state##*:},fg=black,bold" ]] || { echo "FAIL ${state%%:*}: $(style)"; exit 1; }
done

run reset
[[ -z $(style) ]] || { echo "FAIL reset: $(style)"; exit 1; }

run bogus  # unknown state must be a no-op, not a crash
[[ -z $(style) ]] || { echo "FAIL bogus state changed style"; exit 1; }

# iTerm2 branch: no TMUX, run under a pty so /dev/tty resolves and is capturable.
# pty.fork() rather than script(1): it sets up its own session and controlling
# terminal instead of inheriting stdin, which is not a tty under every runner.
# 4a9eff -> 74 158 255.
osc=$(env -u TMUX -u TMUX_PANE python3 - ./hooks/tabcolor.sh busy <<'PY' | tr -d '\r'
import os, pty, sys
pid, fd = pty.fork()
if pid == 0:
    os.execv(sys.argv[1], sys.argv[1:])
out = b""
while True:
    try:
        chunk = os.read(fd, 4096)
    except OSError:
        break
    if not chunk:
        break
    out += chunk
status = os.waitpid(pid, 0)[1]
sys.stdout.write(out.decode("utf-8", "replace"))
sys.exit(os.waitstatus_to_exitcode(status))
PY
)
for want in 'red;brightness;74' 'green;brightness;158' 'blue;brightness;255'; do
  [[ $osc == *"$want"* ]] || { echo "FAIL osc missing $want"; exit 1; }
done

# No controlling tty (hook run headless): must be silent and exit 0. /dev/tty is
# world-writable regardless, so this is the case a -w guard silently lets through.
# setsid(2) via python3, since macOS ships no setsid(1); without it this case
# would silently pass on any machine that happens to have a terminal attached.
detached() {
  env -u TMUX -u TMUX_PANE python3 -c \
    'import os,subprocess,sys; os.setsid(); sys.exit(subprocess.call(sys.argv[1:]))' \
    ./hooks/tabcolor.sh "$1"
}
for state in busy reset; do
  err=$(detached "$state" 2>&1 >/dev/null </dev/null) || {
    echo "FAIL headless $state exited non-zero"; exit 1; }
  [[ -z $err ]] || { echo "FAIL headless $state wrote to stderr: $err"; exit 1; }
done

# hooks/hooks.json is loaded automatically. Naming it in the manifest too makes
# the plugin fail to load with "Duplicate hooks file detected".
python3 - <<'PY' || exit 1
import json, sys
m = json.load(open(".claude-plugin/plugin.json"))
if "hooks" in m:
    sys.exit("FAIL plugin.json must not declare the auto-loaded hooks/hooks.json")
json.load(open("hooks/hooks.json"))
PY

echo "ok"
