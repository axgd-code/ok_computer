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
KDBX_PASSWORD=""  # Will be prompted once and reused
KEYCHAIN_MODE="auto"  # auto|login|system
LOGIN_KEYCHAIN_PASS=""  # Optional: prompted once when using login keychain
USE_CHAINBREAKER=false

# Load .env.local (one level up) if present to get defaults like WIFI_KDBX_DB / WIFI_KDBX_KEY_FILE
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/../.env.local" ]; then
    # shellcheck disable=SC1091
    source "${SCRIPT_DIR}/../.env.local"
fi

usage() {
    cat <<EOF
${BLUE}Usage:${NC} bash wifi_from_keychain.sh --db <file.kdbx> [--group "Wi-Fi"] [--key-file path] [--keychain auto|login|system] [--dry-run]

This script reads Wi‑Fi SSIDs stored in the macOS Keychain and adds entries to a KeePassXC
database using 'keepassxc-cli'.

${YELLOW}IMPORTANT - macOS Security:${NC}
On many Macs, Wi-Fi passwords live in the System keychain. Accessing decrypted secrets from
System.keychain can trigger a macOS authorization prompt per item.

This script defaults to using your login keychain first (no admin password), then falls back
to System.keychain if needed.

Options:
    --keychain auto   Try login keychain first, fallback to system (default)
    --keychain login  Only use login keychain (avoids admin prompts)
    --keychain system Only use system keychain (may prompt per Wi-Fi)
    --use-chainbreaker Use 'chainbreaker' tool to decrypt System keychain (Zero prompt solution but requires tool installation)

Notes:
    - When using the login keychain, the script will unlock it once using your session password
        (entered in the terminal). This typically avoids repeated GUI prompts.
    - 'chainbreaker' is a third-party tool that can decrypt the System keychain directly using the
      master key (/var/db/SystemKey). This bypasses all GUI access prompts but requires sudo.
      Install via: git clone https://github.com/n0fate/chainbreaker && pip install .

Prerequisites:
  - macOS 'security' tool (built-in)
  - 'keepassxc-cli' installed and available in PATH
  - Target KeePassXC DB already exists and is writable

The KeePassXC entry created will use:
  - Title = SSID
  - Password = Wi‑Fi key
  - Username = SSID

If '--db' is not provided, the script will use 'WIFI_KDBX_DB' from '.env.local' if present.
If '--key-file' is not provided, the script will use 'WIFI_KDBX_KEY_FILE' from '.env.local' if present.

EOF
}

log() { echo -e "${BLUE}$*${NC}" >&2; }
log_ok() { echo -e "${GREEN}$*${NC}" >&2; }
log_warn() { echo -e "${YELLOW}$*${NC}" >&2; }
log_err() { echo -e "${RED}$*${NC}" >&2; }

require_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        log_err "Required command missing: $1"
        exit 1
    fi
}

unlock_login_keychain_once() {
    local keychain_path="$1"
    if $DRY_RUN; then
        return 0
    fi

    log "Unlocking login keychain for this session (one-time)..."
    log_warn "Enter your macOS session password (not shown)."
    read -s -r LOGIN_KEYCHAIN_PASS </dev/tty
    echo

    if ! security unlock-keychain -p "$LOGIN_KEYCHAIN_PASS" "$keychain_path" >/dev/null 2>&1; then
        log_err "Failed to unlock login keychain. Wrong password or keychain locked by policy."
        exit 1
    fi
}

