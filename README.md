# XFI AI

Мульти-AI Gateway и control-plane для экосистемы XFI. Клиент подключается к вашему HTTPS-домену, использует единый `xfi_...` API key, а XFI AI выбирает AI-провайдера и выполняет failover при временных ошибках.

## Статус

- Production preflight: готов.
- GitHub Actions: `CI` — SUCCESS, `Gateway CI` — SUCCESS.
- Последний проверенный commit: `07a1efb1426e7585e4a4c0d4cdd6cd2aa1d920fb`.
- Runtime: Python 3.11+, FastAPI, Uvicorn, HTTPX.

## Архитектура

```text
Telegram
   │ pairing
   ▼
OpenClaw Gateway
   │
   ├── RouterAI → Claude / DeepSeek
   └── Groq → GPT-OSS
   │
   ▼
XFI AI Gateway
   ├── AI providers + failover
   ├── Client API keys
   ├── VPS Control Center
   ├── Audit log
   └── Web Admin
   │
   ├── 3X-UI / X-UI
   ├── Xray
   ├── nginx
   ├── Docker
   └── YadrenoVPN
```

## AI-провайдеры

Gateway поддерживает:

- Groq
- Google Gemini
- Cloudflare AI
- OpenRouter
- Mistral
- SambaNova
- Cerebras
- Hugging Face
- Cohere

Порядок failover задаётся переменной `XFI_AI_PROVIDERS`.

RouterAI используется OpenClaw отдельно как основной control-plane provider и не заменяет providers Gateway.

## Автоматическое определение API key

Web Admin поддерживает проверку неизвестного AI API key:

1. ключ вводится через защищённую административную страницу;
2. XFI AI проверяет его против поддерживаемых providers;
3. определяется совместимый provider и модель;
4. показываются только безопасные метаданные: статус, provider, модель, latency и короткий fingerprint;
5. полный ключ не сохраняется функцией автоопределения.

Для Cloudflare дополнительно требуется `CLOUDFLARE_ACCOUNT_ID`.

## API

```text
GET  /health
GET  /v1/models
POST /v1/chat/completions

GET  /api/keys
POST /api/keys
...
```

Клиент использует один `xfi_...` ключ. Реальные API keys AI-провайдеров клиенту не выдаются.

Для `/v1/chat/completions` применяются ограничения размера запроса и безопасная обработка ошибок upstream.

## Web Admin

Web Admin предоставляет:

- создание, активацию и деактивацию XFI client keys;
- автоматическое определение AI provider по API key;
- метрики providers;
- добавление VPS;
- диагностику VPS;
- безопасный restart разрешённых сервисов;
- список Docker containers;
- audit log;
- локальный мониторинг сервисов.

Административный доступ защищён отдельным `XFI_AI_ADMIN_KEY`.

## VPS Control Center

Для SSH разрешены только два режима:

- `key` — путь к существующему приватному ключу на VPS;
- `agent` — системный SSH agent.

SSH-пароли не принимаются и не сохраняются.

Валидация ограничивает host, port, username и путь к ключу. Удалённые команды не принимаются от пользователя как произвольная shell-строка.

Разрешённый restart allowlist:

```text
x-ui
3x-ui
xray
nginx
docker
```

Произвольные команды, shell injection и изменение VPN-конфигурации через VPS Control Center запрещены. Диагностика и restart записываются в audit log.

## OpenClaw + Telegram

OpenClaw используется как отдельный control-plane для диагностики и безопасного обслуживания VPS.

### Установка

```bash
cd /opt/XFI_AI/openclaw
chmod +x install.sh xfi-vpn-heal.sh
./install.sh
```

Установщик:

- устанавливает OpenClaw, если команда отсутствует;
- запрашивает RouterAI API key, Groq API key и Telegram Bot Token;
- сохраняет секреты в `~/.openclaw/.env` с правами `600`;
- добавляет RouterAI и Groq как OpenAI-compatible providers;
- задаёт primary `routerai/anthropic/claude-sonnet-4-5`;
- задаёт fallback `groq/openai/gpt-oss-120b` и `routerai/deepseek/deepseek-chat`;
- включает Telegram `dmPolicy: pairing`;
- устанавливает heartbeat и безопасный workspace.

Полные команды, pairing, cron и troubleshooting: `openclaw/CRON.md`.

### Telegram pairing

```bash
openclaw pairing list telegram
openclaw pairing approve telegram <КОД>
```

Telegram-доступ не открывается для неизвестных пользователей без pairing.

## Auto-heal

`openclaw/HEARTBEAT.md` и `openclaw/xfi-vpn-heal.sh` используют консервативную модель восстановления:

1. проверить состояние;
2. определить существующий проблемный сервис;
3. выполнить не более одного безопасного restart;
4. повторно проверить состояние;
5. сообщить результат в Telegram при исправлении или ошибке.

Автоматически запрещено:

