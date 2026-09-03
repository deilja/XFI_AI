#!/usr/bin/env bash
set -Eeuo pipefail

BASE_URL="${XFI_AI_BASE_URL:-${1:-}}"
API_KEY="${XFI_AI_API_KEY:-}"
[[ -n "$BASE_URL" ]] || { echo "Usage: XFI_AI_BASE_URL=https://example.com XFI_AI_API_KEY=xfi_... bash deploy/smoke_test.sh" >&2; exit 2; }
[[ "$BASE_URL" =~ ^https?://[^/]+/?$ ]] || { echo "Invalid base URL" >&2; exit 2; }
[[ -n "$API_KEY" ]] || { echo "XFI_AI_API_KEY is required" >&2; exit 2; }

BASE_URL="${BASE_URL%/}"

headers="$(curl -fsSI --max-time 10 "$BASE_URL/health")"
grep -qi '^x-content-type-options: nosniff' <<<"$headers"
grep -qi '^x-frame-options: DENY' <<<"$headers"
curl -fsS --max-time 10 "$BASE_URL/health" | grep -q '"status":"ok"'
curl -fsS --max-time 10 -H "Authorization: Bearer $API_KEY" "$BASE_URL/v1/models" | grep -q '"object":"list"'

if curl -sS --max-time 10 -o /dev/null -w '%{http_code}' "$BASE_URL/v1/models" | grep -q '^401$'; then
  :
else
  echo "Expected 401 for missing API key" >&2
  exit 1
fi

if curl -sS --max-time 10 -o /dev/null -w '%{http_code}' -H 'Authorization: Bearer invalid-smoke-key' "$BASE_URL/v1/models" | grep -q '^401$'; then
  :
else
  echo "Expected 401 for invalid API key" >&2
  exit 1
fi

if curl -sS --max-time 10 -o /dev/null -w '%{http_code}' -H 'Content-Type: application/json' -H "Authorization: Bearer $API_KEY" --data-binary '{invalid-json' "$BASE_URL/v1/chat/completions" | grep -q '^400$'; then
  :
else
  echo "Expected 400 for malformed JSON" >&2
  exit 1
fi

echo "SMOKE TEST: PASS"
