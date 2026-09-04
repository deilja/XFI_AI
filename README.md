# XFI AI

AI Gateway и control-plane экосистемы XFI. Единый `xfi_...` API key, маршрутизация между AI-провайдерами, failover, административная панель, VPS Control Center и Telegram Code Agent для безопасного изменения кода XFI CONNECT через Pull Request.

## Что делает XFI AI

- единый API для нескольких AI-провайдеров;
- автоматический provider failover;
- выпуск и управление клиентскими `xfi_...` API keys;
- автоматическое определение provider по неизвестному API key;
- Web Admin для ключей, VPS и аудита;
- диагностика VPS и ограниченный безопасный restart разрешённых сервисов;
- OpenClaw control-plane для Telegram и auto-heal сценариев;
- Telegram Code Agent, который понимает обычные текстовые задачи и правит XFI CONNECT после уточняющих вопросов и подтверждения;
- работа Code Agent только через отдельную ветку и Pull Request.

## Статус

Production-ready компоненты проходят автоматические GitHub Actions проверки. Gateway и Code Agent покрываются тестами, lint и security checks.

## Архитектура

```text
                    ┌──────────────────────┐
                    │      XFI CLIENTS     │
                    │ XFI_CONNECT / /ai API│
                    └──────────┬───────────┘
                               │ xfi_ token
                               ▼
                    ┌──────────────────────┐
                    │    XFI AI Gateway    │
                    │ FastAPI + HTTPX      │
                    ├──────────────────────┤
                    │ key auth / limits    │
                    │ provider routing     │
                    │ failover / metrics   │
                    │ audit                │
                    └──────────┬───────────┘
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
        Groq                 Gemini             OpenRouter
          │                    │                    │
          └──────────── другие providers ──────────┘

 Telegram
    │
    ▼
XFI AI Code Agent
    │
    ├── анализ XFI_CONNECT
    ├── уточняющие вопросы
    ├── план изменений
    ├── подтверждение
    └── branch → commits → Pull Request → CI

 OpenClaw
    │
    └── диагностика и безопасное обслуживание VPS
```

## AI-провайдеры

Поддерживаются:

- Groq;
- Google Gemini;
- Cloudflare AI;
- OpenRouter;
- Mistral;
- SambaNova;
- Cerebras;
- Hugging Face;
- Cohere.

Порядок выбора настраивается через `XFI_AI_PROVIDERS`. Для каждого provider учитываются ошибки, cooldown и задержка ответа.

## Автоматическое определение API key

Web Admin может проверить неизвестный ключ:

1. ключ проверяется против поддерживаемых providers;
2. определяется подходящий provider и модель;
3. выводятся только безопасные метаданные: статус, provider, модель, latency и fingerprint;
4. полный ключ функцией автоопределения не сохраняется.

Для Cloudflare нужен `CLOUDFLARE_ACCOUNT_ID`.

## API

```text
GET  /health
GET  /v1/models
POST /v1/chat/completions
GET  /api/keys
POST /api/keys
```

Клиент использует только XFI token. Реальные ключи AI-провайдеров остаются на сервере.

## Telegram Code Agent

Code Agent предназначен для управляемой разработки XFI CONNECT без прямой записи в `main`.

### Цикл изменения

```text
Пользователь
    │
    ▼
/code
    │
    ▼
Текстовая задача
    │
    ▼
Анализ репозитория
    │
    ▼
Уточняющие вопросы
    │
    ▼
План + список файлов + проверки
    │
    ▼
ПОДТВЕРЖДАЮ
    │
    ▼
Ветка xfi-ai/*
    │
    ▼
Изменения
    │
    ▼
Pull Request
    │
    ▼
GitHub Actions
```

Code Agent ограничивает размер запроса и файлов, блокирует чувствительные пути (`.env`, credentials, private keys), работает только с безопасными существующими файлами и не должен выполнять произвольные shell-команды.

Основные команды Telegram-бота:

```text
/start
/help
/token
/code
/cancel
```

`/token` выдаёт новый XFI API key. Токен показывается один раз.

## XFI_CONNECT integration

XFI CONNECT подключается к Gateway одним токеном. Администратор получает его в XFI AI через `/token`, а затем задаёт в XFI CONNECT через:

```text
/ai_token xfi_...
```

После проверки токен сохраняется на стороне XFI CONNECT. Пользовательские запросы выполняются командой `/ai`.

## Web Admin

Web Admin предоставляет:

- выпуск, активацию и деактивацию XFI client keys;
- определение AI provider по API key;
- метрики provider'ов;
- добавление и диагностику VPS;
- безопасный restart разрешённых сервисов;
- просмотр Docker containers;
- audit log.

Административный доступ защищён `XFI_AI_ADMIN_KEY`.

## VPS Control Center

SSH-подключение допускается через существующий ключ или SSH agent. Пароли не принимаются и не сохраняются.

Безопасный restart ограничен allowlist:

```text
x-ui
3x-ui
xray
nginx
docker
```

Произвольные shell-команды, shell injection и destructive-операции через Control Center запрещены.

## OpenClaw + Telegram

OpenClaw используется как отдельный control-plane для диагностики VPS, heartbeat и консервативного auto-heal.

Telegram использует pairing, поэтому неизвестные пользователи не получают доступ автоматически.

Auto-heal допускает только проверку состояния и не более одного безопасного restart с повторной проверкой. Изменение VPN-конфигурации, firewall, DNS, TLS/Reality, пользователей 3X-UI и удаление инфраструктуры автоматически не выполняются.

## Установка

```bash
git clone https://github.com/deilja/XFI_AI.git
cd XFI_AI
bash deploy/preflight.sh
chmod +x deploy/install.sh
sudo ./deploy/install.sh
```

Установщик настраивает Python venv, systemd, nginx reverse proxy, HTTPS, переменные окружения и локальный `/health` smoke test.

Основные пути:

```text
/opt/xfi-ai/
/etc/xfi-ai/xfi-ai.env
/var/lib/xfi-ai/keys.db
/etc/systemd/system/xfi-ai.service
/etc/nginx/sites-available/xfi-ai
```

## Конфигурация

Минимальный набор переменных:

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

XFI_AI_PROVIDERS=groq,gemini,cloudflare,openrouter,mistral,sambanova,cerebras,huggingface,cohere
XFI_AI_ADMIN_KEY=
XFI_AI_DB=/var/lib/xfi-ai/keys.db
XFI_AI_KEY_PEPPER=
```

Модели можно переопределять через соответствующие `*_MODEL`.

Для OpenClaw дополнительно используются RouterAI/Groq и Telegram credentials.

## Systemd и безопасность

Production service запускается не от root. Используются ограничения systemd:

- `NoNewPrivileges=true`;
- `PrivateTmp=true`;
- `ProtectSystem=strict`;
- `ProtectHome=true`;
- запись только в каталог данных приложения.

Uvicorn слушает localhost, внешний HTTPS отдаёт nginx.

Секреты не должны попадать в Git. Admin key сравнивается constant-time, административные действия пишутся в audit log.

## Тестирование

```bash
python3 -m pytest -q tests
python3 -m compileall -q app
python3 -m ruff check .
bash deploy/preflight.sh
```

GitHub Actions выполняет тесты, lint, security checks, dependency audit и shell validation.

## Связанные проекты

- **XFI_CONNECT** — Telegram VPN-бот и сервис управления подписками, использующий XFI AI Gateway.
- **XFI Guard** — мониторинг и защита VPS-инфраструктуры XFI.

## Лицензия

Лицензионные условия определяются текущими файлами репозитория.
