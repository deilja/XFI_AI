#!/usr/bin/env bash
set -u

LOG=/var/log/xfi-ai-heal.log
mkdir -p "$(dirname "$LOG")" 2>/dev/null || true
exec >>"$LOG" 2>&1

echo "=== $(date -Is) XFI AI health check ==="

services=()
for s in x-ui 3x-ui xray nginx docker; do
  if systemctl list-unit-files --type=service 2>/dev/null | awk '{print $1}' | grep -qx "${s}.service"; then
    services+=("$s")
  fi
done

for s in "${services[@]}"; do
  if ! systemctl is-active --quiet "$s"; then
    echo "WARN: $s is not active; restarting once"
    systemctl restart "$s" || { echo "FAIL: restart $s"; continue; }
    sleep 2
    if systemctl is-active --quiet "$s"; then
      echo "OK: $s recovered"
    else
      echo "FAIL: $s still down after restart"
    fi
  else
    echo "OK: $s active"
  fi
done

if command -v docker >/dev/null 2>&1; then
  docker ps --format 'container={{.Names}} status={{.Status}}' || true
fi

df -h / | tail -1 || true
free -h | head -2 || true
