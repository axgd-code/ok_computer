#!/bin/bash

# Do not exit the whole script on non-zero exit of commands that are used
# for probing remote services; treat unset variables as errors.
set -u

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load .env.local if available
if [ -f "${SCRIPT_DIR}/../.env.local" ]; then
    # shellcheck disable=SC1091
    source "${SCRIPT_DIR}/../.env.local"
fi

# Determine path to packages.conf file
if [ -n "${PACKAGES_CONF_DIR:-}" ] && [ -f "${PACKAGES_CONF_DIR}/packages.conf" ]; then
    PACKAGES_CONF="${PACKAGES_CONF_DIR}/packages.conf"
elif [ -f "${SCRIPT_DIR}/packages.conf" ]; then
    PACKAGES_CONF="${SCRIPT_DIR}/packages.conf"
else
    PACKAGES_CONF="${SCRIPT_DIR}/packages.conf.example"
fi

echo -e "${BLUE}Using config file:${NC} ${PACKAGES_CONF}"

# If the chosen PACKAGES_CONF is not writable (e.g. inside a bundled binary's
# temporary directory), fall back to a user-writable location under $HOME
if [ -f "${PACKAGES_CONF}" ]; then
    if [ ! -w "${PACKAGES_CONF}" ]; then
        echo -e "${YELLOW}Warning:${NC} ${PACKAGES_CONF} is not writable. Falling back to user config." 
        USER_DIR="${HOME}/.ok_computer"
        mkdir -p "${USER_DIR}"
        NEW_CONF="${USER_DIR}/packages.conf"
        if [ ! -f "${NEW_CONF}" ] && [ -f "${SCRIPT_DIR}/packages.conf" ]; then
            # seed from repository packages.conf if available
            cp "${SCRIPT_DIR}/packages.conf" "${NEW_CONF}" || true
        fi
        PACKAGES_CONF="${NEW_CONF}"
        echo -e "${BLUE}Using fallback config file:${NC} ${PACKAGES_CONF}"
    fi
else
    # If the file doesn't exist, check whether we can create it in place; if not, use fallback
    parent_dir=$(dirname "${PACKAGES_CONF}")
    if [ ! -w "${parent_dir}" ]; then
        echo -e "${YELLOW}Warning:${NC} Cannot create ${PACKAGES_CONF} in ${parent_dir}. Falling back to user config." 
        USER_DIR="${HOME}/.ok_computer"
        mkdir -p "${USER_DIR}"
        PACKAGES_CONF="${USER_DIR}/packages.conf"
        echo -e "${BLUE}Using fallback config file:${NC} ${PACKAGES_CONF}"
    fi
fi

# Check availability functions (simplified versions of app.sh)
check_homebrew_api() {
    local app=$1
    local type=$2
    
    if [ "$type" = "cask" ]; then
        curl -s -f -o /dev/null "https://formulae.brew.sh/api/cask/${app}.json"
    else
        curl -s -f -o /dev/null "https://formulae.brew.sh/api/formula/${app}.json"
    fi
}

check_chocolatey_api() {
    local app=$1
    curl -s -f "https://community.chocolatey.org/api/v2/Packages()?%24filter=tolower(Id)%20eq%20tolower('${app}')" | grep -q "${app}"
}

# Detect operating system
OS="$(uname -s)"
case "${OS}" in
    Darwin*)    MACHINE=Mac;;
    CYGWIN*|MINGW*|MSYS*)    MACHINE=Windows;;
    *)          MACHINE=Linux;;
esac

echo -e "${BLUE}Detected System:${NC} ${MACHINE}"

# Function to check if package exists in config
package_exists_in_config() {
    local name=$1
    if [ ! -f "$PACKAGES_CONF" ]; then
        return 1
    fi
    # Check if name appears in column 2 (Mac) or 3 (Win)
    # Format: TYPE|MAC|WIN|DESC
    if grep -qE "^[^|]+\|${name}\|" "$PACKAGES_CONF" || grep -qE "^[^|]+\|[^|]+\|${name}\|" "$PACKAGES_CONF"; then
        return 0
    fi
    return 1
}

