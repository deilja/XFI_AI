# XFI AI

Мульти-AI Gateway для экосистемы XFI. Клиент подключается к вашему HTTPS-домену, а XFI AI выбирает AI-провайдера и автоматически переключается на следующий при временной ошибке.

## OpenClaw + RouterAI + Groq + Telegram

XFI AI включает отдельный control-plane на базе OpenClaw:

```text
Telegram
   │
   ▼
OpenClaw Gateway
   │
   ├── RouterAI → Claude Sonnet / DeepSeek
   └── Groq → GPT-OSS
   │
   ▼
XFI AI / VPS
   ├── 3X-UI / X-UI
   ├── Xray
   ├── nginx
   ├── Docker
   └── YadrenoVPN
```

RouterAI используется как основной AI для сложной диагностики и исправлений. Groq используется как быстрый provider и fallback. Telegram работает через pairing.

### Установка OpenClaw-контура

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
- создаёт безопасный `HEARTBEAT.md`.

Полный набор cron-команд, диагностика, pairing, модели и troubleshooting: `openclaw/CRON.md`.

### Telegram pairing

```bash
openclaw pairing list telegram
openclaw pairing approve telegram <КОД>
```

После pairing доступны `/status`, `/model list` и переключение модели. Подробности находятся в `openclaw/CRON.md`.

## VPS Control Center

XFI AI содержит безопасный менеджер VPS для диагностики удалённых узлов. Для SSH разрешены только два режима:

- `key` — путь к существующему приватному ключу на сервере;
- `agent` — системный SSH agent.

Хранение SSH-паролей отключено. Самодельное шифрование паролей не используется.

Удалённые действия ограничены allowlist: `x-ui`, `3x-ui`, `xray`, `nginx`, `docker`. Произвольные команды и изменение VPN-конфигурации через этот контур не разрешаются. Диагностика и restart записываются в audit log.

## Авто-проверка и auto-heal

`openclaw/HEARTBEAT.md` ограничивает автоматические действия. Разрешён диагностический доступ и однократный restart существующего сервиса после проверки.

Запрещены без явного указания администратора:

- удаление пользователей, inbound и ключей;
- изменение портов, TLS, Reality и firewall;
- изменение базы 3X-UI/X-UI;
- удаление Docker volumes/containers;
- обновление Xray/3X-UI;
- отключение UFW/Fail2Ban;
- массовые destructive-команды.

Для независимой host-проверки:

```bash
sudo bash /opt/XFI_AI/openclaw/xfi-vpn-heal.sh
```

## Комбо AI-провайдеров

XFI AI Gateway поддерживает Groq, Google Gemini, Cloudflare, OpenRouter Free, Mistral, SambaNova, Cerebras, Hugging Face и Cohere. Их порядок задаётся `XFI_AI_PROVIDERS`.

OpenClaw добавляет RouterAI отдельно и не удаляет существующие XFI AI providers.

## API XFI AI

```text
POST https://<your-domain>/v1/chat/completions
GET  https://<your-domain>/v1/models
GET  https://<your-domain>/health
```

Клиент использует один `xfi_...` ключ и не получает реальные ключи AI-провайдеров.

## Установка XFI AI

```bash
git clone https://github.com/deilja/XFI_AI.git
cd XFI_AI
chmod +x deploy/install.sh
sudo ./deploy/install.sh
```

Установщик спрашивает домен, предлагает свободный локальный порт, принимает ключи провайдеров скрытым вводом, создаёт пользователя `xfi-ai`, systemd service, nginx reverse proxy и HTTPS.

## Безопасность

Реальные AI keys находятся только на VPS. Не добавляйте `.env`, Telegram token или RouterAI/Groq keys в Git. OpenClaw Telegram-доступ должен использовать pairing. Для автоматического ремонта применяются консервативные правила из `openclaw/HEARTBEAT.md`.

## Быстрая схема

```text
                ┌──────────────┐
                │   Telegram   │
                └──────┬───────┘
                       │ pairing
                       ▼
                ┌──────────────┐
                │   OpenClaw   │
                └──────┬───────┘
                 ┌─────┴─────┐
                 ▼           ▼
            ┌────────┐   ┌────────┐
            │RouterAI│   │  Groq  │
            └────┬───┘   └───┬────┘
                 └─────┬─────┘
                       ▼
                ┌──────────────┐
                │    XFI AI    │
                └──────┬───────┘
                       ▼
          ┌────────────────────────┐
          │ 3X-UI / Xray / nginx   │
          │ Docker / YadrenoVPN    │
          └────────────────────────┘
```
