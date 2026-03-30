#!/bin/bash

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE=""
ENV_EXAMPLE=""

resolve_env_file() {
    local candidates=(
        "${SCRIPT_DIR}/.env.local"
        "${SCRIPT_DIR}/../.env.local"
        "${HOME}/.env.local"
    )

    for candidate in "${candidates[@]}"; do
        if [ -f "${candidate}" ]; then
            echo "${candidate}"
            return 0
        fi
    done

    echo "${HOME}/.env.local"
}

resolve_env_example() {
    local candidates=(
        "${SCRIPT_DIR}/.env.example"
        "${SCRIPT_DIR}/../.env.example"
    )

    for candidate in "${candidates[@]}"; do
        if [ -f "${candidate}" ]; then
            echo "${candidate}"
            return 0
        fi
    done

    echo "${SCRIPT_DIR}/../.env.example"
}

ENV_FILE="$(resolve_env_file)"
ENV_EXAMPLE="$(resolve_env_example)"

DEFAULT_SHARED_DIRNAME="ok_computer_shared"

resolve_shared_root() {
    if [ -z "${SYNC_DIR}" ]; then
        return 1
    fi

    local legacy_markers=(
        "${SYNC_DIR}/dotfiles"
        "${SYNC_DIR}/packages.conf"
        "${SYNC_DIR}/extensions.conf"
        "${SYNC_DIR}/system_settings.conf"
        "${SYNC_DIR}/exports"
    )

    for marker in "${legacy_markers[@]}"; do
        if [ -e "${marker}" ]; then
            echo "${SYNC_DIR}"
            return 0
        fi
    done

    echo "${SYNC_DIR}/${DEFAULT_SHARED_DIRNAME}"
}

shared_root_or_fail() {
    local shared_root
    shared_root="$(resolve_shared_root)" || return 1

    if [ ! -d "${SYNC_DIR}" ]; then
        echo -e "${RED}✗ Error: SYNC_DIR does not exist: ${SYNC_DIR}${NC}"
        return 1
    fi

    echo "${shared_root}"
}

resolve_shared_config_target_dir() {
    local target_dir="${PACKAGES_CONF_DIR}"

    if [ -z "${target_dir}" ]; then
        target_dir="$(resolve_shared_root 2>/dev/null || true)"
    fi

    if [ -z "${target_dir}" ]; then
        return 1
    fi

    echo "${target_dir}"
}

# Load configuration
load_config() {
    if [ ! -f "${ENV_FILE}" ]; then
        echo -e "${YELLOW}⚠ The file ${ENV_FILE} does not exist${NC}"
        echo -e "${BLUE}Creating from template...${NC}"
        cp "${ENV_EXAMPLE}" "${ENV_FILE}"
        echo -e "${GREEN}✓ File created${NC}"
        echo -e "${YELLOW}⚠ Please edit ${ENV_FILE} and configure SYNC_DIR${NC}"
        return 1
    fi
    
    # Charger les variables
    source "${ENV_FILE}"
}

# Show help
show_help() {
    cat << EOF
${BLUE}Usage:${NC} bash dotfiles.sh [COMMAND]

${BLUE}Commands:${NC}
  ${GREEN}init${NC}              Initialize dotfiles synchronization
  ${GREEN}setup${NC}              Setup dotfiles symlinks
  ${GREEN}sync${NC}               Sync changes from home to sync folder
  ${GREEN}restore${NC}            Restore from sync folder to home
    ${GREEN}shared${NC}             Manage shared config files
    ${GREEN}init-from-shared${NC}   Initialize machine from shared drive
  ${GREEN}status${NC}             Show dotfiles status
  ${GREEN}list${NC}               List tracked dotfiles
  ${GREEN}config${NC}             Show current configuration
  ${GREEN}packages${NC}           Manage packages.conf synchronization
  ${GREEN}obsidian${NC}           Manage Obsidian vault synchronization
  ${GREEN}vscode${NC}             Manage VS Code settings synchronization
  ${GREEN}--help${NC}             Show this help

${BLUE}Configuration:${NC}
  Edit ${ENV_FILE} to set SYNC_DIR, PACKAGES_CONF_DIR, OBSIDIAN_VAULT, VSCODE_CONFIG
        Shared Ok Computer files are stored in SYNC_DIR/${DEFAULT_SHARED_DIRNAME}/ by default.
    Dotfiles sync is manual. No cron is installed by this script.

${BLUE}Dotfiles tracked:${NC}
  - .bashrc / .zshrc
  - .gitconfig
  - .ssh/config
  - .vimrc / .config/nvim
  - packages.conf
  - Obsidian vault
  - VS Code settings
EOF
}

