#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="/opt/xfi-ai"
ENV_DIR="/etc/xfi-ai"
ENV_FILE="$ENV_DIR/xfi-ai.env"
SERVICE="xfi-ai"
DEFAULT_PORT=8091
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

trap 'echo "[ERROR] Строка $LINENO: установка остановлена." >&2' ERR

if [[ $EUID -ne 0 ]]; then echo "Запустите от root: sudo bash deploy/install.sh"; exit 1; fi
say(){ printf '\n==> %s\n' "$*"; }
fail(){ echo "[ERROR] $*" >&2; exit 1; }
valid_domain(){ [[ "$1" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ && "$1" != *..* ]]; }
port_free(){ ! ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq "(:|\\])$1$"; }
find_port(){ local p; for p in $(seq "$DEFAULT_PORT" 8199); do port_free "$p" && { echo "$p"; return; }; done; fail "Не найден свободный порт 8091-8199."; }

say "XFI AI Gateway — установка"
[[ -r /etc/os-release ]] && . /etc/os-release || true
[[ "${ID:-}" == "ubuntu" || "${ID_LIKE:-}" == *debian* ]] || echo "Предупреждение: скрипт рассчитан на Ubuntu/Debian."

read -rp "Домен для XFI AI (например ai.deilja.online): " DOMAIN
DOMAIN="${DOMAIN,,}"
valid_domain "$DOMAIN" || fail "Некорректное доменное имя."
PUBLIC_IP="$(curl -4fsS --max-time 5 https://api.ipify.org 2>/dev/null || true)"
[[ -z "$PUBLIC_IP" ]] || echo "IPv4 VPS: $PUBLIC_IP | DNS должен указывать $DOMAIN -> $PUBLIC_IP"
read -rp "Продолжить? [Y/n]: " OK
[[ "${OK:-Y}" =~ ^([YyДд]|)$ ]] || exit 0

SUGGESTED_PORT="$(find_port)"
echo "Свободный локальный порт: $SUGGESTED_PORT"
read -rp "Порт XFI AI [Enter = $SUGGESTED_PORT]: " PORT
PORT="${PORT:-$SUGGESTED_PORT}"
[[ "$PORT" =~ ^[0-9]+$ && "$PORT" -ge 1024 && "$PORT" -le 65535 ]] || fail "Порт должен быть 1024-65535."
port_free "$PORT" || fail "Порт $PORT уже занят."

read -rsp "GROQ_API_KEY: " GROQ_KEY; echo
[[ "$GROQ_KEY" == gsk_* && ${#GROQ_KEY} -ge 20 ]] || fail "Ожидается Groq key формата gsk_..."
read -rsp "Админ-ключ [Enter = сгенерировать]: " ADMIN_KEY; echo
ADMIN_KEY="${ADMIN_KEY:-$(openssl rand -hex 32)}"
[[ ${#ADMIN_KEY} -ge 24 ]] || fail "Админ-ключ слишком короткий."
PEPPER="$(openssl rand -hex 32)"

say "Установка пакетов"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-venv python3-pip nginx curl openssl ca-certificates

say "Подготовка приложения"
id xfi-ai >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin xfi-ai
install -d -o xfi-ai -g xfi-ai "$APP_DIR" "$ENV_DIR" /var/lib/xfi-ai
if [[ ! -f "$APP_DIR/app/api.py" ]]; then
  REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
  [[ -f "$REPO_ROOT/requirements.txt" && -f "$REPO_ROOT/app/api.py" ]] || fail "Исходники XFI_AI не найдены. Запускайте из deploy/ клонированного репозитория."
  cp -a "$REPO_ROOT"/. "$APP_DIR/"
fi
chown -R xfi-ai:xfi-ai "$APP_DIR" /var/lib/xfi-ai
sudo -u xfi-ai python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

say "Секреты"
cat > "$ENV_FILE" <<EOF
GROQ_API_KEY=$GROQ_KEY
XFI_AI_ADMIN_KEY=$ADMIN_KEY
XFI_AI_DB=/var/lib/xfi-ai/keys.db
XFI_AI_KEY_PEPPER=$PEPPER
EOF
unset GROQ_KEY
chmod 600 "$ENV_FILE"
chown root:xfi-ai "$ENV_FILE"

say "Systemd"
cat > /etc/systemd/system/$SERVICE.service <<EOF
[Unit]
Description=XFI AI Gateway
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
systemctl daemon-reload
systemctl enable --now "$SERVICE"
sleep 2
systemctl is-active --quiet "$SERVICE" || { journalctl -u "$SERVICE" -n 50 --no-pager; fail "XFI AI не запустился."; }

say "Nginx"
cat > /etc/nginx/sites-available/xfi-ai.conf <<EOF
server {
    listen 80;
    server_name $DOMAIN;
    client_max_body_size 2m;
    proxy_read_timeout 130s;
    proxy_send_timeout 130s;
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
ln -sfn /etc/nginx/sites-available/xfi-ai.conf /etc/nginx/sites-enabled/xfi-ai.conf
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

say "Проверка DNS"
DOMAIN_IP="$(getent ahostsv4 "$DOMAIN" 2>/dev/null | awk 'NR==1{print $1}')"
if [[ -n "$PUBLIC_IP" && "$DOMAIN_IP" != "$PUBLIC_IP" ]]; then
  echo "DNS пока не указывает на VPS: $DOMAIN -> ${DOMAIN_IP:-не найден}, VPS -> $PUBLIC_IP"
  echo "После исправления DNS выполните: apt-get install -y certbot python3-certbot-nginx && certbot --nginx -d $DOMAIN --redirect"
else
  say "HTTPS"
  apt-get install -y certbot python3-certbot-nginx
  certbot --nginx --non-interactive --agree-tos --register-unsafely-without-email -d "$DOMAIN" --redirect || echo "Certbot не смог получить сертификат; HTTP остаётся доступен."
fi

say "Проверка"
curl -fsS --max-time 5 "http://127.0.0.1:$PORT/health" || fail "Health-check не прошёл."
chmod 600 "$ENV_FILE"
echo
echo "Установка завершена."
echo "Сайт: https://$DOMAIN/"
echo "API:   https://$DOMAIN/v1/chat/completions"
echo "Порт:  127.0.0.1:$PORT"
echo "Админ-ключ: $ADMIN_KEY"
echo "Секреты: $ENV_FILE"
