#!/usr/bin/env bash
# Start / stop the ML UI (port 8501) and the Dashboard (port 5080) in the background, bound to localhost only.
# They keep running after you log out of the pod; reach them through an SSH tunnel (docs/runpod.md).
#
#   bash deploy/runpod/start.sh            # start both (ones already running are left alone)
#   bash deploy/runpod/start.sh status     # running or not, and the log files
#   bash deploy/runpod/start.sh stop       # stop both (background jobs started from the ML UI keep running)
set -euo pipefail
cd "$(dirname "$0")/../.."
LOGS=results/logs
mkdir -p "$LOGS"
[ -x "$HOME/.dotnet/dotnet" ] && export PATH="$HOME/.dotnet:$PATH"
export DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1

running() { [ -f "$LOGS/$1.pid" ] && kill -0 "$(cat "$LOGS/$1.pid")" 2>/dev/null; }

start_one() {  # name, command...
  local name=$1; shift
  if running "$name"; then echo "$name: already running (pid $(cat "$LOGS/$name.pid"))"; return; fi
  setsid nohup "$@" > "$LOGS/$name.log" 2>&1 < /dev/null &
  echo $! > "$LOGS/$name.pid"
  echo "$name: started (pid $!, log $LOGS/$name.log)"
}

stop_one() {
  local name=$1
  if running "$name"; then
    kill -- "-$(cat "$LOGS/$name.pid")" 2>/dev/null || kill "$(cat "$LOGS/$name.pid")"   # whole process group
    echo "$name: stopped"
  else
    echo "$name: not running"
  fi
  rm -f "$LOGS/$name.pid"
}

case "${1:-start}" in
  start)
    start_one ml-ui python3 -m streamlit run ml/ui.py --server.address localhost --server.port 8501 \
      --server.headless true --client.toolbarMode viewer --browser.gatherUsageStats false
    start_one dashboard dotnet run -c Release --project Dashboard
    echo "ML UI http://localhost:8501   Dashboard http://localhost:5080   (through the SSH tunnel)"
    ;;
  status)
    for n in ml-ui dashboard; do
      if running "$n"; then echo "$n: running (pid $(cat "$LOGS/$n.pid"), log $LOGS/$n.log)"; else echo "$n: not running"; fi
    done
    ;;
  stop)
    stop_one ml-ui
    stop_one dashboard
    ;;
  *) sed -n '2,8p' "$0"; exit 2 ;;
esac
