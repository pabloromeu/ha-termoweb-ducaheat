#!/usr/bin/env bash
set -euo pipefail

# install_termoweb_card.sh
# Copy the TermoWeb schedule card into the public www path.
# Usage: run from an HA shell (SSH add-on), no args needed.
# Optionally pass a custom config dir as the first argument.

CONFIG_DIR="${1:-/config}"
CARD_NAME="termoweb_schedule_card.js"
DEST_DIR="${CONFIG_DIR}/www/termoweb"
DEST="${DEST_DIR}/${CARD_NAME}"

SRC="${CONFIG_DIR}/custom_components/termoweb/www/${CARD_NAME}"

echo "[*] Using config dir: ${CONFIG_DIR}"
mkdir -p "${DEST_DIR}"

if [ -f "${SRC}" ]; then
  cp -f "${SRC}" "${DEST}"
  echo "[+] Copied ${SRC} -> ${DEST}"
  echo "[i] Now add a Lovelace resource in the UI:"
  echo "    URL: /local/termoweb/${CARD_NAME}"
  echo "    Type: JavaScript Module"
else
  echo "[!] Could not find ${CARD_NAME} in ${SRC}"
fi
