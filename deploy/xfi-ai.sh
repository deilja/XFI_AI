#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR="${XFI_AI_DIR:-/opt/xfi-ai}"; ENV_DIR=/etc/xfi-ai; ENV_FILE="$ENV_DIR/xfi-ai.env"; SERVICE=xfi-ai; PORT_FILE="$ENV_DIR/port"; REPO="${XFI_AI_REPO:-https://github.com/deilja/XFI_AI.git}"
[[ $EUID -eq 0 ]] || { echo 'Запустите от root'; exit 1; }
log(){ printf '\n==> %s\n' "$*"; }
free_port(){ for p in $(seq 8091 8199); do ! ss -ltnH | awk '{print $4}' | grep -Eq "(^|:)${p}$" && { echo "$p"; return; }; done; echo 0; }
read_env(){ [[ -f "$ENV_FILE" ]] && set -a && . "$ENV_FILE" && set +a || true; }
write_env(){ umask 077; mkdir -p "$ENV_DIR" /var/lib/xfi-ai; touch "$ENV_FILE"; chmod 600 "$ENV_FILE"; }
configure(){
 read_env; write_env
 DOMAIN="${DOMAIN:-}"; if [[ -z "$DOMAIN" ]]; then read -r -p "Домен: " DOMAIN; fi
 [[ "$DOMAIN" =~ ^[A-Za-z0-9.-]+$ ]] || { echo 'Некорректный домен'; exit 1; }; echo "$DOMAIN" > "$ENV_DIR/domain"
 PORT="${XFI_AI_PORT:-}"; [[ "$PORT" =~ ^[0-9]+$ ]] || PORT=$(free_port); [[ "$PORT" != 0 ]] || { echo 'Нет свободного порта'; exit 1; }; echo "$PORT" > "$PORT_FILE"
 declare -A labels=( [GROQ_API_KEY]=GROQ [GEMINI_API_KEY]=Gemini [OPENROUTER_API_KEY]=OpenRouter [MISTRAL_API_KEY]=Mistral [SAMBANOVA_API_KEY]=SambaNova [CEREBRAS_API_KEY]=Cerebras [HF_TOKEN]=HuggingFace [COHERE_API_KEY]=Cohere [CLOUDFLARE_API_TOKEN]=Cloudflare )
 for var in "${!labels[@]}"; do if [[ -z "${!var:-}" ]]; then read -r -s -p "${labels[$var]} API key (Enter=пропустить): " value; echo; [[ -n "$value" ]] && { printf '%s=%s\n' "$var" "$value" >> "$ENV_FILE"; export "$var=$value"; }; fi; done
 if [[ -n "${CLOUDFLARE_API_TOKEN:-}" && -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]]; then read -r -p 'Cloudflare Account ID: ' v; printf 'CLOUDFLARE_ACCOUNT_ID=%s\n' "$v" >> "$ENV_FILE"; fi
 if ! grep -q '^XFI_AI_ADMIN_KEY=' "$ENV_FILE"; then printf 'XFI_AI_ADMIN_KEY=%s\n' "$(openssl rand -hex 32)" >> "$ENV_FILE"; fi
 if ! grep -q '^XFI_AI_KEY_PEPPER=' "$ENV_FILE"; then printf 'XFI_AI_KEY_PEPPER=%s\n' "$(openssl rand -hex 32)" >> "$ENV_FILE"; fi
 grep -q '^XFI_AI_DB=' "$ENV_FILE" || echo 'XFI_AI_DB=/var/lib/xfi-ai/keys.db' >> "$ENV_FILE"
 grep -q '^XFI_AI_PROVIDERS=' "$ENV_FILE" || echo 'XFI_AI_PROVIDERS=groq,gemini,cloudflare,openrouter,mistral,sambanova,cerebras,huggingface,cohere' >> "$ENV_FILE"
}
install(){
 log 'Установка/переустановка без потери конфигурации'; apt-get update; DEBIAN_FRONTEND=noninteractive apt-get install -y git python3 python3-venv python3-pip nginx certbot python3-certbot-nginx openssl curl
 mkdir -p "$ENV_DIR" /var/lib/xfi-ai
 if [[ -d "$APP_DIR/.git" ]]; then git -C "$APP_DIR" fetch origin && git -C "$APP_DIR" reset --hard origin/main; else git clone "$REPO" "$APP_DIR"; fi
 id xfi-ai >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin xfi-ai
 configure; python3 -m venv "$APP_DIR/venv"; "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"
 chown -R xfi-ai:xfi-ai "$APP_DIR" /var/lib/xfi-ai
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
server { listen 80; server_name $DOMAIN; client_max_body_size 2m; location / { proxy_pass http://127.0.0.1:$PORT; proxy_http_version 1.1; proxy_set_header Host \$host; proxy_set_header X-Real-IP \$remote_addr; proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto \$scheme; proxy_buffering off; proxy_read_timeout 130s; } }
EOF
 ln -sfn /etc/nginx/sites-available/$SERVICE /etc/nginx/sites-enabled/$SERVICE; rm -f /etc/nginx/sites-enabled/default; nginx -t; systemctl daemon-reload; systemctl enable --now "$SERVICE"; systemctl reload nginx
 if getent ahostsv4 "$DOMAIN" >/dev/null; then certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "admin@$DOMAIN" --redirect || true; fi
 systemctl restart "$SERVICE"; show_info
}
update(){ [[ -d "$APP_DIR/.git" ]] || { echo 'Не установлено'; exit 1; }; read_env; git -C "$APP_DIR" fetch origin; git -C "$APP_DIR" reset --hard origin/main; "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"; systemctl restart "$SERVICE"; nginx -t && systemctl reload nginx; }
show_info(){ read_env; echo; echo "Сайт: https://${DOMAIN:-$(cat "$ENV_DIR/domain" 2>/dev/null || echo '?')}"; echo "API:  https://${DOMAIN:-?}/v1"; echo "Порт: ${XFI_AI_PORT:-$(cat "$PORT_FILE" 2>/dev/null || echo '?')}"; echo 'Admin key хранится в /etc/xfi-ai/xfi-ai.env'; }
status(){ systemctl --no-pager --full status "$SERVICE" || true; [[ -f "$PORT_FILE" ]] && curl -fsS "http://127.0.0.1:$(cat "$PORT_FILE")/health" || true; }
logs(){ journalctl -u "$SERVICE" -n 100 --no-pager; }
uninstall(){ read -r -p 'Удалить приложение и конфигурацию? [yes/NO]: ' a; [[ "$a" == yes ]] || exit; systemctl disable --now "$SERVICE" || true; rm -f /etc/systemd/system/$SERVICE.service /etc/nginx/sites-enabled/$SERVICE /etc/nginx/sites-available/$SERVICE; systemctl daemon-reload; rm -rf "$APP_DIR" "$ENV_DIR"; rm -rf /var/lib/xfi-ai; userdel xfi-ai 2>/dev/null || true; nginx -t && systemctl reload nginx || true; }
menu(){ while true; do echo; echo 'XFI AI Manager'; echo '1) Install / Repair'; echo '2) Update'; echo '3) Status'; echo '4) Logs'; echo '5) Restart'; echo '6) Stop'; echo '7) Start'; echo '8) Show config info'; echo '9) Uninstall'; echo '0) Exit'; read -r -p '> ' n; case $n in 1)install;;2)update;;3)status;;4)logs;;5)systemctl restart "$SERVICE";;6)systemctl stop "$SERVICE";;7)systemctl start "$SERVICE";;8)show_info;;9)uninstall;;0)exit;;*)echo 'Неверный выбор';;esac; done; }
case "${1:-menu}" in install)install;;update)update;;status)status;;logs)logs;;restart)systemctl restart "$SERVICE";;stop)systemctl stop "$SERVICE";;start)systemctl start "$SERVICE";;uninstall)uninstall;;*)menu;;esac
