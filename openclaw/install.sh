#!/usr/bin/env bash
set -Eeuo pipefail

OPENCLAW_HOME="${OPENCLAW_HOME:-$HOME/.openclaw}"
CONFIG="$OPENCLAW_HOME/openclaw.json"
ENV="$OPENCLAW_HOME/.env"
WORKSPACE="$OPENCLAW_HOME/workspace"

[[ $EUID -ne 0 ]] || echo "OpenClaw лучше устанавливать от пользователю-оператору, не root."
command -v curl >/dev/null || { echo "curl is required" >&2; exit 1; }
command -v openclaw >/dev/null 2>&1 || {
  echo "Installing OpenClaw..."
  curl -fsSL https://openclaw.ai/install.sh | bash
}
command -v openclaw >/dev/null 2>&1 || { echo "openclaw command not found after installation" >&2; exit 1; }

mkdir -p "$OPENCLAW_HOME" "$WORKSPACE"
chmod 700 "$OPENCLAW_HOME" "$WORKSPACE"

read -rsp "RouterAI API key (Enter = keep existing): " ROUTERAI_KEY; echo
read -rsp "Groq API key (Enter = keep existing): " GROQ_KEY; echo
read -rsp "Telegram bot token (Enter = keep existing): " TELEGRAM_TOKEN; echo
read -rp "Heartbeat interval [15m]: " HEARTBEAT; HEARTBEAT="${HEARTBEAT:-15m}"

python3 - "$CONFIG" "$ENV" "$WORKSPACE" "$ROUTERAI_KEY" "$GROQ_KEY" "$TELEGRAM_TOKEN" "$HEARTBEAT" <<'PY'
import json, os, sys
from pathlib import Path
cfg_path, env_path, workspace, router, groq, telegram, heartbeat = sys.argv[1:]
existing = {}
if Path(cfg_path).exists():
    try: existing = json.loads(Path(cfg_path).read_text())
    except Exception: existing = {}
env = {}
if Path(env_path).exists():
    for line in Path(env_path).read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k,v=line.split('=',1); env[k]=v
if router: env['ROUTERAI_API_KEY']=router
if groq: env['GROQ_API_KEY']=groq
if telegram: env['TELEGRAM_BOT_TOKEN']=telegram
existing.setdefault('env', {}).setdefault('vars', {})
for k in ('ROUTERAI_API_KEY','GROQ_API_KEY','TELEGRAM_BOT_TOKEN'):
    if env.get(k): existing['env']['vars'][k]=env[k]
existing.setdefault('models', {}).setdefault('providers', {})
existing['models']['providers']['routerai']={'baseUrl':'https://routerai.ru/api/v1','apiKey':'${ROUTERAI_API_KEY}','api':'openai-completions'}
existing['models']['providers']['groq']={'baseUrl':'https://api.groq.com/openai/v1','apiKey':'${GROQ_API_KEY}','api':'openai-completions'}
existing.setdefault('agents', {}).setdefault('defaults', {})
existing['agents']['defaults']['model']={'primary':'routerai/anthropic/claude-sonnet-4-5','fallbacks':['groq/openai/gpt-oss-120b','routerai/deepseek/deepseek-chat']}
existing['agents']['defaults'].setdefault('workspace', workspace)
existing.setdefault('channels', {}).setdefault('telegram', {})
existing['channels']['telegram'].update({'botToken':'${TELEGRAM_BOT_TOKEN}','dmPolicy':'pairing'})
existing.setdefault('heartbeat', {})['every']=heartbeat
Path(cfg_path).write_text(json.dumps(existing,ensure_ascii=False,indent=2)+'\n')
Path(env_path).write_text(''.join(f'{k}={v}\n' for k,v in env.items()))
os.chmod(cfg_path,0o600); os.chmod(env_path,0o600)
PY

cp -f "$(dirname "$0")/HEARTBEAT.md" "$WORKSPACE/HEARTBEAT.md"
chmod 600 "$WORKSPACE/HEARTBEAT.md"

openclaw system heartbeat enable || true
openclaw gateway restart || openclaw gateway start || true
openclaw models status || true

# Create only fixed, isolated, read-only/repair jobs. Re-running is idempotent by name.
add_cron() {
  local name="$1" cron="$2" message="$3"
  if ! openclaw cron list 2>/dev/null | grep -Fq "$name"; then
    openclaw cron add --name "$name" --cron "$cron" --session isolated --message "$message" --announce --channel telegram || true
  fi
}

add_cron "vpn-heal" "*/10 * * * *" "Проверь 3X-UI/X-UI, xray, nginx и docker. Используй только правила openclaw/HEARTBEAT.md. Если сервис упал — безопасно перезапусти только существующий сервис один раз. Не меняй пользователей, ключи, inbound, порты, TLS, firewall или базу. Если исправил или не смог поднять — сообщи администратору в Telegram. Если всё нормально — молчи."
add_cron "hourly-check" "0 * * * *" "Сделай только диагностику XFI AI/VPN: состояние OpenClaw gateway, 3X-UI/X-UI, xray, nginx, docker, диск и RAM. Ничего не изменяй, кроме разрешённого безопасного restart по HEARTBEAT. Сообщи только об отклонении или выполненном исправлении."
add_cron "morning-report" "0 9 * * *" "Сформируй краткий ежедневный отчёт: OpenClaw gateway, heartbeat, cron, AI providers, 3X-UI/X-UI, xray, nginx, docker, диск/RAM и ошибки за сутки. Только диагностика, без изменений конфигурации."

# Verification is deliberately non-destructive.
VERIFY="$(dirname "$0")/verify.sh"
if [[ -f "$VERIFY" ]]; then chmod 700 "$VERIFY"; fi

echo
echo "XFI AI OpenClaw integration configured."
echo "Config: $CONFIG"
echo "Env:    $ENV"
echo "Heartbeat: $WORKSPACE/HEARTBEAT.md"
echo "Cron: vpn-heal */10, hourly-check hourly, morning-report 09:00"
echo "Next: openclaw pairing list telegram"
echo "Then: openclaw pairing approve telegram <CODE>"
echo "Verify: bash $VERIFY"
