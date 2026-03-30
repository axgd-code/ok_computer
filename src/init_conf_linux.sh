#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "${SCRIPT_DIR}/../.env.local" ]; then
    # shellcheck disable=SC1091
    source "${SCRIPT_DIR}/../.env.local"
fi

if [ -n "${PACKAGES_CONF_DIR:-}" ] && [ -f "${PACKAGES_CONF_DIR}/system_settings.conf" ]; then
    SETTINGS_CONF="${PACKAGES_CONF_DIR}/system_settings.conf"
elif [ -f "${SCRIPT_DIR}/system_settings.conf" ]; then
    SETTINGS_CONF="${SCRIPT_DIR}/system_settings.conf"
else
    SETTINGS_CONF="${SCRIPT_DIR}/system_settings.conf.example"
fi

echo "Configuring Linux system settings..."

if ! command -v gsettings >/dev/null 2>&1; then
    echo "gsettings not available; skipping Linux desktop settings."
    exit 0
fi

as_bool() {
    case "$(echo "${1:-}" | tr '[:upper:]' '[:lower:]')" in
        1|true|yes|on) echo "true" ;;
        *) echo "false" ;;
    esac
}

apply_linux_setting() {
    local key="$1"
    local value="$2"
    local b
    b="$(as_bool "$value")"

    case "$key" in
        tap_to_click)
            gsettings set org.gnome.desktop.peripherals.touchpad tap-to-click "$b" 2>/dev/null || true
            ;;
        natural_scroll)
            gsettings set org.gnome.desktop.peripherals.touchpad natural-scroll "$b" 2>/dev/null || true
            ;;
        clock_24h)
            if [ "$b" = "true" ]; then
                gsettings set org.gnome.desktop.interface clock-format '24h' 2>/dev/null || true
            else
                gsettings set org.gnome.desktop.interface clock-format '12h' 2>/dev/null || true
            fi
            ;;
        dark_mode)
            if [ "$b" = "true" ]; then
                gsettings set org.gnome.desktop.interface color-scheme 'prefer-dark' 2>/dev/null || true
            else
                gsettings set org.gnome.desktop.interface color-scheme 'default' 2>/dev/null || true
            fi
            ;;
        show_file_extensions)
            # GNOME has no universal "always show extensions" equivalent; best effort skip.
            echo "  - show_file_extensions: not universally supported on Linux desktops (skipped)"
            ;;
        dock_autohide|dock_position|show_recent_apps|textedit_plain_text|time_machine_offer_disks)
            echo "  - ${key}: unsupported on Linux (skipped)"
            ;;
        *)
            echo "  - ${key}: unknown setting (skipped)"
            ;;
    esac
}

while IFS='|' read -r key mac_value win_value linux_value desc; do
    [[ "$key" =~ ^#.*$ ]] && continue
    [[ -z "$key" ]] && continue

    if [ -z "${linux_value:-}" ] || [ "$linux_value" = "-" ]; then
        continue
    fi

    echo "  - Applying ${key}: ${linux_value}"
    apply_linux_setting "$key" "$linux_value"
done < "${SETTINGS_CONF}"

echo "Linux system settings configuration completed"