# List dotfiles to sync
get_dotfiles() {
    cat << 'EOF'
.bashrc
.zshrc
.gitconfig
.git-credentials
.vimrc
.ssh/config
.ssh/authorized_keys
.config/nvim
.config/helix
.config/starship.toml
.config/alacritty
.config/kitty
EOF
}

# Initialize synchronization
init_sync() {
    local shared_root
    shared_root="$(shared_root_or_fail)" || return 1
    
    echo -e "${BLUE}Initializing dotfiles synchronization...${NC}"
    echo -e "Destination: ${GREEN}${shared_root}${NC}\n"
    
    # Créer le dossier dotfiles s'il n'existe pas
    local DOTFILES_DIR="${shared_root}/dotfiles"
    mkdir -p "${DOTFILES_DIR}"
    
    echo -e "${BLUE}Copying existing dotfiles...${NC}"
    
    local count=0
    while IFS= read -r dotfile; do
        [ -z "$dotfile" ] && continue
        
        local home_path="${HOME}/${dotfile}"
        local sync_path="${DOTFILES_DIR}/${dotfile##*/}"  # Nom du fichier seulement
        
        if [ -e "${home_path}" ]; then
            cp -r "${home_path}" "${sync_path}"
            echo -e "  ${GREEN}✓${NC} ${dotfile}"
            ((count++))
        fi
    done < <(get_dotfiles)
    
    echo -e "\n${GREEN}✓ Initialization complete (${count} files)${NC}"
    echo -e "Next step: ${BLUE}bash dotfiles.sh setup${NC}"
    echo -e "${YELLOW}Note:${NC} synchronization remains manual; run sync or restore when needed."
}

# Create symlinks
setup_symlinks() {
    local shared_root
    shared_root="$(shared_root_or_fail)" || return 1
    
    local DOTFILES_DIR="${shared_root}/dotfiles"
    
    if [ ! -d "${DOTFILES_DIR}" ]; then
        echo -e "${RED}✗ Error: ${DOTFILES_DIR} does not exist${NC}"
        echo -e "${YELLOW}Run first: ${BLUE}bash dotfiles.sh init${NC}"
        return 1
    fi
    
    echo -e "${BLUE}Setting up symlinks...${NC}\n"
    
    local count=0
    while IFS= read -r dotfile; do
        [ -z "$dotfile" ] && continue
        
        local home_path="${HOME}/${dotfile}"
        local filename="${dotfile##*/}"
        local sync_path="${DOTFILES_DIR}/${filename}"
        
        if [ ! -e "${sync_path}" ]; then
            continue
        fi
        
        # Créer les répertoires parent s'il faut
        mkdir -p "$(dirname "${home_path}")"
        
        # Supprimer l'original s'il existe et n'est pas un symlink
        if [ -e "${home_path}" ] && [ ! -L "${home_path}" ]; then
            echo -e "  ${YELLOW}⚠${NC} Backup: ${dotfile} → ${dotfile}.backup"
            mv "${home_path}" "${home_path}.backup"
        fi
        
        # Créer le symlink
        if [ ! -L "${home_path}" ]; then
            ln -s "${sync_path}" "${home_path}"
            echo -e "  ${GREEN}✓${NC} Symlink: ${dotfile} → ${filename}"
            ((count++))
        else
            echo -e "  ${BLUE}→${NC} Already linked: ${dotfile}"
        fi
    done < <(get_dotfiles)
    
    echo -e "\n${GREEN}✓ Setup complete (${count} symlinks created)${NC}"
}