get_wifi_passwords_via_chainbreaker() {
    log "Attempting to use chainbreaker to decrypt System Keychain..."
    
    local cb_cmd=""
    if command -v chainbreaker >/dev/null 2>&1; then
        cb_cmd="chainbreaker"
    elif python3 -m chainbreaker --help >/dev/null 2>&1; then
        cb_cmd="python3 -m chainbreaker"
    else
        log_err "chainbreaker not found. Please install it:"
        log_err "  git clone https://github.com/n0fate/chainbreaker"
        log_err "  cd chainbreaker && pip install ."
        return 1
    fi

    log_warn "Sudo is required to read /var/db/SystemKey"
    local raw_output
    # -a / --dump-all might include genetic passwords? 
    # Use generic passwords explicitly if possible, or just dump all and filter.
    # Based on docs: --unlock-file KEY KEYCHAIN
    # We expect standard output to contain the records.
    
    if ! raw_output=$(sudo $cb_cmd --unlock-file /var/db/SystemKey /Library/Keychains/System.keychain 2>/dev/null); then
        log_err "chainbreaker failed to run."
        return 1
    fi

    echo "$raw_output" | perl -0777 -ne '
        while (/\[\+\] Generic Password Record(.*?)(?=\[\+\] Generic Password Record|$)/gs) {
            $block = $1;
            my $service = "";
            my $account = "";
            my $password = "";
            
            if ($block =~ /\[-\] Service:\s*(.+)/) { $service = $1; $service =~ s/^\s+|\s+$//g; }
            if ($block =~ /\[-\] Account:\s*(.+)/) { $account = $1; $account =~ s/^\s+|\s+$//g; }
            if ($block =~ /\[-\] Password:\s*(.+)/) { $password = $1; $password =~ s/^\s+|\s+$//g; }
            
            # Check if this looks like a Wi-Fi password. 
            # Usually Service is "AirPort" or "AirPort network password" ?
            # In chainbreaker output, it might vary. We accept "AirPort"
            
            if ($service =~ /AirPort/i && $account ne "" && $password ne "") {
                print "$account|$password\n";
            }
        }
    ' | sort -u
}

list_ssids_from_keychain_path() {
    local keychain_path="$1"
    local use_sudo="$2" # true|false

    # Use perl to robustly parse the keychain dump structure
    # This avoids false positives from grep context matching across blocks
    local perl_parser='
        while (/keychain:.*?(?=(?:keychain:|$))/gs) {
            $block = $&;
            my $acct = "";
            my $desc = "";
            
            if ($block =~ /"acct"<blob>="((?:[^"\\\\]|\\\\.)*)"/) {
                $acct = $1; $acct =~ s/\\\\(.)/$1/g;
            } elsif ($block =~ /"acct"<blob>=0x([0-9A-Fa-f]+)/) {
                $acct = pack("H*", $1);
            }
            
            if ($block =~ /"desc"<blob>="((?:[^"\\\\]|\\\\.)*)"/) {
                $desc = $1; $desc =~ s/\\\\(.)/$1/g;
            } elsif ($block =~ /"desc"<blob>=0x([0-9A-Fa-f]+)/) {
                $desc = pack("H*", $1);
            }
            
            if ($desc eq "AirPort network password" && $acct ne "") {
                print "$acct\n";
            }
        }
    '

    if [ "$use_sudo" = "true" ]; then
        sudo security dump-keychain "$keychain_path" 2>/dev/null | perl -0777 -ne "$perl_parser" | sort -u
    else
        security dump-keychain "$keychain_path" 2>/dev/null | perl -0777 -ne "$perl_parser" | sort -u
    fi
}


