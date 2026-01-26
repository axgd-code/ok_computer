#!/bin/bash

# If the user runs this script with 'sh' (POSIX shell) it may fail due to Bash-only features
# like process-substitution and 'mapfile'. Detect that and print an actionable message.
if [ -z "${BASH_VERSION:-}" ]; then
    echo "This script requires Bash. Run with: bash $0 [--db path]" >&2
    exit 2
fi

set -euo pipefail

# Extract Wi‑Fi profiles from macOS Keychain and import them into a KeePassXC database
# Usage: bash wifi_from_keychain.sh --db /path/to/db.kdbx [--group "Wi-Fi"] [--key-file /path/to/keyfile] [--dry-run]

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

DB_FILE=""
GROUP="Wifi"
KEY_FILE=""
DRY_RUN=false

# Load .env.local (one level up) if present to get defaults like WIFI_KDBX_DB / WIFI_KDBX_KEY_FILE
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/../.env.local" ]; then
    # shellcheck disable=SC1091
    source "${SCRIPT_DIR}/../.env.local"
fi

usage() {
    cat <<EOF
${BLUE}Usage:${NC} bash wifi_from_keychain.sh --db <file.kdbx> [--group "Wi-Fi"] [--key-file path] [--dry-run]

This script reads Wi‑Fi SSIDs stored in the macOS Keychain and adds entries to a KeePassXC
database using 'keepassxc-cli'.

Prerequisites:
  - macOS 'security' tool (built-in)
  - 'keepassxc-cli' installed and available in PATH
  - Target KeePassXC DB already exists and is writable

The KeePassXC entry created will use:
  - Title = SSID
  - Password = Wi‑Fi key
  - Comment = "imported from macOS keychain"

If '--db' is not provided, the script will use 'WIFI_KDBX_DB' from '.env.local' if present.
If '--key-file' is not provided, the script will use 'WIFI_KDBX_KEY_FILE' from '.env.local' if present.

EOF
}

log() { echo -e "${BLUE}$*${NC}"; }
log_ok() { echo -e "${GREEN}$*${NC}"; }
log_warn() { echo -e "${YELLOW}$*${NC}"; }
log_err() { echo -e "${RED}$*${NC}"; }

require_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        log_err "Required command missing: $1"
        exit 1
    fi
}

list_ssids_from_keychain() {
    # Use `security` to list generic passwords of kind "AirPort network password" and extract acct (SSID)
    security find-generic-password -D "AirPort network password" 2>/dev/null \
        | awk -F'"' '/"acct"<blob>="/{print $4}' \
        | sort -u
}

get_password_for_ssid() {
    local ssid="$1"
    # Try -w (prints only password). If that fails, fall back to parsing -g output.
    if pw=$(security find-generic-password -D "AirPort network password" -a "$ssid" -w 2>/dev/null); then
        echo "$pw"
        return 0
    fi
    # fallback
    if out=$(security find-generic-password -D "AirPort network password" -a "$ssid" -g 2>&1); then
        # parse: password: "..."
        echo "$out" | sed -nE 's/^password: "(.*)"$/\1/p' | head -n1
        return 0
    fi
    return 1
}

add_entry_to_kp() {
    local ssid="$1" pw="$2"
    require_cmd keepassxc-cli
    if $DRY_RUN; then
        log "[dry-run] would add entry: ${ssid}"
        return 0
    fi
    
    # Construct the command array
    local cmd=(keepassxc-cli add "${DB_FILE}" "${GROUP}" "${ssid}" --username "" --password "${pw}" --comment "imported from macOS keychain")
    if [ -n "${KEY_FILE}" ]; then
        cmd=(keepassxc-cli add --key-file "${KEY_FILE}" "${DB_FILE}" "${GROUP}" "${ssid}" --username "" --password "${pw}" --comment "imported from macOS keychain")
    fi

    # Execute with password pipe if KEEPASS_DB_PASS is set, otherwise interactive
    if [ -n "${KEEPASS_DB_PASS:-}" ]; then
        echo "${KEEPASS_DB_PASS}" | "${cmd[@]}"
    else
        "${cmd[@]}"
    fi
}

main() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --db)
                DB_FILE="$2"; shift 2;;
            --group)
                GROUP="$2"; shift 2;;
            --key-file)
                KEY_FILE="$2"; shift 2;;
            --dry-run)
                DRY_RUN=true; shift;;
            -h|--help)
                usage; exit 0;;
            *)
                log_err "Unknown option: $1"; usage; exit 1;;
        esac
    done

    # If DB_FILE not provided as arg, try environment variable loaded from .env.local
    if [ -z "${DB_FILE}" ]; then
        DB_FILE="${WIFI_KDBX_DB:-}"
    fi
    if [ -z "${DB_FILE}" ]; then
        usage; exit 1
    fi
    if [ ! -f "${DB_FILE}" ]; then
        log_err "KeePassXC DB not found: ${DB_FILE}"; exit 1
    fi

    # If KEY_FILE not provided as arg, try environment variable
    if [ -z "${KEY_FILE}" ]; then
        KEY_FILE="${WIFI_KDBX_KEY_FILE:-}"
    fi

    require_cmd security

    log "Detecting SSIDs stored in macOS Keychain..."
    mapfile -t ssids < <(list_ssids_from_keychain)
    if [ ${#ssids[@]} -eq 0 ]; then
        log_warn "No Wi‑Fi SSIDs found in Keychain."
        exit 0
    fi

    for ssid in "${ssids[@]}"; do
        log "Processing SSID: ${ssid}"
        if ! pw=$(get_password_for_ssid "$ssid"); then
            log_warn "Password not found for ${ssid}, skipping"
            continue
        fi
        # Add to KeePassXC
        if add_entry_to_kp "$ssid" "$pw"; then
            log_ok "Imported ${ssid} into KeePassXC"
        else
            log_err "Failed to import ${ssid}"
        fi
    done

    log_ok "Done."
}

main "$@"