# Sync from home to sync folder
sync_to_remote() {
    local shared_root
    shared_root="$(shared_root_or_fail)" || return 1
    
    local DOTFILES_DIR="${shared_root}/dotfiles"
    mkdir -p "${DOTFILES_DIR}"
    
    echo -e "${BLUE}Syncing to sync folder...${NC}\n"
    
    local count=0
    while IFS= read -r dotfile; do
        [ -z "$dotfile" ] && continue
        
        local home_path="${HOME}/${dotfile}"
        local filename="${dotfile##*/}"
        local sync_path="${DOTFILES_DIR}/${filename}"
        
        if [ -e "${home_path}" ]; then
            if [ -L "${home_path}" ]; then
                # C'est un symlink, pas besoin de copier
                echo -e "  ${BLUE}→${NC} Linked: ${dotfile}"
            else
                cp -r "${home_path}" "${sync_path}"
                echo -e "  ${GREEN}✓${NC} Copied: ${dotfile}"
                ((count++))
            fi
        fi
    done < <(get_dotfiles)
    
    echo -e "\n${GREEN}✓ Sync complete (${count} files)${NC}"
}

# Restore from sync folder to home
restore_from_remote() {
    local shared_root
    shared_root="$(shared_root_or_fail)" || return 1
    
    local DOTFILES_DIR="${shared_root}/dotfiles"
    
    if [ ! -d "${DOTFILES_DIR}" ]; then
        echo -e "${RED}✗ Erreur: ${DOTFILES_DIR} n'existe pas${NC}"
        return 1
    fi
    
    echo -e "${BLUE}Restoring from sync folder...${NC}\n"
    
    local count=0
    while IFS= read -r dotfile; do
        [ -z "$dotfile" ] && continue
        
        local home_path="${HOME}/${dotfile}"
        local filename="${dotfile##*/}"
        local sync_path="${DOTFILES_DIR}/${filename}"
        
        if [ -e "${sync_path}" ]; then
            mkdir -p "$(dirname "${home_path}")"
            
            if [ ! -L "${home_path}" ]; then
                if [ -e "${home_path}" ]; then
                    mv "${home_path}" "${home_path}.backup"
                    echo -e "  ${YELLOW}⚠${NC} Backup: ${dotfile}"
                fi
                cp -r "${sync_path}" "${home_path}"
                echo -e "  ${GREEN}✓${NC} Restored: ${dotfile}"
                ((count++))
            fi
        fi
    done < <(get_dotfiles)
    
    echo -e "\n${GREEN}✓ Restore complete (${count} files)${NC}"
}

# Show status
show_status() {
    echo -e "${BLUE}Dotfiles sync status:${NC}\n"
    
    if [ -z "${SYNC_DIR}" ]; then
        echo -e "  ${RED}✗ SYNC_DIR not configured${NC}"
        return 1
    fi
    
    if [ ! -d "${SYNC_DIR}" ]; then
        echo -e "  ${RED}✗ SYNC_DIR does not exist: ${SYNC_DIR}${NC}"
        return 1
    fi
    
    local shared_root
    shared_root="$(resolve_shared_root)"

    echo -e "  ${GREEN}✓ SYNC_DIR: ${SYNC_DIR}${NC}"
    echo -e "  ${GREEN}✓ Shared root: ${shared_root}${NC}"
    
    local DOTFILES_DIR="${shared_root}/dotfiles"
    if [ -d "${DOTFILES_DIR}" ]; then
        echo -e "  ${GREEN}✓ Dotfiles folder found${NC}"
        
        local linked=0
        local files=0
        
        while IFS= read -r dotfile; do
            [ -z "$dotfile" ] && continue
            local home_path="${HOME}/${dotfile}"
            if [ -L "${home_path}" ]; then
                ((linked++))
            fi
            ((files++))
        done < <(get_dotfiles)
        
        echo -e "  ${GREEN}✓ ${linked}/${files} dotfiles linked${NC}"
    else
        echo -e "  ${YELLOW}⚠ Dotfiles folder not found${NC}"
    fi

    echo ""
    manage_shared_configs status 2>/dev/null || true
}

