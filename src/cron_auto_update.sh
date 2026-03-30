#!/bin/bash

# Called every minute by system cron.
# Runs update.sh only when AUTO_UPDATE_ENABLED=true and interval elapsed.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="$HOME/.ok_computer"
LOG_DIR="$STATE_DIR/logs"
STATE_FILE="$STATE_DIR/.auto_update_last_run"

mkdir -p "$STATE_DIR" "$LOG_DIR"

ENV_LOCAL="$HOME/.env.local"
if [ -f "$ENV_LOCAL" ]; then
    # shellcheck disable=SC1090
    source "$ENV_LOCAL"
fi

enabled="${AUTO_UPDATE_ENABLED:-false}"
interval_min="${AUTO_UPDATE_INTERVAL_MINUTES:-1440}"

case "$(echo "$enabled" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on) ;;
    *) exit 0 ;;
esac

if ! [[ "$interval_min" =~ ^[0-9]+$ ]]; then
    interval_min=1440
fi
if [ "$interval_min" -lt 1 ]; then
    interval_min=1
fi

UPDATE_SCRIPT="$SCRIPT_DIR/update.sh"
if [ ! -f "$UPDATE_SCRIPT" ]; then
    echo "cron_auto_update: update.sh not found at $UPDATE_SCRIPT" >> "$LOG_DIR/auto_update_error.log"
    exit 1
fi

now_ts=$(date +%s)
last_ts=0
if [ -f "$STATE_FILE" ]; then
    last_ts=$(cat "$STATE_FILE" 2>/dev/null || echo 0)
fi

elapsed=$((now_ts - last_ts))
required=$((interval_min * 60))

if [ "$elapsed" -lt "$required" ]; then
    exit 0
fi

echo "$now_ts" > "$STATE_FILE"

/bin/bash "$UPDATE_SCRIPT" >> "$LOG_DIR/auto_update.log" 2>> "$LOG_DIR/auto_update_error.log"
