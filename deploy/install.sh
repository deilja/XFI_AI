#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR="/opt/xfi-ai"; ENV_DIR="/etc/xfi-ai"; ENV_FILE="$ENV_DIR/xfi-ai.env"; SERVICE="xfi-ai"; DEFAULT_PORT=8091
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
trap 'echo "[ERROR] Строка $LINENO: установка остановлена." >&2' ERR
[[ $EUID -eq 0 ]] || { echo "Запустите от root: sudo bash deploy/install.sh"; exit 1; }
say(){ printf '\n==> %s\n' "$*"; }; fail(){ echo "[ERROR] $*" >&2; exit 1; }
valid_domain(){ [[ "$1" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ && "$1" != *..* ]]; }
port_free(){ ! ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq "(:|\\])$1$"; }
find_port(){ local p; for p in $(seq "$DEFAULT_PORT" 8199); do port_free "$p" && { echo "$p"; return; }; done; fail "Нет свободного порта 8091-8199."; }
validate_provider_order(){
  local item
  [[ -n "$1" ]] || return 1
  IFS=',' read -ra items <<< "$1"
  for item in "${items[@]}"; do
    [[ "$item" =~ ^(groq|gemini|openrouter|mistral|sambanova|cerebras|huggingface|cohere)$ ]] || return 1
  done
}

say "XFI AI Gateway — Multi-AI установка"
[[ -r /etc/os-release ]] && . /etc/os-release || true
read -rp "Домен для XFI AI: " DOMAIN; DOMAIN="${DOMAIN,,}"; valid_domain "$DOMAIN" || fail "Некорректный домен."
PUBLIC_IP="$(curl -4fsS --max-time 5 https://api.ipify.org 2>/dev/null || true)"
echo "VPS IPv4: ${PUBLIC_IP:-не определён}"
SUGGESTED_PORT="$(find_port)"; echo "Предложенный свободный локальный порт: $SUGGESTED_PORT"
read -rp "Порт XFI AI [Enter = $SUGGESTED_PORT]: " PORT; PORT="${PORT:-$SUGGESTED_PORT}"
[[ "$PORT" =~ ^[0-9]+$ && "$PORT" -ge 1024 && "$PORT" -le 65535 ]] || fail "Порт должен быть 1024-65535."; port_free "$PORT" || fail "Порт занят."

