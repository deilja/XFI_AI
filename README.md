# XFI AI

AI Gateway для экосистемы XFI: клиент обращается к вашему домену, VPS обращается к Groq, а секретный `GROQ_API_KEY` никогда не передается клиенту.

## Архитектура

```text
Client / XFI Support / XFI Guard
          |
          | HTTPS + XFI proxy key
          v
   https://<your-domain>
          |
       Nginx
          |
     127.0.0.1:8091
          |
       XFI AI
          |
          | GROQ_API_KEY
          v
https://api.groq.com/openai/v1/chat/completions
```

Groq официально поддерживает OpenAI-compatible API; базовый URL Groq — `https://api.groq.com/openai/v1`, а chat completions endpoint — `/chat/completions`. citeturn0search0turn0search1

## Возможности

- OpenAI-compatible `POST /v1/chat/completions`;
- поддержка streaming-ответов от Groq;
- секретный Groq key хранится только на VPS;
- отдельные XFI proxy API keys для клиентов;
- ключи хранятся только в виде SHA-256 хеша с optional pepper;
- админская выдача ключей через веб-сайт;
- health-check `/health`;
- Nginx reverse proxy + HTTPS;
- systemd service с базовым hardening;
- ограничение размера запроса 2 MiB;
- `.env` исключен из Git.

## API

Клиент использует:

```text
https://<your-domain>/v1
```

Например, OpenAI-compatible клиент должен использовать этот `base_url` и выданный `xfi_...` ключ вместо прямого Groq key.

## Выдача ключей

Веб-сайт находится на `/`. Для создания ключа используется административный заголовок `X-Admin-Key`. Сам Groq key через браузер не передается.

## Переменные окружения

- `GROQ_API_KEY` — настоящий секрет Groq;
- `XFI_AI_ADMIN_KEY` — секрет администратора портала;
- `XFI_AI_DB` — SQLite-файл ключей;
- `XFI_AI_KEY_PEPPER` — дополнительный секрет для хеширования ключей.

Никогда не помещайте реальные значения этих переменных в GitHub.

## Запуск на VPS

```bash
python3 -m venv /opt/xfi-ai/venv
/opt/xfi-ai/venv/bin/pip install -r requirements.txt
/opt/xfi-ai/venv/bin/uvicorn app.api:app --host 127.0.0.1 --port 8091
```

Для production используйте `deploy/xfi-ai.service` и `deploy/nginx.conf.example`.

## Безопасность

Публичным является только ваш HTTPS endpoint. Порт 8091 должен слушать только `127.0.0.1`. Реальный Groq key не должен попадать в frontend, GitHub, URL или клиентские конфигурации.