count=0

process_package() {
    local name="$1"
    local type="$2"
    local origin="$3"
    
    if package_exists_in_config "$name"; then
        # echo "Skipping $name (already configured)"
        return
    fi

    echo -e "${GREEN}Found new package:${NC} $name ($type)"
    
    local mac_name="-"
    local win_name="-"
    local desc="Imported from $origin"

    if [ "$MACHINE" = "Mac" ]; then
        mac_name="$name"
        # Try to find match on Windows
        echo -n "  Checking duplicate on Windows... "
        if check_chocolatey_api "$name"; then
            win_name="$name"
            echo "found ($name)"
        else
            echo "not found"
        fi
    elif [ "$MACHINE" = "Windows" ]; then
        win_name="$name"
        # Try to find match on Mac
        echo -n "  Checking duplicate on macOS... "
        if check_homebrew_api "$name" "cask"; then
            mac_name="$name"
            type="cask"
            echo "found (cask)"
        elif check_homebrew_api "$name" "brew"; then
            mac_name="$name"
            if [ "$type" != "cask" ]; then type="brew"; fi
            echo "found (brew)"
        else
            echo "not found"
        fi
    fi

    echo "${type}|${mac_name}|${win_name}|${desc}" >> "$PACKAGES_CONF"
    ((count++))
}

if [ "$MACHINE" = "Mac" ]; then
    if command -v brew &>/dev/null; then
        echo -e "\n${BLUE}Searching Homebrew Formulas...${NC}"
        # using leaves to avoid dependencies
        for pkg in $(brew leaves); do
            process_package "$pkg" "brew" "macOS"
        done

        echo -e "\n${BLUE}Searching Homebrew Casks...${NC}"
        for pkg in $(brew list --cask); do
            process_package "$pkg" "cask" "macOS"
        done
    fi

    if command -v mas &>/dev/null; then
        echo -e "\n${BLUE}Searching Mac App Store...${NC}"
        # mas list output: "123456 App Name"
        # But config format is usually brew|mas|-|Desc ?? 
        # Actually existing config has 'brew|mas|-|Mac App Store CLI' which refers to the mas tool itself.
        # ok_computer doesn't seem to have explicit 'mas' generic support in install logic yet? 
        # src/init_conf_macOs.sh usually handles 'mas' lines.
        # Let's verify src/init_conf_macOs.sh logic.
        # Assuming format 'mas|app_id|name|desc' or 'type|mac_name|...' where mac_name is id?
        # Let's stick to brew/cask for now to be safe unless we verify mas support.
        # Skipping 'mas' for now to avoid breaking config with IDs.
        echo "Skipping MAS apps (auto-import not fully supported yet)"
    fi

elif [ "$MACHINE" = "Windows" ]; then
    if command -v choco &>/dev/null; then
        echo -e "\n${BLUE}Searching Chocolatey packages...${NC}"
        # choco list -lo -r returns "name|version"
        # use -r for pipe delimited
        choco list --local-only --limit-output | while IFS='|' read -r name ver; do
            # Filter out chocolatey itself or common lib packages?
            if [ "$name" = "chocolatey" ]; then continue; fi
            
            # Heuristic for type: default to brew (CLI) or cask (GUI)?
            # Hard to know. Let's assume 'cask' for everything on Windows default as usually people install tools.
            # OR check if it exists as a cask on mac?
            process_package "$name" "brew" "Windows" 
        done
    else
        echo "Chocolatey not found."
    fi
else
    echo "Linux import not implemented yet."
fi

echo -e "\n${GREEN}Done!${NC} Added $count new packages to $PACKAGES_CONF"

# Explicit successful exit; avoid relying on `set -e` behavior.
exit 0
