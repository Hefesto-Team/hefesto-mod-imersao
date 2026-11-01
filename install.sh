#!/usr/bin/env bash
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI="${HEFESTO_CLI:-hefesto-dualsense4unix}"

if [ "$(id -u)" -eq 0 ] || [ -n "${SUDO_USER:-}" ]; then
  echo "install.sh: rode sem sudo; a extensão mora na casa de quem joga." >&2
  exit 1
fi

SIM=()
for arg in "$@"; do
  case "$arg" in
    --yes | --sim) SIM=(--sim) ;;
    *) echo "install.sh: opção desconhecida: $arg (use --yes)" >&2; exit 2 ;;
  esac
done

if ! command -v "$CLI" >/dev/null 2>&1; then
  echo "install.sh: o Hefesto não está instalado ($CLI fora do PATH)." >&2
  exit 1
fi

exec "$CLI" mod instalar "$RAIZ" "${SIM[@]}"
