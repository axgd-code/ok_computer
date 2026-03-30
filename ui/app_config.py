from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class AppPaths:
    base_dir: Path
    user_app_dir: Path
    user_src_dir: Path
    env_local_home: Path
    env_local_repo: Path
    env_local: Path
    env_example: Path
    packages_conf: Path
    system_settings_conf: Path


UI_DIR = Path(__file__).resolve().parent
DEFAULT_USER_APP_DIRNAME = '.ok_computer'
DEFAULT_SHARED_DIRNAME = 'ok_computer_shared'
CRON_UPDATE_TAG = '# OKC_AUTO_UPDATE'
APP_DISPLAY_NAME = 'OK Computer'
WEBVIEW_BASE_WIDTH = 800
WEBVIEW_EXTRA_WIDTH = 150
WEBVIEW_WINDOW_WIDTH = WEBVIEW_BASE_WIDTH + WEBVIEW_EXTRA_WIDTH
WEBVIEW_WINDOW_HEIGHT = 600

LEGACY_HIDDEN_ENV_KEYS = {
    'AUTO_EXPORT_DIR',
    'AUTO_EXPORT_ENABLED',
    'AUTO_EXPORT_FILE_PREFIX',
    'AUTO_EXPORT_INTERVAL_MINUTES',
    'AUTO_EXPORT_PATH',
    'AUTO_UPDATE_INTERVAL_MINUTES',
    'SYNC_TYPE',
    'WIFI_KDBX_DRY_RUN',
}

AUTOMATION_STATE_DEFAULTS = {
    'started': False,
    'last_update_at': None,
    'last_update_ok': None,
    'last_update_message': '',
    'last_export_at': None,
    'last_export_ok': None,
    'last_export_message': '',
    'last_export_path': '',
    'update_running': False,
    'export_running': False,
}

LOG_FILE_NAME = 'app.log'
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 3

PKG_DEBIAN_TIMEOUT_SEC = 3
PKG_ENRICH_MAX_ITEMS = 12
PKG_ENRICH_WORKERS = 8
PKG_ENRICH_COMPLETED_TIMEOUT_SEC = 20
PKG_ENRICH_RESULT_TIMEOUT_SEC = 7

FIREFOX_API_TIMEOUT_SEC = 2
FIREFOX_SEARCH_LIMIT = 10
FIREFOX_SCAN_WORKERS = 3
FIREFOX_SCAN_TIMEOUT_SEC = 5

ACTIONS_IMPORT_TIMEOUT_SEC = 120
ACTIONS_UNINSTALL_TIMEOUT_SEC = 30
ACTIONS_WIFI_EXPORT_TIMEOUT_SEC = 60
ACTIONS_PATH_PREFIX = '/opt/homebrew/bin:/usr/local/bin'

AUTOMATION_SCHEDULED_UPDATE_TIMEOUT_SEC = 900
AUTOMATION_LOOP_SLEEP_SEC = 60

ROUTE_ACTION_UPDATE_TIMEOUT_SEC = 300

ROUTE_BROWSE_TIMEOUT_SEC = 120

ROUTE_EXT_FIREFOX_PAGE_SIZE = 10
ROUTE_EXT_CHROME_METADATA_TIMEOUT_SEC = 5
ROUTE_EXT_FIREFOX_SEARCH_TIMEOUT_SEC = 5
ROUTE_EXT_CHROME_SEARCH_TIMEOUT_SEC = 6
ROUTE_EXT_CHROME_RESULTS_LIMIT = 10
ROUTE_EXT_CHROME_CHUNK_SIZE = 3000
ROUTE_EXT_INSTALL_TIMEOUT_SEC = 600

ROUTE_PKG_ICON_TIMEOUT_SEC = 1.5
ROUTE_PKG_HB_EXACT_TIMEOUT_SEC = 5
ROUTE_PKG_HB_INDEX_TIMEOUT_SEC = 10
ROUTE_PKG_HB_RESULT_LIMIT = 12
ROUTE_PKG_CHOCOLATEY_TIMEOUT_SEC = 8
ROUTE_PKG_CHOCOLATEY_RESULT_LIMIT = 10
ROUTE_PKG_APT_TIMEOUT_SEC = 6
ROUTE_PKG_APT_RESULT_LIMIT = 10
ROUTE_PKG_SEARCH_WORKERS = 4
ROUTE_PKG_SEARCH_WAIT_TIMEOUT_SEC = 10

ROUTE_SYSTEM_SETTINGS_APPLY_TIMEOUT_SEC = 240


def resolve_app_paths(base_dir=None, home=None):
    root = Path(base_dir) if base_dir is not None else Path(__file__).resolve().parents[1]
    user_home = Path(home) if home is not None else Path.home()
    cwd = Path.cwd()

    user_app_dir = user_home / DEFAULT_USER_APP_DIRNAME
    user_src_dir = user_app_dir / 'src'
    env_local_home = user_home / '.env.local'
    env_local_repo = root / '.env.local'

    explicit_env = os.environ.get('OKC_ENV_FILE', '').strip()
    env_local_explicit = Path(explicit_env).expanduser() if explicit_env else None

    env_example_candidates = [
        root / '.env.example',
        cwd / '.env.example',
    ]
    env_example = next((path for path in env_example_candidates if path.exists()), env_example_candidates[0])

    cwd_looks_like_project = (cwd / '.env.example').exists() or (cwd / 'src').exists() or (cwd / 'ui').exists()
    env_local_candidates = []
    if env_local_explicit:
        env_local_candidates.append(env_local_explicit)
    if cwd_looks_like_project:
        env_local_candidates.append(cwd / '.env.local')
    env_local_candidates.extend([
        env_local_home,
        env_local_repo,
        user_app_dir / '.env.local',
    ])
    env_local = next((path for path in env_local_candidates if path.exists()), None)
    if env_local is None:
        if cwd_looks_like_project:
            env_local = cwd / '.env.local'
        elif root.joinpath('.env.example').exists():
            env_local = env_local_repo
        else:
            env_local = env_local_home

    packages_user = user_src_dir / 'packages.conf'
    packages_conf = packages_user if packages_user.exists() else root / 'src' / 'packages.conf'

    settings_user = user_src_dir / 'system_settings.conf'
    system_settings_conf = settings_user if settings_user.exists() else root / 'src' / 'system_settings.conf'

    return AppPaths(
        base_dir=root,
        user_app_dir=user_app_dir,
        user_src_dir=user_src_dir,
        env_local_home=env_local_home,
        env_local_repo=env_local_repo,
        env_local=env_local,
        env_example=env_example,
        packages_conf=packages_conf,
        system_settings_conf=system_settings_conf,
    )


def resolve_shared_root(sync_dir):
    if not sync_dir:
        return None
    sync_path = Path(sync_dir).expanduser()
    if sync_path.name == DEFAULT_SHARED_DIRNAME:
        return sync_path
    candidate = sync_path / DEFAULT_SHARED_DIRNAME
    legacy_markers = (
        sync_path / 'dotfiles',
        sync_path / 'packages.conf',
        sync_path / 'extensions.conf',
        sync_path / 'system_settings.conf',
        sync_path / 'exports',
    )
    if any(path.exists() for path in legacy_markers):
        return sync_path
    return candidate