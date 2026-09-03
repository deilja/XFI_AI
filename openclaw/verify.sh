#!/usr/bin/env bash
set -Eeuo pipefail

ok=0
fail=0
warn=0

check() {
  local label="$1"; shift
  printf '%-28s' "$label"
  if "$@" >/dev/null 2>&1; then
    echo 'OK'
    ok=$((ok + 1))
  else
    echo 'FAIL'
    fail=$((fail + 1))
  fi
}

optional_check() {
  local label="$1"; shift
  printf '%-28s' "$label"
  if "$@" >/dev/null 2>&1; then
    echo 'OK'
    ok=$((ok + 1))
  else
    echo 'WARN'
    warn=$((warn + 1))
  fi
}

command -v openclaw >/dev/null 2>&1 || {
  echo 'OpenClaw не найден в PATH.'
  exit 1
}

check 'OpenClaw CLI' openclaw --version
check 'Gateway status' openclaw gateway status
check 'Models list' openclaw models list
check 'Cron list' openclaw cron list
check 'Heartbeat' openclaw system heartbeat last

if command -v systemctl >/dev/null 2>&1; then
  for svc in x-ui 3x-ui xray nginx docker; do
    if systemctl cat "$svc" >/dev/null 2>&1; then
      check "service: $svc" systemctl is-active --quiet "$svc"
    fi
  done
fi

if command -v docker >/dev/null 2>&1 && systemctl cat docker >/dev/null 2>&1; then
  check 'Docker daemon' systemctl is-active --quiet docker
fi

optional_check 'Telegram pairing' openclaw pairing list telegram

printf '\nИтог: OK=%d FAIL=%d WARN=%d\n' "$ok" "$fail" "$warn"
if [ "$fail" -ne 0 ]; then
  echo 'Есть проверки, требующие внимания. Скрипт ничего не изменяет.'
  exit 2
fi

if [ "$warn" -ne 0 ]; then
  echo 'Критические проверки пройдены; есть предупреждения по необязательным компонентам.'
else
  echo 'Все доступные проверки пройдены.'
fi