# List dotfiles
list_dotfiles() {
    echo -e "${BLUE}Tracked dotfiles:${NC}\n"
    
    get_dotfiles | while read -r dotfile; do
        [ -z "$dotfile" ] && continue
        
        local home_path="${HOME}/${dotfile}"
        local filename="${dotfile##*/}"
        
        if [ -L "${home_path}" ]; then
            echo -e "  ${GREEN}✓${NC} ${dotfile} → $(readlink "${home_path}")"
        elif [ -e "${home_path}" ]; then
            echo -e "  ${YELLOW}✗${NC} ${dotfile} (not linked)"
        else
            echo -e "  ${BLUE}○${NC} ${dotfile} (missing)"
        fi
    done
}

# Show configuration
show_config() {
    echo -e "${BLUE}Configuration:${NC}\n"
    echo -e "  Config file: ${ENV_FILE}"
    
    if [ -f "${ENV_FILE}" ]; then
        echo -e "  ${GREEN}✓ Configuration found${NC}\n"
        echo -e "${BLUE}Content:${NC}"
        grep -v "^#" "${ENV_FILE}" | grep -v "^$" | sed 's/^/    /'
    else
        echo -e "  ${RED}✗ Configuration not found${NC}"
    fi
}

# Execute the command
if [ -z "$1" ] || [ "$1" = "--help" ] || [ "$1" = "-h" ] || [ "$1" = "help" ]; then
    show_help
    exit 0
fi

# Load configuration
if ! load_config; then
    if [ "$1" != "config" ] && [ "$1" != "init" ]; then
        echo -e "${RED}✗ Configuration required${NC}"
        exit 1
    fi
fi

# Exécuter la commande
if [ -z "$1" ] || [ "$1" = "--help" ] || [ "$1" = "-h" ] || [ "$1" = "help" ]; then
    show_help
    exit 0
fi

# Load configuration
if ! load_config; then
    if [ "$1" != "config" ] && [ "$1" != "init" ]; then
        echo -e "${RED}✗ Configuration requise${NC}"
        exit 1
    fi
fi

# Function to manage Obsidian
manage_obsidian() {
    local cmd=$1
    
    if [ -z "${OBSIDIAN_VAULT}" ]; then
        echo -e "${YELLOW}⚠ OBSIDIAN_VAULT not configured${NC}"
        return 1
    fi
    
    if [ ! -d "${OBSIDIAN_VAULT}" ]; then
        echo -e "${YELLOW}⚠ Obsidian folder does not exist: ${OBSIDIAN_VAULT}${NC}"
        return 1
    fi
    
    # Path to local Obsidian vault
    local OBSIDIAN_LOCAL="${HOME}/Obsidian"
    
    case "${cmd}" in
        sync)
            echo -e "${BLUE}Syncing Obsidian to ${OBSIDIAN_VAULT}...${NC}"
            if [ -d "${OBSIDIAN_LOCAL}" ]; then
                rsync -av "${OBSIDIAN_LOCAL}/" "${OBSIDIAN_VAULT}/"
                echo -e "${GREEN}✓ Obsidian sync complete${NC}"
            else
                echo -e "${YELLOW}⚠ Local vault not found${NC}"
            fi
            ;;
        restore)
            echo -e "${BLUE}Restoring Obsidian from ${OBSIDIAN_VAULT}...${NC}"
            mkdir -p "${OBSIDIAN_LOCAL}"
            rsync -av "${OBSIDIAN_VAULT}/" "${OBSIDIAN_LOCAL}/"
            echo -e "${GREEN}✓ Obsidian restore complete${NC}"
            ;;
        status)
            echo -e "${BLUE}Obsidian status:${NC}"
            echo -e "  Remote vault: ${GREEN}${OBSIDIAN_VAULT}${NC}"
            if [ -d "${OBSIDIAN_LOCAL}" ]; then
                local local_size=$(du -sh "${OBSIDIAN_LOCAL}" 2>/dev/null | cut -f1)
                echo -e "  Local vault: ${GREEN}${OBSIDIAN_LOCAL}${NC} (${local_size})"
            else
                echo -e "  Local vault: ${YELLOW}not found${NC}"
            fi
            ;;
    esac
}

