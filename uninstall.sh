#!/usr/bin/env bash
set -euo pipefail

CLI="${HEFESTO_CLI:-hefesto-dualsense4unix}"
ID="imersao"

if [ "$(id -u)" -eq 0 ] || [ -n "${SUDO_USER:-}" ]; then
  echo "uninstall.sh: rode sem sudo; a extensão mora na casa de quem joga." >&2
  exit 1
fi

if ! command -v "$CLI" >/dev/null 2>&1; then
  echo "uninstall.sh: o Hefesto não está instalado; não há extensão a remover."
  exit 0
fi

set +e
SAIDA="$("$CLI" mod remover "$ID" 2>&1)"
RC=$?
set -e
printf '%s\n' "$SAIDA"
if [ "$RC" -ne 0 ] && printf '%s' "$SAIDA" | grep -q "não está instalada"; then
  exit 0
fi
exit "$RC"
