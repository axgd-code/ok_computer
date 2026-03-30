#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load .env.local if available
if [ -f "${SCRIPT_DIR}/../.env.local" ]; then
    # shellcheck disable=SC1091
    source "${SCRIPT_DIR}/../.env.local"
fi

# Determine path to packages.conf
if [ -n "${PACKAGES_CONF_DIR:-}" ] && [ -f "${PACKAGES_CONF_DIR}/packages.conf" ]; then
    PACKAGES_CONF="${PACKAGES_CONF_DIR}/packages.conf"
elif [ -f "${SCRIPT_DIR}/packages.conf" ]; then
    PACKAGES_CONF="${SCRIPT_DIR}/packages.conf"
else
    PACKAGES_CONF="${SCRIPT_DIR}/packages.conf.example"
fi

# Determine path to system_settings.conf
if [ -n "${PACKAGES_CONF_DIR:-}" ] && [ -f "${PACKAGES_CONF_DIR}/system_settings.conf" ]; then
    SETTINGS_CONF="${PACKAGES_CONF_DIR}/system_settings.conf"
elif [ -f "${SCRIPT_DIR}/system_settings.conf" ]; then
    SETTINGS_CONF="${SCRIPT_DIR}/system_settings.conf"
else
    SETTINGS_CONF="${SCRIPT_DIR}/system_settings.conf.example"
fi

echo "Configuring Windows..."

# Install and configure Chocolatey if needed
if ! command -v choco &> /dev/null; then
    echo "Installing Chocolatey..."
    # For Git Bash/WSL, use PowerShell to install Chocolatey
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))"
    
    # Reload PATH
    export PATH="$PATH:/c/ProgramData/chocolatey/bin"
fi

echo "Installing applications via Chocolatey..."

# Lecture du fichier packages.conf et installation des packages Windows
while IFS='|' read -r type mac_name win_name desc; do
    # Ignore comments and empty lines
    [[ "$type" =~ ^#.*$ ]] && continue
    [[ -z "$type" ]] && continue
    
    # Install if the package exists for Windows
    if [ "$win_name" != "-" ] && [ -n "$win_name" ]; then
        echo "  - Installation: $win_name ($desc)"
        choco install -y "$win_name"
    fi
done < "${PACKAGES_CONF}"

echo "Applying Windows settings..."

as_bool() {
    case "$(echo "${1:-}" | tr '[:upper:]' '[:lower:]')" in
        1|true|yes|on) echo "true" ;;
        *) echo "false" ;;
    esac
}

ps_exec() {
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$1" >/dev/null 2>&1 || true
}

apply_windows_setting() {
    local key="$1"
    local value="$2"
    local b
    b="$(as_bool "$value")"

    case "$key" in
        show_file_extensions)
            if [ "$b" = "true" ]; then
                ps_exec 'Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced" -Name "HideFileExt" -Type DWord -Value 0'
            else
                ps_exec 'Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced" -Name "HideFileExt" -Type DWord -Value 1'
            fi
            ;;
        clock_24h)
            if [ "$b" = "true" ]; then
                ps_exec 'Set-ItemProperty -Path "HKCU:\Control Panel\International" -Name "iTime" -Value "1"'
            else
                ps_exec 'Set-ItemProperty -Path "HKCU:\Control Panel\International" -Name "iTime" -Value "0"'
            fi
            ;;
        dark_mode)
            if [ "$b" = "true" ]; then
                ps_exec 'Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize" -Name "AppsUseLightTheme" -Type DWord -Value 0'
                ps_exec 'Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize" -Name "SystemUsesLightTheme" -Type DWord -Value 0'
            else
                ps_exec 'Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize" -Name "AppsUseLightTheme" -Type DWord -Value 1'
                ps_exec 'Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize" -Name "SystemUsesLightTheme" -Type DWord -Value 1'
            fi
            ;;
        dock_autohide|tap_to_click|natural_scroll|dock_position|show_recent_apps|textedit_plain_text|time_machine_offer_disks)
            echo "  - ${key}: unsupported or hardware-dependent on Windows (skipped)"
            ;;
        *)
            echo "  - ${key}: unknown setting (skipped)"
            ;;
    esac
}

while IFS='|' read -r key mac_value win_value linux_value desc; do
    [[ "$key" =~ ^#.*$ ]] && continue
    [[ -z "$key" ]] && continue

    if [ -z "${win_value:-}" ] || [ "$win_value" = "-" ]; then
        continue
    fi

    echo "  - Applying ${key}: ${win_value}"
    apply_windows_setting "$key" "$win_value"
done < "${SETTINGS_CONF}"

# Git configuration (if needed)
# git config --global user.name "Votre Nom"
# git config --global user.email "votre.email@example.com"

echo "Configuration completed!"
echo "Note: Some applications may require a Windows restart to work correctly."