say "AI-провайдеры"
echo "Пустой ключ отключает провайдера."
read -rsp "Groq API key: " GROQ_KEY; echo
read -rsp "Google Gemini API key: " GEMINI_KEY; echo
read -rsp "OpenRouter API key: " OPENROUTER_KEY; echo
read -rsp "Mistral API key: " MISTRAL_KEY; echo
read -rsp "SambaNova API key: " SAMBANOVA_KEY; echo
read -rsp "Cerebras API key: " CEREBRAS_KEY; echo
read -rsp "Hugging Face token: " HF_KEY; echo
read -rsp "Cohere API key: " COHERE_KEY; echo
[[ -n "$GROQ_KEY$GEMINI_KEY$OPENROUTER_KEY$MISTRAL_KEY$SAMBANOVA_KEY$CEREBRAS_KEY$HF_KEY$COHERE_KEY" ]] || fail "Нужен хотя бы один AI provider."
PROVIDERS=""; addp(){ [[ -n "$2" ]] && PROVIDERS="${PROVIDERS:+$PROVIDERS,}$1"; }; addp groq "$GROQ_KEY"; addp gemini "$GEMINI_KEY"; addp openrouter "$OPENROUTER_KEY"; addp mistral "$MISTRAL_KEY"; addp sambanova "$SAMBANOVA_KEY"; addp cerebras "$CEREBRAS_KEY"; addp huggingface "$HF_KEY"; addp cohere "$COHERE_KEY"
echo "Порядок failover: $PROVIDERS"; read -rp "Изменить порядок? [Enter = оставить]: " CUSTOM; PROVIDERS="${CUSTOM:-$PROVIDERS}"
validate_provider_order "$PROVIDERS" || fail "Некорректный порядок провайдеров. Разрешены: groq,gemini,openrouter,mistral,sambanova,cerebras,huggingface,cohere."
read -rsp "Админ-ключ [Enter = сгенерировать]: " ADMIN_KEY; echo; ADMIN_KEY="${ADMIN_KEY:-$(openssl rand -hex 32)}"; [[ ${#ADMIN_KEY} -ge 24 ]] || fail "Админ-ключ слишком короткий."
PEPPER="$(openssl rand -hex 32)"

say "Пакеты"; export DEBIAN_FRONTEND=noninteractive; apt-get update; apt-get install -y python3 python3-venv python3-pip nginx curl openssl ca-certificates certbot python3-certbot-nginx
say "Приложение"; id xfi-ai >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin xfi-ai; install -d -o xfi-ai -g xfi-ai "$APP_DIR" "$ENV_DIR" /var/lib/xfi-ai
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"; [[ -f "$REPO_ROOT/app/api.py" && -f "$REPO_ROOT/app/providers.py" ]] || fail "Запускайте скрипт из клонированного XFI_AI."
cp -a "$REPO_ROOT"/. "$APP_DIR/"; chown -R xfi-ai:xfi-ai "$APP_DIR" /var/lib/xfi-ai; runuser -u xfi-ai -- python3 -m venv "$APP_DIR/venv"; "$APP_DIR/venv/bin/pip" install --upgrade pip; "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

say "Секреты"; umask 077; cat > "$ENV_FILE" <<EOF
GROQ_API_KEY=$GROQ_KEY
GEMINI_API_KEY=$GEMINI_KEY
OPENROUTER_API_KEY=$OPENROUTER_KEY
MISTRAL_API_KEY=$MISTRAL_KEY
SAMBANOVA_API_KEY=$SAMBANOVA_KEY
CEREBRAS_API_KEY=$CEREBRAS_KEY
HF_TOKEN=$HF_KEY
COHERE_API_KEY=$COHERE_KEY
XFI_AI_PROVIDERS=$PROVIDERS
GROQ_MODEL=openai/gpt-oss-120b
GEMINI_MODEL=gemini-2.5-flash
OPENROUTER_MODEL=openrouter/free
MISTRAL_MODEL=mistral-small-latest
SAMBANOVA_MODEL=Meta-Llama-3.3-70B-Instruct
CEREBRAS_MODEL=gpt-oss-120b
HF_MODEL=openai/gpt-oss-120b:fastest
COHERE_MODEL=command-a-03-2025
XFI_AI_REFERER=https://$DOMAIN
XFI_AI_ADMIN_KEY=$ADMIN_KEY
XFI_AI_DB=/var/lib/xfi-ai/keys.db
XFI_AI_KEY_PEPPER=$PEPPER
EOF
unset GROQ_KEY GEMINI_KEY OPENROUTER_KEY MISTRAL_KEY SAMBANOVA_KEY CEREBRAS_KEY HF_KEY COHERE_KEY; chmod 600 "$ENV_FILE"; chown root:xfi-ai "$ENV_FILE"

say "Systemd"; cat > /etc/systemd/system/$SERVICE.service <<EOF
[Unit]
Description=XFI AI Gateway Multi-Provider
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
User=xfi-ai
Group=xfi-ai
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$APP_DIR/venv/bin/uvicorn app.api:app --host 127.0.0.1 --port $PORT --proxy-headers
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/xfi-ai
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload; systemctl enable --now "$SERVICE"; sleep 2; systemctl is-active --quiet "$SERVICE" || { journalctl -u "$SERVICE" -n 50 --no-pager; fail "XFI AI не запустился."; }

say "Nginx"; cat > /etc/nginx/sites-available/xfi-ai.conf <<EOF
server {
 listen 80;
 server_name $DOMAIN;
 client_max_body_size 2m;
 proxy_read_timeout 130s;
 proxy_send_timeout 130s;
 add_header X-Content-Type-Options "nosniff" always;
 add_header X-Frame-Options "DENY" always;
 add_header Referrer-Policy "no-referrer" always;
 add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
 location / {
  proxy_pass http://127.0.0.1:$PORT;
  proxy_http_version 1.1;
  proxy_set_header Host \$host;
  proxy_set_header X-Real-IP \$remote_addr;
  proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto \$scheme;
  proxy_buffering off;
 }
}
EOF
ln -sfn /etc/nginx/sites-available/xfi-ai.conf /etc/nginx/sites-enabled/xfi-ai.conf; rm -f /etc/nginx/sites-enabled/default; nginx -t; systemctl reload nginx

say "DNS и HTTPS"; DOMAIN_IP="$(getent ahostsv4 "$DOMAIN" 2>/dev/null | awk 'NR==1{print $1}')"; echo "DNS: ${DOMAIN_IP:-не найден} | VPS: ${PUBLIC_IP:-не определён}"
if [[ -n "$PUBLIC_IP" && "$DOMAIN_IP" == "$PUBLIC_IP" ]]; then certbot --nginx --non-interactive --agree-tos --register-unsafely-without-email -d "$DOMAIN" --redirect || echo "Certbot не получил сертификат."; else echo "Сначала направьте A-запись $DOMAIN на $PUBLIC_IP, затем: certbot --nginx -d $DOMAIN --redirect"; fi
say "Проверка"; curl -fsS --max-time 5 "http://127.0.0.1:$PORT/health"; echo; echo "Установка завершена: https://$DOMAIN/"; echo "API: https://$DOMAIN/v1/chat/completions"; echo "Порт: 127.0.0.1:$PORT"; echo "Админ-ключ: $ADMIN_KEY"; echo "Секреты: $ENV_FILE"
