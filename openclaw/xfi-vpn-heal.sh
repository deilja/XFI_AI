#!/usr/bin/env bash
set -u

LOG=/var/log/xfi-ai-heal.log
LOCK=/run/lock/xfi-ai-heal.lock
mkdir -p "$(dirname "$LOG")" 2>/dev/null || true
exec >>"$LOG" 2>&1

# Prevent overlapping cron/systemd/manual runs. A hung run is also bounded.
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "SKIP: another XFI AI health check is already running"
  exit 0
fi

if ! command -v timeout >/dev/null 2>&1; then
  echo "FAIL: timeout command is required"
  exit 1
fi

run() {
  timeout --signal=TERM --kill-after=3s 15s "$@"
}

echo "=== $(date -Is) XFI AI health check ==="

services=()
for s in x-ui 3x-ui xray nginx docker; do
  if systemctl list-unit-files --type=service 2>/dev/null | awk '{print $1}' | grep -qx "${s}.service"; then
    services+=("$s")
  fi
done

for s in "${services[@]}"; do
  if ! run systemctl is-active --quiet "$s"; then
    echo "WARN: $s is not active; restarting once"
    if ! run systemctl restart "$s"; then
      echo "FAIL: restart $s"
      continue
    fi
    sleep 2
    if run systemctl is-active --quiet "$s"; then
      echo "OK: $s recovered"
    else
      echo "FAIL: $s still down after restart"
    fi
  else
    echo "OK: $s active"
  fi
done

if command -v docker >/dev/null 2>&1; then
  run docker ps --format 'container={{.Names}} status={{.Status}}' || true
fi

run df -h / | tail -1 || true
run free -h | head -2 || true
