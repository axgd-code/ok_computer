#!/bin/bash

# Browser Extensions Setup Script
# Configures Firefox, Chrome, and Arc with extensions defined in extensions.conf

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXT_CONF="${SCRIPT_DIR}/extensions.conf"

log() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_ok() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_err() { echo -e "${RED}[ERROR]${NC} $1"; }

SUDO_NONINTERACTIVE_AVAILABLE=0
if sudo -n true 2>/dev/null; then
    SUDO_NONINTERACTIVE_AVAILABLE=1
fi

run_sudo() {
    if [ "$SUDO_NONINTERACTIVE_AVAILABLE" -ne 1 ]; then
        log_warn "No non-interactive sudo session available; skipping privileged step: $*"
        return 0
    fi
    if ! sudo -n "$@"; then
        log_warn "Privileged step failed and was skipped: $*"
    fi
    return 0
}

if [ "$SUDO_NONINTERACTIVE_AVAILABLE" -ne 1 ]; then
    log_warn "Running extension setup in user mode (without sudo)."
    log_warn "Some system-wide policies may not be applied, but user-level setup will continue."
fi

if [ ! -f "$EXT_CONF" ]; then
    log_err "Configuration file not found: $EXT_CONF"
    exit 1
fi

setup_firefox() {
    local extensions=("$@")
    
    if [ ! -d "/Applications/Firefox.app" ]; then
        log_warn "Firefox not installed, skipping."
        return
    fi

    log "Setting up Firefox extensions via System Policy..."

    # Build the URLs for Firefox extensions
    local ext_urls=()   
    for ext in "${extensions[@]}"; do
        ext_urls+=("https://addons.mozilla.org/firefox/downloads/latest/${ext}/latest.xpi")
    done

    # Create a temporary plist for Firefox
    local tmp_plist
    tmp_plist=$(mktemp).plist
    
    # We create a structure for EnterprisePolicies
    # This matches the org.mozilla.firefox.plist format
    cat <<EOF > "$tmp_plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>EnterprisePolicies</key>
    <dict>
        <key>Extensions</key>
        <dict>
            <key>Install</key>
            <array>
$(for url in "${ext_urls[@]}"; do echo "                <string>$url</string>"; done)
            </array>
        </dict>
    </dict>
</dict>
</plist>
EOF

    # Import the policy into the system preferences
    run_sudo plutil -convert binary1 "$tmp_plist"
    run_sudo cp "$tmp_plist" "/Library/Preferences/org.mozilla.firefox.plist"
    rm -f "$tmp_plist"
    
    log_ok "Firefox system policy updated."
}