# Function to manage VS Code
manage_vscode() {
    local cmd=$1
    
    if [ -z "${VSCODE_CONFIG}" ]; then
        echo -e "${YELLOW}⚠ VSCODE_CONFIG not configured${NC}"
        return 1
    fi
    
    if [ ! -d "${VSCODE_CONFIG}" ]; then
        echo -e "${YELLOW}⚠ VS Code folder does not exist: ${VSCODE_CONFIG}${NC}"
        return 1
    fi
    
    # Determine VS Code path depending on the system
    local VSCODE_LOCAL
    if [ "$(uname -s)" = "Darwin" ]; then
        VSCODE_LOCAL="${HOME}/Library/Application Support/Code"
    else
        VSCODE_LOCAL="${HOME}/.config/Code"
    fi
    
    case "${cmd}" in
        sync)
            echo -e "${BLUE}Syncing VS Code to ${VSCODE_CONFIG}...${NC}"
            if [ -d "${VSCODE_LOCAL}" ]; then
                rsync -av --exclude=workspaceStorage --exclude=CachedData "${VSCODE_LOCAL}/User/" "${VSCODE_CONFIG}/"
                echo -e "${GREEN}✓ VS Code sync complete${NC}"
            else
                echo -e "${YELLOW}⚠ Local VS Code configuration not found${NC}"
            fi
            ;;
        restore)
            echo -e "${BLUE}Restoring VS Code from ${VSCODE_CONFIG}...${NC}"
            mkdir -p "${VSCODE_LOCAL}/User"
            rsync -av "${VSCODE_CONFIG}/" "${VSCODE_LOCAL}/User/"
            echo -e "${GREEN}✓ VS Code restore complete${NC}"
            ;;
        status)
            echo -e "${BLUE}VS Code status:${NC}"
            echo -e "  Remote config: ${GREEN}${VSCODE_CONFIG}${NC}"
            if [ -d "${VSCODE_LOCAL}" ]; then
                local local_size=$(du -sh "${VSCODE_LOCAL}" 2>/dev/null | cut -f1)
                echo -e "  Local config: ${GREEN}${VSCODE_LOCAL}${NC} (${local_size})"
            else
                echo -e "  Local config: ${YELLOW}not found${NC}"
            fi
            ;;
    esac
}