get_all_wifi_passwords() {
    local keychain_path="$1"
    local use_sudo="$2" # true|false

    # 1. Fetch Existing Entries from KeePassXC to avoid duplication/prompts
    log "Checking for existing entries in KeePassXC..."
    local existing_entries=""
    if [ -n "$KDBX_PASSWORD" ] && [ -n "$DB_FILE" ]; then
        # Fetch list of titles from the group (silence errors if group missing)
        existing_entries=$(printf "%s\n" "$KDBX_PASSWORD" | keepassxc-cli ls ${KEY_FILE:+--key-file "$KEY_FILE"} "$DB_FILE" "$GROUP" 2>/dev/null || true)
    fi

    # 2. Strategy: Chainbreaker (if requested)
    if [ "$USE_CHAINBREAKER" = "true" ]; then
        local cb_list
        cb_list=$(get_wifi_passwords_via_chainbreaker) # Returns SSID|PW
        
        # Filter chainbreaker results
        local final_list=""
        while IFS= read -r line; do
             [ -z "$line" ] && continue
             local ssid="${line%%|*}"
             if ! echo "$existing_entries" | grep -Fxq "$ssid"; then
                 final_list+="${line}"$'\n'
             fi
        done <<< "$cb_list"
        
        local count
        count=$(echo "$final_list" | grep -cve '^\s*$' || echo 0)
        log "Chainbreaker found $count new network(s)."
        
        echo "$final_list"
        return
    fi

    # 3. Strategy: Security (Standard)
    # Extract all WiFi passwords using a single batch 'security -i' session.
    log "Fetching Wi-Fi passwords from keychain: ${keychain_path}"
    if [ "$use_sudo" = "true" ]; then
        log_warn "Accessing System keychain. You may receive multiple authorization prompts from macOS."
        log_warn "This is standard macOS security behavior for the System Keychain."
    fi

    local ssids_list
    ssids_list=$(list_ssids_from_keychain_path "$keychain_path" "$use_sudo")
    
    # Filter SSIDs before fetching passwords to minimize prompts
    local ssids_to_process=""
    local skipped_count=0
    
    while IFS= read -r ssid; do
        [ -z "$ssid" ] && continue
        if echo "$existing_entries" | grep -Fxq "$ssid"; then
            skipped_count=$((skipped_count + 1))
        else
            ssids_to_process+="${ssid}"$'\n'
        fi
    done <<< "$ssids_list"
    
    local to_process_count
    to_process_count=$(echo "$ssids_to_process" | grep -cve '^\s*$' || echo 0)
    
    log "Skipped $skipped_count existing networks."
    log "Processing $to_process_count new network(s)."
    
    if [ -z "$ssids_to_process" ] || [ "$to_process_count" -eq 0 ]; then
        return
    fi
    
    # Display the list to user
    log_warn "The following networks will be added:"
    echo "$ssids_to_process" >&2

    # Create batch script for password retrieval
    local batch_file
    batch_file=$(mktemp)
    
    while IFS= read -r ssid; do
        [ -z "$ssid" ] && continue
        # Escape quotes/backslashes for the command string
        local safe_ssid="${ssid//\\/\\\\}"
        safe_ssid="${safe_ssid//\"/\\\"}"
        # We use -g to get attributes (including account/SSID) AND password in one block
        echo "find-generic-password -D \"AirPort network password\" -a \"$safe_ssid\" -g \"$keychain_path\"" >> "$batch_file"
    done <<< "$ssids_to_process"

    local raw_output
    # Run security in interactive mode
    if [ "$use_sudo" = "true" ]; then
        # Capture stdout and stderr (security prints errors to stderr, output to stdout? or mixed?)
        # Testing showed mixed. We capture both to be safe.
        raw_output=$(sudo security -i < "$batch_file" 2>&1)
    else
        raw_output=$(security -i < "$batch_file" 2>&1)
    fi
    rm -f "$batch_file"

    # Parse the output using Perl
    # Blocks start with 'keychain: ...'
    # We look for "acct"<blob> and password: fields
    echo "$raw_output" | perl -0777 -ne '
        while (/keychain:.*?(?=(?:keychain:|$))/gs) {
            $block = $&;
            
            # Extract account (SSID)
            # Format: "acct"<blob>="String"  OR  "acct"<blob>=0xHex
            my $ssid = "";
            if ($block =~ /"acct"<blob>="((?:[^"\\\\]|\\\\.)*)"/) {
                $ssid = $1;
                $ssid =~ s/\\\\(.)/$1/g; # Unescape
            } elsif ($block =~ /"acct"<blob>=0x([0-9A-Fa-f]+)/) {
                # Hex string
                $hex = $1;
                $ssid = pack("H*", $hex);
            }

            # Extract password
            # Format: password: "String"  OR  password: 0xHex
            # Located at the end of the block typically
            my $pass = "";
            if ($block =~ /password: "((?:[^"\\\\]|\\\\.)*)"/) {
                $pass = $1;
                $pass =~ s/\\\\(.)/$1/g; # Unescape
            } elsif ($block =~ /password: 0x([0-9A-Fa-f]+)/) {
                 $hex = $1;
                 $pass = pack("H*", $hex);
            }

            if ($ssid ne "" && $pass ne "") {
                # Output using pipe delimiter
                print "$ssid|$pass\n";
            }
        }
    '
}