setup_chromium() {
    local browser_name="$1"
    local plist_id="$2"
    shift 2
    local extensions=("$@")

    log "Setting up ${browser_name} extensions..."
    
    local forcelist=()
    local settings_xml="<dict>"
    
    for ext_id in "${extensions[@]}"; do
        forcelist+=("${ext_id};https://clients2.google.com/service/update2/crx")
        
        # Add to ExtensionSettings dictionary
        settings_xml="${settings_xml}<key>${ext_id}</key><dict><key>installation_mode</key><string>force_installed</string><key>update_url</key><string>https://clients2.google.com/service/update2/crx</string></dict>"
    done
    settings_xml="${settings_xml}</dict>"

    if [ ${#forcelist[@]} -gt 0 ]; then
        # 1. Update User Preferences
        log "  → Updating user preferences (${plist_id})..."
        defaults write "$plist_id" ExtensionInstallForcelist -array "${forcelist[@]}"
        
        # Write ExtensionSettings to user domain too
        # We use plutil to ensure the dictionary is correctly formatted in user preferences
        local user_plist="~/Library/Preferences/${plist_id}.plist"
        # Expand tilde
        user_plist="${user_plist/#\~/$HOME}"
        
        # If the file doesn't exist, defaults write will create it, but we want to be sure
        if [ ! -f "$user_plist" ]; then
            defaults write "$plist_id" LastPolicyCheck -string "$(date)"
        fi
        
        sudo plutil -replace "ExtensionSettings" -xml "$(echo $settings_xml | sed 's/&/&amp;/g')" "$user_plist" 2>/dev/null || \
        plutil -replace "ExtensionSettings" -xml "$(echo $settings_xml | sed 's/&/&amp;/g')" "$user_plist" 2>/dev/null || true

        # 2. Update System Preferences (Forced Policy)
        log "  → Updating system-wide policy via sudo..."
        
        # We'll use a temporary file to create a clean plist with both keys
        local tmp_plist
        tmp_plist=$(mktemp).plist
        
        cat <<EOF > "$tmp_plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>ExtensionInstallForcelist</key>
    <array>
$(for item in "${forcelist[@]}"; do echo "        <string>$item</string>"; done)
    </array>
    <key>ExtensionSettings</key>
    $settings_xml
</dict>
</plist>
EOF

        run_sudo plutil -convert binary1 "$tmp_plist"
        run_sudo cp "$tmp_plist" "/Library/Preferences/${plist_id}.plist"
        
        # Also copy to Managed Preferences (where macOS actually reads enterprise policies)
        run_sudo mkdir -p "/Library/Managed Preferences" "/Library/Managed Preferences/${USER}"
        run_sudo cp "$tmp_plist" "/Library/Managed Preferences/${plist_id}.plist"
        run_sudo cp "$tmp_plist" "/Library/Managed Preferences/${USER}/${plist_id}.plist"
        rm -f "$tmp_plist"
        
        run_sudo chmod 644 "/Library/Preferences/${plist_id}.plist"
        run_sudo chmod 644 "/Library/Managed Preferences/${plist_id}.plist"
        run_sudo chmod 644 "/Library/Managed Preferences/${USER}/${plist_id}.plist"

        # 3. Force macOS to reload preference cache
        log "  → Refreshing macOS preference cache..."
        run_sudo killall cfprefsd || true
        killall cfprefsd || true

        # 4. Arc Specific: External Extensions Folder Method
        if [ "$plist_id" = "company.thebrowser.Browser" ]; then
            log "  → Applying Arc-specific External Extensions files..."
            
            # Arc stores user data in "User Data", similar to Chrome. 
            local arc_user_data="$HOME/Library/Application Support/Arc/User Data"
            local arc_root_ext_dir="$HOME/Library/Application Support/Arc/External Extensions"
            local arc_user_data_ext_dir="${arc_user_data}/External Extensions"
            
            if [ -d "$arc_user_data" ]; then
                # 4.1 Create External Extensions in various possible locations
                mkdir -p "$arc_root_ext_dir" "$arc_user_data_ext_dir"
                
                # Also try in each profile's Extensions folder if we want to be aggressive 
                # (but actually the 'External Extensions' folder alongside 'Default' is the standard)
                
                for ext_id in "${extensions[@]}"; do
                    local json_content="{ \"external_update_url\": \"https://clients2.google.com/service/update2/crx\" }"
                    echo "$json_content" > "${arc_root_ext_dir}/${ext_id}.json"
                    echo "$json_content" > "${arc_user_data_ext_dir}/${ext_id}.json"
                    
                    # Try profile-specific directories too
                    for profile in "$arc_user_data"/Default "$arc_user_data"/Profile*; do
                        if [ -d "$profile" ]; then
                            local profile_ext_dir="${profile}/External Extensions"
                            mkdir -p "$profile_ext_dir"
                            echo "$json_content" > "${profile_ext_dir}/${ext_id}.json"
                        fi
                    done
                done
                log_ok "Arc external extensions definitions created in multiple locations."
                
                # 4.2 Check if Arc is running
                if pgrep -x "Arc" > /dev/null; then
                    log_warn "Arc is currently running. You MUST restart it for extensions to install."
                fi
            else
                log_warn "Arc User Data directory not found at $arc_user_data"
            fi
        fi

        log_ok "${browser_name} policies updated and cache cleared."
    else
        log "No extensions to install for ${browser_name}."
    fi
}

main() {
    local ff_exts=()
    local chrome_exts=()
    local arc_exts=()

    # Parse extensions.conf
    # Format for 'all': all|CHROME_ID|FIREFOX_SLUG|DESCRIPTION
    # Format for specific: browser|ID|DESCRIPTION
    while IFS='|' read -r browser id desc1 desc2 || [ -n "$browser" ]; do
        [[ "$browser" =~ ^#.* ]] || [ -z "$browser" ] && continue
        
        case "$browser" in
            all)
                # In 'all' mode: id is ChromeID, desc1 is FirefoxSlug
                chrome_exts+=("$id")
                arc_exts+=("$id")
                ff_exts+=("$desc1")
                ;;
            firefox) ff_exts+=("$id") ;;
            chrome)  chrome_exts+=("$id") ;;
            arc)     arc_exts+=("$id") ;;
        esac
    done < "$EXT_CONF"

    # Apply configurations
    [ ${#ff_exts[@]} -gt 0 ] && setup_firefox "${ff_exts[@]}"
    [ ${#chrome_exts[@]} -gt 0 ] && setup_chromium "Chrome" "com.google.Chrome" "${chrome_exts[@]}"
    [ ${#arc_exts[@]} -gt 0 ] && setup_chromium "Arc" "company.thebrowser.Browser" "${arc_exts[@]}"

    log_ok "Browser extension setup complete."
    log_warn "Note: You may need to restart your browsers for changes to take effect."
}

main
