#!/usr/bin/env bash
set -u

ok=0
fail=0

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

command -v openclaw >/dev/null 2>&1 || {
  echo 'OpenClaw не найден в PATH.'
  exit 1
}

check 'OpenClaw CLI' openclaw --version
check 'Gateway status' openclaw gateway status
check 'Models list' openclaw models list
check 'Telegram pairing' openclaw pairing list telegram
check 'Cron list' openclaw cron list
check 'Heartbeat' openclaw system heartbeat last

for svc in x-ui 3x-ui xray nginx docker; do
  if systemctl cat "$svc" >/dev/null 2>&1; then
    check "service: $svc" systemctl is-active --quiet "$svc"
  fi
done

if command -v docker >/dev/null 2>&1; then
  check 'Docker daemon' systemctl is-active --quiet docker
fi

printf '\nИтог: OK=%d FAIL=%d\n' "$ok" "$fail"
if [ "$fail" -ne 0 ]; then
  echo 'Есть проверки, требующие внимания. Скрипт ничего не изменяет.'
  exit 2
fi

echo 'Все доступные проверки пройдены.'
