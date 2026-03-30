#!/bin/bash
#
# Manage OKC auto-update cron job independently.
# Usage:
#   manage_cron.sh install   - Install/enable the cron job
#   manage_cron.sh uninstall - Remove the cron job
#   manage_cron.sh status    - Show cron job status
#   manage_cron.sh help      - Print this help

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CRON_UPDATE_TAG='# OKC_AUTO_UPDATE'
CRON_RUNNER_SCRIPT="$SCRIPT_DIR/cron_auto_update.sh"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $*"
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[✗]${NC} $*" >&2
}

# Check if crontab command is available
check_crontab() {
    if ! command -v crontab &> /dev/null; then
        log_error "crontab command not found. Cron is not available on this system."
        return 1
    fi
    return 0
}

# Read current crontab, filter out OKC entries
read_crontab_filtered() {
    crontab -l 2>/dev/null | grep -v "$CRON_UPDATE_TAG" || true
}

# Build the cron line
build_cron_line() {
    if [ ! -f "$CRON_RUNNER_SCRIPT" ]; then
        log_error "cron_auto_update.sh not found at $CRON_RUNNER_SCRIPT"
        return 1
    fi
    echo "* * * * * /bin/bash \"$CRON_RUNNER_SCRIPT\" >/dev/null 2>&1 $CRON_UPDATE_TAG"
}

# Install cron job
install_cron() {
    check_crontab || return 1
    
    if grep -q "$CRON_UPDATE_TAG" <(crontab -l 2>/dev/null) 2>/dev/null; then
        log_warning "Cron job already installed. Skipping."
        return 0
    fi
    
    local cron_line
    cron_line=$(build_cron_line) || return 1
    
    (read_crontab_filtered; echo "$cron_line") | crontab - || {
        log_error "Failed to install cron job"
        return 1
    }
    
    log_success "Cron job installed successfully"
    log_info "Schedule: Every minute"
    log_info "Script: $CRON_RUNNER_SCRIPT"
    return 0
}

# Uninstall cron job
uninstall_cron() {
    check_crontab || return 1
    
    if ! grep -q "$CRON_UPDATE_TAG" <(crontab -l 2>/dev/null) 2>/dev/null; then
        log_warning "Cron job not installed. Nothing to remove."
        return 0
    fi
    
    read_crontab_filtered | crontab - || {
        log_error "Failed to remove cron job"
        return 1
    }
    
    log_success "Cron job removed successfully"
    return 0
}

# Show cron status
show_status() {
    check_crontab || return 1
    
    log_info "Checking OKC cron status..."
    
    if grep -q "$CRON_UPDATE_TAG" <(crontab -l 2>/dev/null) 2>/dev/null; then
        log_success "Cron job is INSTALLED"
        echo ""
        echo "Cron entry:"
        crontab -l 2>/dev/null | grep "$CRON_UPDATE_TAG"
        echo ""
        
        if [ -f "$HOME/.env.local" ]; then
            echo "Configuration (.env.local):"
            grep -E "AUTO_UPDATE_ENABLED|AUTO_UPDATE_INTERVAL" "$HOME/.env.local" | sed 's/^/  /'
        fi
        
        if [ -f "$HOME/.ok_computer/.auto_update_last_run" ]; then
            local last_run
            last_run=$(cat "$HOME/.ok_computer/.auto_update_last_run")
            echo ""
            echo "Last execution timestamp: $last_run"
            if command -v date &> /dev/null; then
                echo "Last execution: $(date -r "$last_run" 2>/dev/null || echo 'N/A')"
            fi
        fi
        
        return 0
    else
        log_warning "Cron job is NOT installed"
        return 1
    fi
}

# Print help
print_help() {
    cat << 'EOF'
OKC Cron Manager
================

Manage automatic updates via system cron job.
The cron job runs every minute and executes update.sh only when the configured interval has elapsed.

Usage:
  manage_cron.sh install    - Install/enable the cron job
  manage_cron.sh uninstall  - Remove the cron job  
  manage_cron.sh status     - Show cron job status
  manage_cron.sh help       - Print this help message

Configuration:
  ~/.env.local:
    AUTO_UPDATE_ENABLED='true'        - Enable/disable auto-updates (controls cron job)
    AUTO_UPDATE_INTERVAL_MINUTES=1440 - Run update.sh every N minutes (default: 1440 = 1 day)

Logs:
  ~/.ok_computer/logs/auto_update.log       - Main log
  ~/.ok_computer/logs/auto_update_error.log - Error log
  ~/.ok_computer/.auto_update_last_run      - Timestamp of last execution

Persistence:
  The cron job persists at the system level and will continue running even after
  the application is closed, as long as AUTO_UPDATE_ENABLED='true' in ~/.env.local.

Example:
  # Enable and install the cron job
  bash manage_cron.sh install
  
  # Check status
  bash manage_cron.sh status
  
  # Disable by removing from crontab
  bash manage_cron.sh uninstall

EOF
}

# Main entrypoint
main() {
    local cmd="${1:-status}"
    
    case "$cmd" in
        install)
            install_cron
            ;;
        uninstall|remove|disable)
            uninstall_cron
            ;;
        status)
            show_status
            ;;
        help|-h|--help)
            print_help
            ;;
        *)
            log_error "Unknown command: $cmd"
            echo ""
            print_help
            return 1
            ;;
    esac
}

main "$@"
