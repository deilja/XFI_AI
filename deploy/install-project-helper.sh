#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR="/opt/xfi-ai"
HELPER="$APP_DIR/deploy/xfi_ai_project_helper.py"
TARGET="/usr/local/libexec/xfi-ai-project-helper"
SUDOERS="/etc/sudoers.d/xfi-ai-project-helper"
[[ $EUID -eq 0 ]] || { echo "Run as root" >&2; exit 1; }
[[ -f "$HELPER" ]] || { echo "Helper source not found: $HELPER" >&2; exit 1; }
install -d -m 0755 -o root -g root /usr/local/libexec
install -m 0755 -o root -g root "$HELPER" "$TARGET"
cat > "$SUDOERS" <<'EOF'
# XFI AI may invoke only the fixed root-owned project helper.
xfi-ai ALL=(root) NOPASSWD: /usr/local/libexec/xfi-ai-project-helper
EOF
chown root:root "$SUDOERS"
chmod 0440 "$SUDOERS"
visudo -cf "$SUDOERS"
install -d -m 0750 -o root -g xfi-ai /var/lib/xfi-ai/backups
systemctl daemon-reload
systemctl restart xfi-ai
systemctl is-active --quiet xfi-ai
printf '%s\n' "XFI AI project helper installed and enabled."