# Manage packages.conf
manage_packages() {
    local cmd="${1:-status}"
    local target_dir="${PACKAGES_CONF_DIR}"
    
    if [ -z "${target_dir}" ]; then
        target_dir="$(resolve_shared_root 2>/dev/null || true)"
    fi

    if [ -z "${target_dir}" ]; then
        echo -e "${YELLOW}⚠ PACKAGES_CONF_DIR is not defined in ${ENV_FILE}${NC}"
        echo -e "${BLUE}Configure SYNC_DIR or PACKAGES_CONF_DIR first${NC}"
        return 1
    fi
    
    if [ ! -d "${target_dir}" ]; then
        echo -e "${YELLOW}⚠ Directory does not exist: ${target_dir}${NC}"
        echo -e "${BLUE}Creating directory...${NC}"
        mkdir -p "${target_dir}"
    fi
    
    local SOURCE_CONF="${SCRIPT_DIR}/packages.conf"
    local EXAMPLE_CONF="${SCRIPT_DIR}/packages.conf.example"
    local REMOTE_CONF="${target_dir}/packages.conf"
    
    case "${cmd}" in
        sync)
            echo -e "${BLUE}Syncing packages.conf to ${target_dir}...${NC}"
            if [ -f "${SOURCE_CONF}" ]; then
                cp "${SOURCE_CONF}" "${REMOTE_CONF}"
                echo -e "${GREEN}✓ packages.conf synced${NC}"
            elif [ -f "${EXAMPLE_CONF}" ]; then
                cp "${EXAMPLE_CONF}" "${REMOTE_CONF}"
                echo -e "${GREEN}✓ packages.conf.example copied as base${NC}"
            else
                echo -e "${RED}✗ No packages.conf file found${NC}"
                return 1
            fi
            ;;
        restore)
            echo -e "${BLUE}Restoring packages.conf from ${target_dir}...${NC}"
            if [ -f "${REMOTE_CONF}" ]; then
                cp "${REMOTE_CONF}" "${SOURCE_CONF}"
                echo -e "${GREEN}✓ packages.conf restored${NC}"
            else
                echo -e "${YELLOW}⚠ No remote packages.conf found${NC}"
                if [ -f "${EXAMPLE_CONF}" ]; then
                    echo -e "${BLUE}Copying example...${NC}"
                    cp "${EXAMPLE_CONF}" "${SOURCE_CONF}"
                    echo -e "${GREEN}✓ packages.conf created from example${NC}"
                fi
            fi
            ;;
        status)
            echo -e "  Remote dir: ${GREEN}${target_dir}${NC}"
            if [ -f "${REMOTE_CONF}" ]; then
                local line_count=$(wc -l < "${REMOTE_CONF}" 2>/dev/null | tr -d ' ')
                echo -e "  Remote file: ${GREEN}${REMOTE_CONF}${NC} (${line_count} lines)"
            else
                echo -e "  Remote file: ${YELLOW}not found${NC}"
            fi
            if [ -f "${SOURCE_CONF}" ]; then
                local line_count=$(wc -l < "${SOURCE_CONF}" 2>/dev/null | tr -d ' ')
                echo -e "  Local file: ${GREEN}${SOURCE_CONF}${NC} (${line_count} lines)"
            else
                echo -e "  Local file: ${YELLOW}using packages.conf.example${NC}"
            fi
            ;;
    esac
}