add_entry_to_kp() {
    local ssid="$1" pw="$2"
    require_cmd keepassxc-cli
    if $DRY_RUN; then
        log "[dry-run] would add entry: ${ssid}"
        return 0
    fi
    
    local entry_path="${GROUP}/${ssid}"
    local output
    
    # Check if entry already exists (DB password via stdin)
    if printf "%s\n" "$KDBX_PASSWORD" | keepassxc-cli show ${KEY_FILE:+--key-file "$KEY_FILE"} \
        "$DB_FILE" "$entry_path" >/dev/null 2>&1; then
        # Entry exists - update password
        if output=$(printf "%s\n%s\n" "$KDBX_PASSWORD" "$pw" | keepassxc-cli edit \
            ${KEY_FILE:+--key-file "$KEY_FILE"} \
            --password-prompt \
            "$DB_FILE" \
            "$entry_path" 2>&1); then
            log_ok "Updated existing entry: ${ssid}"
            return 0
        else
            log_err "keepassxc-cli error: ${output}"
            return 1
        fi
    else
        # Entry doesn't exist - create new one
        if output=$(printf "%s\n%s\n" "$KDBX_PASSWORD" "$pw" | keepassxc-cli add \
            ${KEY_FILE:+--key-file "$KEY_FILE"} \
            --username "$ssid" \
            --password-prompt \
            "$DB_FILE" \
            "$entry_path" 2>&1); then
            log_ok "Created new entry: ${ssid}"
            return 0
        else
            log_err "keepassxc-cli error: ${output}"
            return 1
        fi
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
            --keychain)
                KEYCHAIN_MODE="$2"; shift 2;;
            --use-chainbreaker)
                USE_CHAINBREAKER=true; shift;;
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

    local login_keychain system_keychain keychain_path use_sudo
    login_keychain="${HOME}/Library/Keychains/login.keychain-db"
    system_keychain="/Library/Keychains/System.keychain"
    keychain_path=""
    use_sudo="false"

    case "$KEYCHAIN_MODE" in
        auto)
            if [ -f "$login_keychain" ]; then
                keychain_path="$login_keychain"
                use_sudo="false"
            else
                keychain_path="$system_keychain"
                use_sudo="true"
            fi
            ;;
        login)
            if [ ! -f "$login_keychain" ]; then
                log_err "login keychain not found: ${login_keychain}"
                exit 1
            fi
            keychain_path="$login_keychain"
            use_sudo="false"
            ;;
        system)
            keychain_path="$system_keychain"
            use_sudo="true"
            ;;
        *)
            log_err "Invalid --keychain value: ${KEYCHAIN_MODE} (expected auto|login|system)"
            exit 1
            ;;
    esac

    if [ "$use_sudo" = "true" ]; then
        log "Requesting sudo access to read System.keychain..."
        sudo -v || { log_err "Sudo access required to read System.keychain"; exit 1; }
        log "Attempting to unlock System.keychain..."
        sudo security unlock-keychain "$keychain_path" 2>/dev/null || true
    else
        # Avoid admin prompts by using login keychain and unlocking it once.
        unlock_login_keychain_once "$keychain_path"
    fi

    # Prompt for KeePassXC database password once (unless dry-run)
    if ! $DRY_RUN; then
        log "Enter password for KeePassXC database: ${DB_FILE}"
        read -s -r KDBX_PASSWORD </dev/tty
        echo  # newline after password input
        
        # Validate password by testing database access (do NOT depend on the group existing)
        local kp_check
        kp_check=$(printf "%s\n" "$KDBX_PASSWORD" | keepassxc-cli db-info ${KEY_FILE:+--key-file "$KEY_FILE"} "$DB_FILE" 2>&1) || {
            log_err "Failed to unlock KeePassXC database. Check your password and try again."
            log_err "keepassxc-cli: ${kp_check}"
            exit 1
        }
        log_ok "Database unlocked successfully."
    fi

    log "Detecting SSIDs stored in macOS Keychain..."
    mapfile -t wifi_entries < <(get_all_wifi_passwords "$keychain_path" "$use_sudo")

    # In auto mode, fall back to System.keychain if login keychain has no Wi‑Fi items.
    if [ ${#wifi_entries[@]} -eq 0 ] && [ "$KEYCHAIN_MODE" = "auto" ] && [ "$use_sudo" = "false" ]; then
        log_warn "No Wi‑Fi items found in login keychain; falling back to System.keychain."
        keychain_path="$system_keychain"
        use_sudo="true"

        log "Requesting sudo access to read System.keychain..."
        sudo -v || { log_err "Sudo access required to read System.keychain"; exit 1; }
        log "Attempting to unlock System.keychain..."
        sudo security unlock-keychain "$keychain_path" 2>/dev/null || true

        mapfile -t wifi_entries < <(get_all_wifi_passwords "$keychain_path" "$use_sudo")
    fi

    if [ ${#wifi_entries[@]} -eq 0 ]; then
        log_warn "No Wi‑Fi SSIDs found in Keychain."
        exit 0
    fi

    log "Found ${#wifi_entries[@]} Wi-Fi network(s). Importing to KeePassXC..."
    for entry in "${wifi_entries[@]}"; do
        # Parse SSID|password
        ssid="${entry%%|*}"
        pw="${entry#*|}"
        [ -z "$ssid" ] || [ -z "$pw" ] && continue
        
        log "Processing SSID: ${ssid}"
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
