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

echo "Configuring macOS system settings..."

as_bool() {
	case "$(echo "${1:-}" | tr '[:upper:]' '[:lower:]')" in
		1|true|yes|on) echo "true" ;;
		*) echo "false" ;;
	esac
}

apply_macos_setting() {
	local key="$1"
	local value="$2"
	local b
	b="$(as_bool "$value")"

	case "$key" in
		dock_autohide)
			defaults write com.apple.dock autohide -bool "$b"
			;;
		dock_position)
			defaults write com.apple.dock orientation -string "$value"
			;;
		show_recent_apps)
			defaults write com.apple.dock show-recents -bool "$b"
			;;
		show_file_extensions)
			defaults write NSGlobalDomain AppleShowAllExtensions -bool "$b"
			;;
		tap_to_click)
			if [ "$b" = "true" ]; then
				defaults write com.apple.driver.AppleBluetoothMultitouch.trackpad Clicking -bool true
				defaults -currentHost write NSGlobalDomain com.apple.mouse.tapBehavior -int 1
			else
				defaults write com.apple.driver.AppleBluetoothMultitouch.trackpad Clicking -bool false
				defaults -currentHost write NSGlobalDomain com.apple.mouse.tapBehavior -int 0
			fi
			;;
		natural_scroll)
			defaults write NSGlobalDomain com.apple.swipescrolldirection -bool "$b"
			;;
		clock_24h)
			if [ "$b" = "true" ]; then
				defaults write com.apple.menuextra.clock DateFormat -string '"EEE d MMM HH:mm"'
			else
				defaults write com.apple.menuextra.clock DateFormat -string '"EEE d MMM h:mm a"'
			fi
			;;
		dark_mode)
			if [ "$b" = "true" ]; then
				osascript -e 'tell application "System Events" to tell appearance preferences to set dark mode to true' >/dev/null 2>&1 || true
			else
				osascript -e 'tell application "System Events" to tell appearance preferences to set dark mode to false' >/dev/null 2>&1 || true
			fi
			;;
		textedit_plain_text)
			if [ "$b" = "true" ]; then
				defaults write com.apple.TextEdit RichText -bool false
			else
				defaults write com.apple.TextEdit RichText -bool true
			fi
			;;
		time_machine_offer_disks)
			# macOS setting is inverted: DoNotOfferNewDisksForBackup
			if [ "$b" = "true" ]; then
				defaults write com.apple.TimeMachine DoNotOfferNewDisksForBackup -bool false
			else
				defaults write com.apple.TimeMachine DoNotOfferNewDisksForBackup -bool true
			fi
			;;
		*)
			echo "  - ${key}: unknown setting (skipped)"
			;;
	esac
}

while IFS='|' read -r key mac_value win_value linux_value desc; do
	[[ "$key" =~ ^#.*$ ]] && continue
	[[ -z "$key" ]] && continue

	if [ -z "${mac_value:-}" ] || [ "$mac_value" = "-" ]; then
		continue
	fi

	echo "  - Applying ${key}: ${mac_value}"
	apply_macos_setting "$key" "$mac_value"
done < "${SETTINGS_CONF}"

killall Dock >/dev/null 2>&1 || true
killall Finder >/dev/null 2>&1 || true

echo "macOS system settings configuration completed"