manage_shared_configs() {
    local cmd="${1:-status}"
    local target_dir
    target_dir="$(resolve_shared_config_target_dir 2>/dev/null || true)"

    if [ -z "${target_dir}" ]; then
        echo -e "${YELLOW}⚠ Shared configuration target is not defined${NC}"
        echo -e "${BLUE}Configure SYNC_DIR or PACKAGES_CONF_DIR first${NC}"
        return 1
    fi

    if [ ! -d "${target_dir}" ]; then
        mkdir -p "${target_dir}"
    fi

    local files=(packages.conf extensions.conf system_settings.conf)
    local synced=0
    local restored=0

    case "${cmd}" in
        sync)
            echo -e "${BLUE}Syncing shared configuration files to ${target_dir}...${NC}"
            for name in "${files[@]}"; do
                local source_path="${SCRIPT_DIR}/${name}"
                local example_path="${SCRIPT_DIR}/${name}.example"
                local target_path="${target_dir}/${name}"
                if [ -f "${source_path}" ]; then
                    cp "${source_path}" "${target_path}"
                    echo -e "  ${GREEN}✓${NC} ${name}"
                    ((synced++))
                elif [ -f "${example_path}" ]; then
                    cp "${example_path}" "${target_path}"
                    echo -e "  ${GREEN}✓${NC} ${name} (seeded from example)"
                    ((synced++))
                else
                    echo -e "  ${YELLOW}⚠${NC} ${name} missing locally"
                fi
            done
            echo -e "\n${GREEN}✓ Shared config sync complete (${synced} files)${NC}"
            ;;
        restore)
            echo -e "${BLUE}Restoring shared configuration files from ${target_dir}...${NC}"
            for name in "${files[@]}"; do
                local source_path="${target_dir}/${name}"
                local target_path="${SCRIPT_DIR}/${name}"
                if [ -f "${source_path}" ]; then
                    cp "${source_path}" "${target_path}"
                    echo -e "  ${GREEN}✓${NC} ${name}"
                    ((restored++))
                else
                    echo -e "  ${YELLOW}⚠${NC} ${name} not found in shared drive"
                fi
            done
            echo -e "\n${GREEN}✓ Shared config restore complete (${restored} files)${NC}"
            ;;
        status)
            echo -e "${BLUE}Shared configuration status:${NC}"
            echo -e "  Shared dir: ${GREEN}${target_dir}${NC}"
            for name in "${files[@]}"; do
                local source_path="${SCRIPT_DIR}/${name}"
                local target_path="${target_dir}/${name}"
                local local_label="${YELLOW}missing${NC}"
                local remote_label="${YELLOW}missing${NC}"
                [ -f "${source_path}" ] && local_label="${GREEN}present${NC}"
                [ -f "${target_path}" ] && remote_label="${GREEN}present${NC}"
                echo -e "  - ${name}: local ${local_label}, shared ${remote_label}"
            done
            ;;
        *)
            echo -e "${RED}✗ Unknown shared config action: ${cmd}${NC}"
            return 1
            ;;
    esac
}

init_from_shared_drive() {
    local shared_root
    shared_root="$(shared_root_or_fail)" || return 1

    echo -e "${BLUE}Initializing machine from shared drive...${NC}"
    echo -e "Shared root: ${GREEN}${shared_root}${NC}\n"

    manage_shared_configs restore || return 1

    if [ -d "${shared_root}/dotfiles" ]; then
        restore_from_remote || return 1
    else
        echo -e "${YELLOW}⚠ No shared dotfiles folder found, skipping dotfiles restore${NC}"
    fi

    if [ -f "${SCRIPT_DIR}/init.sh" ]; then
        bash "${SCRIPT_DIR}/init.sh"
    else
        echo -e "${RED}✗ init.sh not found${NC}"
        return 1
    fi

    if [ "$(uname -s)" = "Darwin" ] && [ -f "${SCRIPT_DIR}/setup_browsers.sh" ]; then
        bash "${SCRIPT_DIR}/setup_browsers.sh"
    fi

    echo -e "\n${GREEN}✓ Initialization from shared drive completed${NC}"
}

case "$1" in
    init)
        init_sync
        ;;
    setup)
        setup_symlinks
        ;;
    sync)
        sync_to_remote
        manage_obsidian sync 2>/dev/null || true
        manage_vscode sync 2>/dev/null || true
        ;;
    restore)
        restore_from_remote
        manage_obsidian restore 2>/dev/null || true
        manage_vscode restore 2>/dev/null || true
        ;;
    status)
        show_status
        echo ""
        manage_obsidian status 2>/dev/null || true
        echo ""
        manage_vscode status 2>/dev/null || true
        ;;
    list)
        list_dotfiles
        ;;
    config)
        show_config
        ;;
    obsidian)
        manage_obsidian "${2:-status}"
        ;;
    vscode)
        manage_vscode "${2:-status}"
        ;;
    packages)
        manage_packages "${2:-status}"
        ;;
    shared)
        manage_shared_configs "${2:-status}"
        ;;
    init-from-shared)
        init_from_shared_drive
        ;;
    *)
        echo -e "${RED}✗ Unknown command: $1${NC}"
        show_help
        exit 1
        ;;
esac
