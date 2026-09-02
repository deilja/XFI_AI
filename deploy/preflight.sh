#!/usr/bin/env bash
set -Eeuo pipefail

# XFI_AI production preflight. Read-only: no package/service/config changes.
PASS=0
WARN=0
FAIL=0

ok() { PASS=$((PASS + 1)); printf '[READY] %s\n' "$*"; }
warn() { WARN=$((WARN + 1)); printf '[WARN ] %s\n' "$*"; }
bad() { FAIL=$((FAIL + 1)); printf '[FAIL ] %s\n' "$*" >&2; }

if [[ ${EUID:-$(id -u)} -eq 0 ]]; then ok 'Running as root'; else bad 'Run preflight as root'; fi

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  if [[ ${ID:-} == ubuntu && ${VERSION_ID:-} == 24.04* ]]; then
    ok "OS: Ubuntu ${VERSION_ID}"
  elif [[ ${ID:-} == ubuntu ]]; then
    warn "OS: Ubuntu ${VERSION_ID:-unknown}; Ubuntu 24.04 is recommended"
  else
    warn "OS: ${PRETTY_NAME:-unknown}; Ubuntu 24.04 is recommended"
  fi
else
  bad 'Cannot read /etc/os-release'
fi

for cmd in python3 curl openssl ss systemctl; do
  if command -v "$cmd" >/dev/null 2>&1; then ok "$cmd available"; else bad "$cmd is missing"; fi
done

if command -v python3 >/dev/null 2>&1; then
  if python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
    ok "Python $(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  else
    bad 'Python 3.11+ required'
  fi
fi

if command -v nginx >/dev/null 2>&1; then
  if nginx -t >/dev/null 2>&1; then ok 'Nginx installed and configuration is valid'; else warn 'Nginx is installed but nginx -t fails'; fi
else
  warn 'Nginx is not installed yet; installer can install it'
fi

if command -v certbot >/dev/null 2>&1; then ok 'Certbot available'; else warn 'Certbot is not installed yet; installer can install it'; fi

if command -v free >/dev/null 2>&1; then
  mem_mb="$(free -m | awk '/^Mem:/ {print $2}')"
  if [[ ${mem_mb:-0} -ge 512 ]]; then ok "RAM: ${mem_mb} MiB"; else warn "RAM: ${mem_mb:-unknown} MiB; 512 MiB+ recommended"; fi
fi

if command -v df >/dev/null 2>&1; then
  disk_kb="$(df -Pk / | awk 'NR==2 {print $4}')"
  if [[ ${disk_kb:-0} -ge 1048576 ]]; then ok "Root filesystem free: $((disk_kb / 1024)) MiB"; else warn 'Less than 1 GiB free on root filesystem'; fi
fi

if command -v ss >/dev/null 2>&1; then
  free_port=''
  busy=0
  for port in $(seq 8091 8199); do
    if ss -H -ltn "sport = :$port" 2>/dev/null | grep -q .; then busy=$((busy + 1)); elif [[ -z "$free_port" ]]; then free_port="$port"; fi
  done
  if [[ -n "$free_port" ]]; then ok "Port range 8091-8199 has a free port (first: $free_port)"; else bad 'All ports 8091-8199 are busy'; fi
fi

if [[ -d /opt/xfi-ai ]]; then warn '/opt/xfi-ai already exists; review before installation'; else ok '/opt/xfi-ai is free'; fi
if [[ -d /etc/xfi-ai ]]; then warn '/etc/xfi-ai already exists; review before installation'; else ok '/etc/xfi-ai is free'; fi
if systemctl list-unit-files 'xfi-ai.service' --no-legend 2>/dev/null | grep -q '^xfi-ai\.service'; then
  warn 'xfi-ai.service already exists'
else
  ok 'xfi-ai.service does not exist'
fi

if [[ -e /etc/nginx/sites-enabled/xfi-ai.conf || -e /etc/nginx/sites-available/xfi-ai.conf ]]; then
  warn 'Existing XFI_AI Nginx configuration detected'
else
  ok 'No existing XFI_AI Nginx configuration'
fi

if command -v curl >/dev/null 2>&1; then
  public_ip="$(curl -4fsS --max-time 5 https://api.ipify.org 2>/dev/null || true)"
  if [[ -n "$public_ip" ]]; then ok "Public IPv4 detected: $public_ip"; else warn 'Could not determine public IPv4 automatically'; fi
  if curl -4fsS --max-time 5 https://www.google.com/generate_204 >/dev/null 2>&1; then
    ok 'Outbound IPv4 HTTPS connectivity works'
  else
    warn 'Outbound IPv4 HTTPS connectivity test failed'
  fi
fi

if [[ -r /proc/mounts ]] && grep -Eq ' / .*\b(ro|nosuid|nodev)' /proc/mounts; then
  warn 'Some root mount flags may restrict installer writes; verify before installation'
fi

printf '%s\n' '--------------------------------------'
printf 'RESULT: READY=%d WARN=%d FAIL=%d\n' "$PASS" "$WARN" "$FAIL"
if ((FAIL > 0)); then
  echo 'PREFLIGHT: FAIL'
  exit 2
elif ((WARN > 0)); then
  echo 'PREFLIGHT: READY WITH WARNINGS'
  exit 0
else
  echo 'PREFLIGHT: READY'
  exit 0
fi
