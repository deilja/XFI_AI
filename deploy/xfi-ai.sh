#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${XFI_AI_DIR:-/opt/xfi-ai}"
ENV_DIR="/etc/xfi-ai"
ENV_FILE="$ENV_DIR/xfi-ai.env"
SERVICE="xfi-ai"
PORT_FILE="$ENV_DIR/port"
REPO="${XFI_AI_REPO:-https://github.com/deilja/XFI_AI.git}"

[[ $EUID -eq 0 ]] || { echo 'Запустите от root: sudo bash deploy/xfi-ai.sh'; exit 1; }

log(){ printf '\n==> %s\n' "$*"; }
press(){ read -r -p 'Enter для продолжения...' _ || true; }

free_port(){
  for p in $(seq 8091 8199); do
    if ! ss -ltnH | awk '{print $4}' | grep -Eq "(^|:)${p}$"; then echo "$p"; return; fi
  done
  echo 0
}

install(){
  log 'Установка XFI AI'
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y git python3 python3-venv python3-pip nginx certbot python3-certbot-nginx openssl curl
  mkdir -p "$ENV_DIR" /var/lib/xfi-ai
  if [[ -d "$APP_DIR/.git" ]]; then git -C "$APP_DIR" fetch --all && git -C "$APP_DIR" reset --hard origin/main
  else git clone "$REPO" "$APP_DIR"; fi
  id xfi-ai >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin xfi-ai
  python3 -m venv "$APP_DIR/venv"
  "$APP_DIR/venv/bin/pip" install --upgrade pip
  "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"
  PORT=$(free_port); [[ "$PORT" != 0 ]] || { echo 'Свободный порт 8091-8199 не найден'; exit 1; }
  echo "$PORT" > "$PORT_FILE"
  read -r -p "Домен (например ai.example.com): " DOMAIN
  [[ "$DOMAIN" =~ ^[A-Za-z0-9.-]+$ ]] || { echo 'Некорректный домен'; exit 1; }
  read -r -s -p 'GROQ_API_KEY (Enter если пока нет): ' GROQ; echo
  read -r -s -p 'GEMINI_API_KEY (Enter если пока нет): ' GEMINI; echo
  read -r -s -p 'OPENROUTER_API_KEY (Enter если пока нет): ' OR; echo
  read -r -s -p 'MISTRAL_API_KEY (Enter если пока нет): ' MIS; echo
  read -r -s -p 'SAMBANOVA_API_KEY (Enter если пока нет): ' SAMBA; echo
  read -r -s -p 'CEREBRAS_API_KEY (Enter если пока нет): ' CER; echo
  read -r -s -p 'HF_TOKEN (Enter если пока нет): ' HF; echo
  read -r -s -p 'COHERE_API_KEY (Enter если пока нет): ' COH; echo
  read -r -s -p 'CLOUDFLARE_API_TOKEN (Enter если пока нет): ' CF; echo
  if [[ -n "$CF" ]]; then read -r -p 'CLOUDFLARE_ACCOUNT_ID: ' CFA; else CFA=''; fi
  ADMIN=$(openssl rand -hex 32); PEPPER=$(openssl rand -hex 32)
  cat > "$ENV_FILE" <<EOF
GROQ_API_KEY=$GROQ
GEMINI_API_KEY=$GEMINI
OPENROUTER_API_KEY=$OR
MISTRAL_API_KEY=$MIS
SAMBANOVA_API_KEY=$SAMBA
CEREBRAS_API_KEY=$CER
HF_TOKEN=$HF
COHERE_API_KEY=$COH
CLOUDFLARE_API_TOKEN=$CF
CLOUDFLARE_ACCOUNT_ID=$CFA
XFI_AI_ADMIN_KEY=$ADMIN
XFI_AI_KEY_PEPPER=$PEPPER
XFI_AI_DB=/var/lib/xfi-ai/keys.db
XFI_AI_PORT=$PORT
XFI_AI_PROVIDERS=groq,gemini,cloudflare,openrouter,mistral,sambanova,cerebras,huggingface,cohere
EOF
  chmod 600 "$ENV_FILE"; chown -R xfi-ai:xfi-ai "$APP_DIR" /var/lib/xfi-ai
  cat > /etc/systemd/system/$SERVICE.service <<EOF
[Unit]
Description=XFI AI Gateway
After=network-online.target
Wants=network-online.target
[Service]
User=xfi-ai
Group=xfi-ai
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$APP_DIR/venv/bin/uvicorn app.api:app --host 127.0.0.1 --port $PORT
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
  cat > /etc/nginx/sites-available/$SERVICE <<EOF
server {
 listen 80;
 server_name $DOMAIN;
 location / { proxy_pass http://127.0.0.1:$PORT; proxy_http_version 1.1; proxy_set_header Host \$host; proxy_set_header X-Real-IP \$remote_addr; proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto \$scheme; proxy_buffering off; proxy_read_timeout 130s; client_max_body_size 2m; }
}
EOF
  ln -sfn /etc/nginx/sites-available/$SERVICE /etc/nginx/sites-enabled/$SERVICE
  rm -f /etc/nginx/sites-enabled/default
  nginx -t && systemctl daemon-reload && systemctl enable --now "$SERVICE" && systemctl reload nginx
  echo "$DOMAIN" > "$ENV_DIR/domain"
  if getent ahostsv4 "$DOMAIN" >/dev/null; then certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "admin@$DOMAIN" --redirect || true; fi
  systemctl restart "$SERVICE"
  echo; echo 'Установка завершена.'; echo "Сайт: https://$DOMAIN"; echo "API:  https://$DOMAIN/v1"; echo "Admin key: $ADMIN"; echo 'Сохраните Admin key.'
}

update(){
  log 'Обновление XFI AI'
  [[ -d "$APP_DIR/.git" ]] || { echo 'XFI AI не установлен'; exit 1; }
  git -C "$APP_DIR" fetch --all
  git -C "$APP_DIR" reset --hard origin/main
  "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"
  systemctl restart "$SERVICE"
  nginx -t && systemctl reload nginx
  systemctl --no-pager --full status "$SERVICE" || true
}

status(){ systemctl --no-pager --full status "$SERVICE" || true; echo; curl -fsS http://127.0.0.1:$(cat "$PORT_FILE")/health || true; }
logs(){ journalctl -u "$SERVICE" -n 100 --no-pager; }
uninstall(){ read -r -p 'Удалить XFI AI, Nginx-конфиг и сервис? [yes/NO]: ' a; [[ "$a" == yes ]] || exit 0; systemctl disable --now "$SERVICE" || true; rm -f /etc/systemd/system/$SERVICE.service /etc/nginx/sites-enabled/$SERVICE /etc/nginx/sites-available/$SERVICE; systemctl daemon-reload; systemctl reload nginx || true; rm -rf "$APP_DIR" "$ENV_DIR"; userdel xfi-ai 2>/dev/null || true; echo 'Удалено.'; }

case "${1:-menu}" in
 install) install;; update) update;; status) status;; logs) logs;; restart) systemctl restart "$SERVICE";; stop) systemctl stop "$SERVICE";; start) systemctl start "$SERVICE";; uninstall) uninstall;; menu)
  while true; do echo; echo 'XFI AI Manager'; echo '1) Установить'; echo '2) Обновить'; echo '3) Статус'; echo '4) Логи'; echo '5) Restart'; echo '6) Stop'; echo '7) Start'; echo '8) Удалить'; echo '0) Выход'; read -r -p '> ' n; case $n in 1) install;;2) update;;3)status;;4)logs;;5)systemctl restart "$SERVICE";;6)systemctl stop "$SERVICE";;7)systemctl start "$SERVICE";;8)uninstall;;0)exit 0;;*)echo 'Неверный выбор';;esac; done;; *) echo "Использование: $0 {install|update|status|logs|restart|stop|start|uninstall}"; exit 2;; esac
