<p align="center">
  <img src="ui/static/img/logo.svg" alt="OK Computer logo" width="160">
</p>

# OK Computer

OK Computer is an open source toolbox to bootstrap, maintain, and migrate a workstation with the same set of scripts from either the command line or a compiled desktop UI.

It is built to work across multiple operating systems with the same project model:

- macOS
- Linux
- Windows

The goal is not to provide identical low-level behavior on every OS, because package managers, browser paths, and system settings differ. The goal is to provide one consistent control plane for those OS-specific operations.

It is designed for people who want one place to manage:

- package installation and removal
- browser extensions
- dotfiles and shared-drive sync
- system settings
- Wi-Fi export to KeePassXC
- machine-to-machine migration through configuration ZIP exports

## Cross-Platform Compatibility

OK Computer is explicitly designed as a cross-platform project.

- the CLI scripts cover macOS, Linux, and Windows workflows where the underlying tools exist
- the package model supports OS-specific mappings in a single shared catalog
- the desktop UI wraps the same script and configuration model regardless of the target platform
- migration through ZIP export/import is intended to work across machines, not only inside one OS family

In practice, compatibility means:

- one shared repository and one shared configuration model
- OS-aware scripts for package installation and system configuration
- one desktop UI for users who do not want to operate directly from the shell

This is particularly useful if you maintain more than one machine or if your setup mixes macOS, Linux, and Windows.

## What You Can Do

With OK Computer, you can:

- initialize a new machine from a curated package list
- maintain a shared `packages.conf` catalog
- manage dotfiles through a synced drive or ZIP snapshots
- restore a machine from an exported configuration ZIP
- install and remove apps from the CLI
- operate the same workflows from a desktop UI that wraps the scripts

## Release Assets

Each tagged GitHub release can publish two deliverables:

1. `ok_computer-cli-<tag>.zip`
   A CLI-first archive containing the scripts, `okc`, `.env.example`, and supporting files.

2. `ok_computer-ui-<os>-<tag>.zip`
   A compiled desktop UI bundle for the target operating system. The UI talks to the same scripts and configuration model as the CLI.

This is handled by GitHub Actions in [release.yml](.github/workflows/release.yml).

## Quick Start

### CLI users

Download the latest CLI ZIP from GitHub Releases, extract it, then run:

```bash
chmod +x okc install_okc.sh
./install_okc.sh
okc init
```

If you do not want to install `okc` globally, you can run it locally:

```bash
chmod +x okc
./okc init
```

### Desktop UI users

Download the compiled UI ZIP for your OS from GitHub Releases, extract it, and launch the application.

The UI lets you:

- inspect and edit `.env.local`
- browse packages and extensions
- run update actions
- export or restore a configuration ZIP
- trigger dotfiles workflows, including `setup` for symlink-based drive sync

## Configuration

Copy `.env.example` to `.env.local` and adjust it to your environment.

Important variables include:

- `SYNC_DIR`: root of your synced drive location; OK Computer stores shared data under `ok_computer_shared/`
- `PACKAGES_CONF_DIR`: optional shared folder for `packages.conf`
- `OBSIDIAN_VAULT`: optional path to a synced Obsidian vault
- `VSCODE_CONFIG`: optional path to shared VS Code user settings
- `ENABLE_DOTFILES_SYNC`: enables the dotfiles feature in the UI
- `DOTFILES_SYNC_MODE`: preferred workflow, `drive` or `zip`
- `AUTO_UPDATE_HOUR`: automatic update hour
- `AUTO_UPDATE_MINUTE`: automatic update minute

Example:

```dotenv
SYNC_DIR="$HOME/OneDrive"
ENABLE_DOTFILES_SYNC=true
DOTFILES_SYNC_MODE="drive"
AUTO_UPDATE_HOUR=21
AUTO_UPDATE_MINUTE=0
```

With this configuration, OK Computer uses:

- local runtime: `~/.ok_computer`
- shared drive root: `$SYNC_DIR/ok_computer_shared`

## Recommended Local and Shared Layout

The current recommended and now supported model is:

- a local runtime directory under `~/.ok_computer`
- a shared drive root such as `~/OneDrive` or `~/SynologyDrive`
- a shared OK Computer directory under that drive called `ok_computer_shared`

So a typical layout looks like this:

```text
~/.ok_computer/
  src/
  .env.local

~/OneDrive/ok_computer_shared/
  packages.conf
  extensions.conf
  system_settings.conf        # optional
  dotfiles/
  exports/
```

Why this is a good model:

