#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_PORT=8091
FAIL=0

ok(){ printf '[ OK ] %s\n' "$*"; }
warn(){ printf '[WARN] %s\n' "$*"; }
bad(){ printf '[FAIL] %s\n' "$*" >&2; FAIL=1; }

[[ $EUID -eq 0 ]] || { echo "Запустите: sudo bash deploy/preflight.sh" >&2; exit 1; }

printf '%s\n' 'XFI AI production preflight (read-only)'
printf '%s\n' '========================================'

[[ -f /etc/os-release ]] && . /etc/os-release || true
if [[ "${ID:-}" == "ubuntu" && "${VERSION_ID:-}" == 24.04* ]]; then
  ok "Ubuntu $VERSION_ID"
else
  warn "Рекомендуется Ubuntu 24.04; обнаружено: ${PRETTY_NAME:-unknown}"
fi

for cmd in python3 curl openssl nginx systemctl ss; do
  command -v "$cmd" >/dev/null 2>&1 && ok "Команда: $cmd" || bad "Не найдена команда: $cmd"
done

if python3 - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
then ok "Python >= 3.11"; else bad "Требуется Python >= 3.11"; fi

[[ -f "$APP_ROOT/app/api.py" ]] && ok "app/api.py найден" || bad "Не найден app/api.py"
[[ -f "$APP_ROOT/app/providers.py" ]] && ok "app/providers.py найден" || bad "Не найден app/providers.py"
[[ -f "$APP_ROOT/requirements.txt" ]] && ok "requirements.txt найден" || bad "Не найден requirements.txt"
[[ -f "$APP_ROOT/deploy/install.sh" ]] && ok "deploy/install.sh найден" || bad "Не найден deploy/install.sh"
[[ -f "$APP_ROOT/pyproject.toml" ]] && ok "pyproject.toml найден" || bad "Не найден pyproject.toml"

if python3 -m compileall -q "$APP_ROOT/app"; then
  ok "Python syntax check"
else
  bad "Ошибка Python syntax check"
fi

if [[ -d "$APP_ROOT/tests" ]]; then
  if python3 -m pytest -q "$APP_ROOT/tests" >/tmp/xfi-ai-preflight-pytest.log 2>&1; then
    ok "Pytest"
  else
    bad "Pytest завершился ошибкой"
    tail -n 30 /tmp/xfi-ai-preflight-pytest.log >&2 || true
  fi
else
  warn "Каталог tests не найден"
fi

if ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq '(:|\])8091$'; then
  warn "Порт 8091 уже занят; установщик предложит другой порт"
else
  ok "Порт 8091 свободен"
fi

if systemctl is-active --quiet xfi-ai 2>/dev/null; then
  warn "xfi-ai.service уже запущен"
else
  ok "xfi-ai.service не запущен"
fi

if nginx -t >/tmp/xfi-ai-preflight-nginx.log 2>&1; then
  ok "Nginx configuration valid"
else
  warn "Текущая конфигурация Nginx не проходит nginx -t (может быть чистый VPS)"
fi

if [[ -e /etc/letsencrypt/live ]]; then
  ok "Let's Encrypt каталог доступен"
else
  warn "Let's Encrypt ещё не настроен"
fi

printf '\n'
if (( FAIL )); then
  echo "PREFLIGHT: FAILED"
  exit 2
fi

echo "PREFLIGHT: READY"
echo "Следующий шаг: sudo bash deploy/install.sh"