- удалять пользователей, inbound и ключи;
- менять порты;
- менять TLS или Reality;
- менять firewall или DNS;
- редактировать БД 3X-UI/X-UI;
- удалять Docker volumes/containers;
- обновлять Xray/3X-UI;
- отключать UFW/Fail2Ban;
- выполнять массовые destructive-команды.

Host-проверка вручную:

```bash
sudo bash /opt/XFI_AI/openclaw/xfi-vpn-heal.sh
```

## Production preflight

Перед установкой можно выполнить read-only проверку репозитория и окружения:

```bash
bash deploy/preflight.sh
```

Скрипт проверяет:

- Ubuntu и Python;
- обязательные команды;
- структуру проекта;
- Python compile check;
- весь `pytest` suite;
- nginx configuration;
- systemd service;
- локальный порт;
- наличие Let's Encrypt directory.

Успешный результат заканчивается:

```text
PREFLIGHT: READY
```

При обязательной ошибке:

```text
PREFLIGHT: FAILED
```

## Установка XFI AI

```bash
git clone https://github.com/deilja/XFI_AI.git
cd XFI_AI
bash deploy/preflight.sh
chmod +x deploy/install.sh
sudo ./deploy/install.sh
```

Установщик:

- запрашивает домен;
- определяет публичный IPv4;
- предлагает свободный локальный порт;
- принимает API keys providers через скрытый ввод;
- позволяет задать порядок providers;
- создаёт `xfi-ai` system user;
- создаёт Python venv;
- устанавливает зависимости;
- создаёт systemd service;
- настраивает nginx reverse proxy;
- настраивает HTTPS через Certbot при корректном DNS;
- создаёт `/etc/xfi-ai/xfi-ai.env` с правами `600`;
- создаёт административный ключ, если он не задан вручную;
- выполняет локальный `/health` smoke check.

### Основные пути после установки

```text
/opt/xfi-ai/
/etc/xfi-ai/xfi-ai.env
/var/lib/xfi-ai/keys.db
/etc/systemd/system/xfi-ai.service
/etc/nginx/sites-available/xfi-ai
```

## Переменные окружения

Минимальный пример находится в `.env.example`.

Основные параметры:

```env
GROQ_API_KEY=
GEMINI_API_KEY=
CLOUDFLARE_API_TOKEN=
CLOUDFLARE_ACCOUNT_ID=
OPENROUTER_API_KEY=
MISTRAL_API_KEY=
SAMBANOVA_API_KEY=
CEREBRAS_API_KEY=
HF_TOKEN=
COHERE_API_KEY=

ROUTERAI_API_KEY=
TELEGRAM_BOT_TOKEN=
OPENCLAW_HEARTBEAT=15m

XFI_AI_PROVIDERS=groq,gemini,cloudflare,openrouter,mistral,sambanova,cerebras,huggingface,cohere

XFI_AI_ADMIN_KEY=
XFI_AI_DB=/var/lib/xfi-ai/keys.db
XFI_AI_KEY_PEPPER=
```

Конкретные модели можно переопределить через `*_MODEL`. Полный пример находится в `.env.example`.

## Systemd и права

Production service запускается не от root, а от пользователя `xfi-ai`. Для systemd включены ограничения:

- `NoNewPrivileges=true`
- `PrivateTmp=true`
- `ProtectSystem=strict`
- `ProtectHome=true`
- запись только в `/var/lib/xfi-ai`

Uvicorn слушает localhost, внешний доступ выполняет nginx.

## Безопасность

- Реальные AI keys находятся только на VPS.
- Секреты не должны попадать в Git.
- `.env`, Telegram token, RouterAI/Groq keys и admin key нельзя публиковать.
- SSH password authentication для VPS Control Center отключена.
- API credentials ограничиваются по размеру и проверяются безопасно.
- Admin key сравнивается constant-time.
- OpenClaw использует fixed command allowlists для административных операций.
- Restart разрешён только для заранее определённых сервисов.
- Аудит административных операций сохраняется в SQLite.

## Тестирование

Локальный запуск тестов:

```bash
python3 -m pytest -q tests
```

Проверка синтаксиса приложения:

```bash
python3 -m compileall -q app
```

Production preflight:

```bash
bash deploy/preflight.sh
```

GitHub Actions автоматически проверяет проект. Последний production-preflight commit прошёл оба workflow: `CI` и `Gateway CI`.

## Операционные команды OpenClaw

```bash
openclaw gateway status
openclaw gateway restart
openclaw models list
openclaw models set routerai/anthropic/claude-sonnet-4-5
openclaw pairing list telegram
openclaw cron list
openclaw system heartbeat last
journalctl -u openclaw -f
```

Подробная эксплуатационная документация: `openclaw/CRON.md`.

## Лицензия

Проект развивается как часть экосистемы XFI. Лицензионные условия следует проверять в текущем состоянии репозитория.