- it gives the application and the CLI one stable local runtime location
- it keeps shared assets grouped in one place
- it makes multi-machine migration easier
- it avoids scattering symlinks all over the home directory for non-dotfile configuration

### What should be shared through a drive

Good candidates for a shared folder are:

- `packages.conf`
- `extensions.conf`
- `system_settings.conf` when you want shared defaults
- exported ZIP snapshots
- the `dotfiles/` directory used by the dotfiles workflow
- optional shared assets such as Obsidian or VS Code user settings

### What should stay local by default

`.env.local` should usually stay local, or at least be split carefully.

Reasons:

- it may contain machine-specific paths
- it may contain values that differ across OSes
- it can contain sensitive local configuration

So the safest recommendation is:

- keep shared catalogs and dotfiles in the drive
- keep `.env.local` local
- if needed later, introduce a shared config plus local override model instead of syncing one identical `.env.local` to every machine

### Current architecture decision

The project now treats `~/.ok_computer` as the official local runtime.

That means:

- scripts and local runtime state live under `~/.ok_computer`
- `.env.local` stays local by default
- shared machine-to-machine assets live under `$SYNC_DIR/ok_computer_shared`
- dotfiles are still exposed into `$HOME` through symlinks when you run `setup`

This is more maintainable than trying to make the entire runtime directory itself a direct symlink into a drive.

### What is already implemented

Today, the project already uses this logic:

- local runtime under `~/.ok_computer`
- drive-backed shared folder under `ok_computer_shared`
- shared resolution for:
  - `packages.conf`
  - `extensions.conf`
  - `dotfiles/`
  - `exports/`
  - optionally `system_settings.conf`
- local `.env.local`

### Planned next steps

The following ideas are intentionally left for a later iteration:

- init from shared drive
- explicit sync of shared configs
- optional `env.shared` plus `env.local` layering

## CLI Usage

The `okc` wrapper dispatches to scripts under `src/`.

### Bootstrap a machine

```bash
okc init
```

### Manage packages

```bash
okc app install firefox
okc app uninstall firefox
okc app add docker
okc app remove docker
okc app list
```

### Manage dotfiles

```bash
okc dotfiles init
okc dotfiles setup
okc dotfiles sync
okc dotfiles restore
okc dotfiles status
```

How dotfiles work:

- `init` copies tracked files into `$SYNC_DIR/ok_computer_shared/dotfiles`
- `setup` creates symlinks from your home directory to that shared folder
- once symlinks are in place, your drive client handles automatic synchronization
- `sync` and `restore` remain useful when you want explicit push/pull behavior

### Manage shared package catalogs

```bash
okc packages status
okc packages sync
okc packages restore
```

### Manage optional targets

```bash
okc dotfiles obsidian status
okc dotfiles obsidian sync
okc dotfiles vscode restore
```

### Export Wi-Fi credentials to KeePassXC

```bash
okc wifi_from_kdbx --db /path/to/vault.kdbx --group "Wi-Fi"
```

Optional variables for Wi-Fi workflows:

- `WIFI_KDBX_DB`
- `WIFI_KDBX_GROUP`
- `WIFI_KDBX_KEY_FILE`
- `WIFI_KDBX_ASK_PASS`

## Desktop UI Workflow

The compiled UI is intended for users who prefer discovery and guided actions over raw shell commands.

The desktop application can:

- show the active config file and edit settings
- run package and extension workflows
- export a configuration ZIP for migration
- restore another machine from that ZIP
- manage dotfiles with either:
  - `drive` mode: shared folder plus symlink setup
  - `zip` mode: snapshot export/import

For drive-based dotfiles sync, the important point is:

- `setup` creates symlinks
- once the symlinks point into a drive-backed folder, your drive client provides the practical automatic sync
- no cron job is needed for that workflow

## Repository Layout

- `src/`: shell scripts and configuration files
- `ui/`: Flask + pywebview desktop interface
- `test/`: regression and E2E tests
- `.github/workflows/`: CI and release automation

## Local Development

Run the CLI checks:

```bash
bash test/test.sh
```

Run the Python/UI tests:

```bash
source .venv/bin/activate
pytest test/test_app.py test/test_services.py test/test_api_e2e_full.py -q
```

Run the UI in development:

```bash
source .venv/bin/activate
python ui/app.py
```

Build the desktop UI locally:

```bash
cd ui
sh build.sh
```

## GitHub Releases

To publish a release:

```bash
git tag v1.2.3
git push origin v1.2.3
```

The release workflow will:

1. create a GitHub Release
2. attach a CLI ZIP for script-only users
3. build and attach compiled UI archives for supported operating systems

## License

See [LICENSE](LICENSE).
