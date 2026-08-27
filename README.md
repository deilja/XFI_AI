# XFI AI

Мульти-AI Gateway для экосистемы XFI. Клиент подключается к вашему HTTPS-домену, а XFI AI сам выбирает AI-провайдера и автоматически переключается на следующий при временной ошибке.

## Комбо провайдеров

Поддерживается до 7 провайдеров:

1. Groq
2. Google Gemini
3. OpenRouter Free
4. Mistral
5. SambaNova
6. Cerebras
7. Hugging Face Inference Providers

Порядок задаётся `XFI_AI_PROVIDERS`. В установщике можно оставить ненужные ключи пустыми и изменить порядок failover.

Mistral Studio имеет бесплатный режим с ограничениями и rate limits. citeturn2search1 Hugging Face Inference Providers дают единый доступ к сотням моделей, но бесплатные кредиты зависят от типа аккаунта и могут изменяться. citeturn0search0turn0search4 Cerebras сейчас предоставляет бесплатный trial credit, а не гарантированный бессрочный бесплатный тариф. citeturn0search1 Поэтому XFI AI считает их опциональными провайдерами, а не обещает безлимитный бесплатный доступ.

## Архитектура

```text
Client / XFI Support / XFI Guard
          |
          | HTTPS + xfi_ API key
          v
   https://<your-domain>
          |
       Nginx
          |
     XFI AI Gateway
          |
    provider failover
    /  /  |  |  |  |  \
 Groq Gemini OR Mistral SambaNova Cerebras HF
          |
       AI response
```

## API

```text
POST https://<your-domain>/v1/chat/completions
GET  https://<your-domain>/v1/models
GET  https://<your-domain>/health
```

Клиент использует один `xfi_...` ключ и не знает настоящих ключей провайдеров.

## Установка

```bash
git clone https://github.com/deilja/XFI_AI.git
cd XFI_AI
chmod +x deploy/install.sh
sudo ./deploy/install.sh
```

Установщик автоматически:

- спрашивает домен;
- находит свободный локальный порт;
- принимает ключи провайдеров скрытым вводом;
- формирует порядок failover;
- создаёт отдельного пользователя `xfi-ai`;
- устанавливает Python/Nginx/Certbot;
- создаёт systemd service;
- создаёт HTTPS reverse proxy;
- проверяет DNS и health endpoint;
- хранит секреты в `/etc/xfi-ai/xfi-ai.env` с правами `600`.

## Безопасность

Реальные AI keys никогда не выдаются клиенту. Они находятся только на VPS. Публичным является только XFI API endpoint. В Git не должны попадать реальные ключи.
