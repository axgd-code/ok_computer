from flask import Flask, render_template, send_from_directory
from dotenv import load_dotenv
import os
import requests
from pathlib import Path
import subprocess
import threading
import shutil
import sys
import platform
from urllib.parse import quote as _urlquote
from datetime import datetime
import app_config as cfg

UI_DIR = cfg.UI_DIR
if str(UI_DIR) not in sys.path:
    sys.path.insert(0, str(UI_DIR))
import extensions_service as ext_svc
import preferences_service as pref_svc
import packages_service as pkg_svc
import automation_service as auto_svc
import actions_service as act_svc
import runtime_helpers as rt_h
import platform_helpers as pf_h
import bootstrap as boot_svc
from application.container import build_use_cases
from routes import register_blueprints

PATHS = cfg.resolve_app_paths()
BASE_DIR = PATHS.base_dir
USER_APP_DIR = PATHS.user_app_dir
USER_SRC_DIR = PATHS.user_src_dir
ENV_LOCAL_HOME = PATHS.env_local_home
ENV_LOCAL_REPO = PATHS.env_local_repo
ENV_LOCAL = PATHS.env_local
ENV_EXAMPLE = PATHS.env_example
PACKAGES_CONF = PATHS.packages_conf
SYSTEM_SETTINGS_CONF = PATHS.system_settings_conf

if ENV_LOCAL and Path(ENV_LOCAL).exists():
    load_dotenv(dotenv_path=ENV_LOCAL, override=False)

INIT_JOBS = {}
INIT_JOBS_LOCK = threading.Lock()
EXTENSIONS_INSTALL_LOCK = threading.Lock()

def create_app():
    return Flask(__name__, static_folder='static', template_folder='templates')


app = create_app()


AUTOMATION_STATE = dict(cfg.AUTOMATION_STATE_DEFAULTS)
AUTOMATION_LOCK = threading.Lock()
AUTOMATION_THREAD = None
LEGACY_HIDDEN_ENV_KEYS = set(cfg.LEGACY_HIDDEN_ENV_KEYS)

PACKAGES_SERVICE = None


def _set_exec_if_possible(path_obj):
    rt_h.set_exec_if_possible(path_obj)


def _copy_if_newer(src, dst):
    return rt_h.copy_if_newer(src, dst)


def _find_src_candidates():
    return rt_h.find_src_candidates(BASE_DIR)


def ensure_user_scripts_available():
    return rt_h.ensure_user_scripts_available(BASE_DIR, USER_APP_DIR, USER_SRC_DIR)


try:
    ensure_user_scripts_available()
except Exception:
    pass


# --- Robust script/file resolution for dev & PyInstaller modes -------------
def find_script(name):
    return rt_h.find_script(name, USER_SRC_DIR, BASE_DIR)


def find_conf_file(name):
    shared_conf = _shared_conf_path(name) if name in {'packages.conf', 'extensions.conf', 'system_settings.conf'} else None
    if shared_conf and shared_conf.exists():
        return shared_conf
    return rt_h.find_conf_file(name, USER_SRC_DIR, BASE_DIR)


def _run_script_with_optional_admin(script_path, args=None, timeout=None, require_admin=False, extra_env=None):
    return rt_h.run_script_with_optional_admin(
        script_path,
        args=args,
        timeout=timeout,
        require_admin=require_admin,
        extra_env=extra_env,
    )

# --- Logging configuration -------------------------------------------------
import logging
from logging.handlers import RotatingFileHandler

LOG_DIR = BASE_DIR / 'logs'
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass
log_file = LOG_DIR / cfg.LOG_FILE_NAME
handler = RotatingFileHandler(str(log_file), maxBytes=cfg.LOG_MAX_BYTES, backupCount=cfg.LOG_BACKUP_COUNT)
formatter = logging.Formatter('%(asctime)s %(levelname)s [%(name)s] %(message)s')
handler.setFormatter(formatter)
handler.setLevel(logging.INFO)

# Attach to Flask logger
app.logger.setLevel(logging.INFO)
if not any(isinstance(h, RotatingFileHandler) for h in app.logger.handlers):
    app.logger.addHandler(handler)

import logging as _root_logging
if not _root_logging.getLogger().handlers:
    _root_logging.basicConfig(level=_root_logging.INFO)

# Ensure root logger and werkzeug also write to the rotating file
try:
    root_logger = _root_logging.getLogger()
    root_logger.setLevel(logging.INFO)
    if not any(isinstance(h, RotatingFileHandler) for h in root_logger.handlers):
        root_logger.addHandler(handler)
    werk_logger = _root_logging.getLogger('werkzeug')
    if not any(isinstance(h, RotatingFileHandler) for h in werk_logger.handlers):
        werk_logger.addHandler(handler)
except Exception:
    pass

PACKAGES_SERVICE = pkg_svc.PackagesService(logger=app.logger)


def _preferences_service():
    return pref_svc.PreferencesService(
        env_local=ENV_LOCAL,
        env_example=ENV_EXAMPLE,
        env_local_repo=ENV_LOCAL_REPO,
        legacy_hidden_env_keys=LEGACY_HIDDEN_ENV_KEYS,
        logger=app.logger,
        sync_env_to_repo=_sync_env_to_repo_if_possible,
    )


def _automation_service():
    return auto_svc.AutomationService(
        logger=app.logger,
        load_env_dict_fn=load_env_dict,
        env_local_getter=lambda: ENV_LOCAL,
        packages_conf_getter=lambda: PACKAGES_CONF,
        find_conf_file_fn=find_conf_file,
        base_dir_getter=lambda: BASE_DIR,
        system_settings_conf_path_fn=_system_settings_conf_path,
        export_dotfiles_entries_fn=lambda: _actions_service().dotfiles_export_entries(),
        run_update_script_fn=_run_update_script,
        cron_available_fn=_cron_available,
        read_crontab_lines_fn=_read_crontab_lines,
        cron_update_tag=CRON_UPDATE_TAG,
    )


def _actions_service():
    return act_svc.ActionsService(
        logger=app.logger,
        base_dir_getter=lambda: BASE_DIR,
        env_local_getter=lambda: ENV_LOCAL,
        runtime_src_dir_fn=_runtime_src_dir,
        sync_env_to_repo_fn=_sync_env_to_repo_if_possible,
        find_script_fn=find_script,
        run_script_with_optional_admin_fn=_run_script_with_optional_admin,
        remove_package_from_conf_fn=remove_package_from_conf,
        load_env_dict_fn=load_env_dict,
    )


class AppState:
    pass


STATE = AppState()


# Load environment
def _sync_env_to_repo_if_possible():
    try:
        if ENV_LOCAL.exists():
            ENV_LOCAL_REPO.write_text(ENV_LOCAL.read_text())
    except Exception:
        pass


def _str_to_bool(raw, default=False):
    if raw is None:
        return default
    return str(raw).strip().lower() in ('1', 'true', 'yes', 'on')


def _int_from_env(raw, default_value, min_value=1, max_value=10080):
    try:
        val = int(str(raw).strip())
    except Exception:
        return default_value
    return max(min_value, min(max_value, val))


def _safe_iso_now():
    return datetime.now().isoformat(timespec='seconds')


def _runtime_src_dir():
    if USER_SRC_DIR.exists():
        return USER_SRC_DIR
    return BASE_DIR / 'src'


def _shared_root_dir():
    sync_dir = _env_map().get('SYNC_DIR', '')
    if not sync_dir:
        return None
    return cfg.resolve_shared_root(sync_dir)


def _shared_conf_path(name):
    shared_root = _shared_root_dir()
    if not shared_root:
        return None
    return shared_root / name


def _config_target_path(name):
    shared_conf = _shared_conf_path(name)
    if shared_conf and shared_conf.parent.exists():
        shared_conf.parent.mkdir(parents=True, exist_ok=True)
        return shared_conf
    runtime_src = _runtime_src_dir()
    runtime_src.mkdir(parents=True, exist_ok=True)
    return runtime_src / name


CRON_UPDATE_TAG = cfg.CRON_UPDATE_TAG


def _cron_available():
    try:
        return shutil.which('crontab') is not None
    except Exception:
        return False


def _read_crontab_lines():
    if not _cron_available():
        return []
    try:
        res = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
        if res.returncode != 0:
            return []
        return (res.stdout or '').splitlines()
    except Exception:
        return []


def _write_crontab_lines(lines):
    if not _cron_available():
        raise RuntimeError('crontab command not available')
    payload = '\n'.join([ln for ln in lines if ln is not None]).strip('\n')
    if payload:
        payload += '\n'
    res = subprocess.run(['crontab', '-'], input=payload, text=True, capture_output=True)
    if res.returncode != 0:
        raise RuntimeError((res.stderr or res.stdout or 'failed to write crontab').strip())


def _build_update_cron_line():
    runner_script, checked = find_script('cron_auto_update.sh')
    if not runner_script:
        raise RuntimeError(f'cron_auto_update.sh not found (checked={checked})')
    return f'* * * * * /bin/bash "{runner_script}" >/dev/null 2>&1 {CRON_UPDATE_TAG}'


def _remove_update_cron_job():
    current = _read_crontab_lines()
    kept = [ln for ln in current if CRON_UPDATE_TAG not in ln]
    _write_crontab_lines(kept)


def _apply_update_cron_job():
    current = _read_crontab_lines()
    kept = [ln for ln in current if CRON_UPDATE_TAG not in ln]
    kept.append(_build_update_cron_line())
    _write_crontab_lines(kept)


def _sync_update_cron_from_env():
    import platform
    sysname = platform.system().lower()
    if 'windows' in sysname or os.name == 'nt':
        return {'mode': 'task-scheduler', 'applied': False, 'reason': 'cron unavailable on windows'}
    if not _cron_available():
        return {'mode': 'cron', 'applied': False, 'reason': 'crontab command not available'}

    env = _env_map()
    enabled = _str_to_bool(env.get('AUTO_UPDATE_ENABLED', 'false'))
    if enabled:
        _apply_update_cron_job()
        return {'mode': 'cron', 'applied': True, 'enabled': True}

    _remove_update_cron_job()
    return {'mode': 'cron', 'applied': True, 'enabled': False}


def load_env_dict():
    return _preferences_service().load_env_dict()


def _parse_env_example_schema():
    return _preferences_service().parse_env_example_schema()


def _read_env_keys(path):
    return _preferences_service().read_env_keys(path)


def _ensure_env_local_complete():
    return _preferences_service().ensure_env_local_complete()

# Packages parsing
def read_packages():
    shared_conf = _shared_conf_path('packages.conf')
    packages_conf = shared_conf if shared_conf and shared_conf.exists() else PACKAGES_CONF
    return PACKAGES_SERVICE.read_packages(packages_conf, find_conf_file)


def remove_package_from_conf(app_name):
    shared_conf = _shared_conf_path('packages.conf')
    packages_conf = shared_conf if shared_conf and shared_conf.exists() else PACKAGES_CONF
    return PACKAGES_SERVICE.remove_package_from_conf(app_name, packages_conf, find_conf_file)


def _system_settings_conf_path():
    shared_conf = _shared_conf_path('system_settings.conf')
    conf = shared_conf if shared_conf and shared_conf.exists() else SYSTEM_SETTINGS_CONF if SYSTEM_SETTINGS_CONF.exists() else find_conf_file('system_settings.conf')
    if conf and Path(conf).exists():
        return Path(conf)
    fallback = BASE_DIR / 'src' / 'system_settings.conf'
    if fallback.exists():
        return fallback
    return BASE_DIR / 'src' / 'system_settings.conf.example'


def parse_system_settings_conf():
    return _preferences_service().parse_system_settings_conf(SYSTEM_SETTINGS_CONF, find_conf_file, BASE_DIR, _runtime_src_dir)

# Simple availability checks
def check_homebrew(app):
    return pf_h.check_homebrew(app)

def check_chocolatey(app):
    return pf_h.check_chocolatey(app)

def check_debian(app):
    return PACKAGES_SERVICE.check_debian(app)


def parse_extensions_conf():
    return ext_svc.parse_extensions_conf(find_conf_file, BASE_DIR)


def scan_chrome_family_extensions():
    return ext_svc.scan_chrome_family_extensions()


_normalize_text = ext_svc._normalize_text
_firefox_icon_from_payload = ext_svc._firefox_icon_from_payload
_fetch_firefox_addon_payload = ext_svc._fetch_firefox_addon_payload
_search_firefox_addons = ext_svc._search_firefox_addons
_pick_firefox_search_result = ext_svc._pick_firefox_search_result
_resolve_firefox_addon_details = ext_svc._resolve_firefox_addon_details
_resolve_firefox_addon_slug = ext_svc._resolve_firefox_addon_slug
_fetch_firefox_icon_from_mozilla = ext_svc._fetch_firefox_icon_from_mozilla


def scan_firefox_extensions():
    return ext_svc.scan_firefox_extensions()


def scan_local_extensions():
    return ext_svc.scan_local_extensions()


def uninstall_chrome_extension(ext_id):
    return pf_h.uninstall_chrome_extension(ext_id)


def uninstall_firefox_extension(addon_id):
    return pf_h.uninstall_firefox_extension(addon_id)


def uninstall_extension(browser, ext_id):
    return pf_h.uninstall_extension(browser, ext_id)

def _run_update_script(timeout=300):
    return _actions_service().run_update_script(timeout=timeout)

def _env_map():
    return _automation_service().env_map()


def _default_export_dir():
    return _automation_service().default_export_dir()


def _default_export_path():
    return _automation_service().default_export_path()


def _export_configuration(out_path):
    return _automation_service().export_configuration(out_path)


def _update_automation_state(**kwargs):
    _automation_service().update_state(AUTOMATION_STATE, AUTOMATION_LOCK, **kwargs)


def _run_scheduled_update():
    return _automation_service().run_scheduled_update(
        AUTOMATION_STATE,
        AUTOMATION_LOCK,
        timeout=cfg.AUTOMATION_SCHEDULED_UPDATE_TIMEOUT_SEC,
    )


def _run_scheduled_export(path_override=None):
    return _automation_service().run_scheduled_export(AUTOMATION_STATE, AUTOMATION_LOCK, path_override=path_override)


def _automation_loop():
    return _automation_service().automation_loop(AUTOMATION_STATE, AUTOMATION_LOCK)


def start_automation_scheduler_if_needed():
    global AUTOMATION_THREAD
    with AUTOMATION_LOCK:
        if AUTOMATION_THREAD and AUTOMATION_THREAD.is_alive():
            return False
        AUTOMATION_THREAD = threading.Thread(target=_automation_loop, daemon=True, name='okc-automation')
        AUTOMATION_THREAD.start()
        return True


def _auto_update_status_for_os():
    return _automation_service().auto_update_status_for_os()


def _run_init_from_zip_job(job_id, zip_path):
    return _actions_service().run_init_from_zip_job(job_id, zip_path, INIT_JOBS, INIT_JOBS_LOCK)


def _run_init_from_shared_job(job_id):
    return _actions_service().run_init_from_shared_job(job_id, INIT_JOBS, INIT_JOBS_LOCK)


def _populate_state():
    use_cases = build_use_cases(STATE)
    state_values = {
        '__file__': __file__,
        'app': app,
        'BASE_DIR': BASE_DIR,
        'USER_APP_DIR': USER_APP_DIR,
        'USER_SRC_DIR': USER_SRC_DIR,
        'ENV_LOCAL': ENV_LOCAL,
        'ENV_EXAMPLE': ENV_EXAMPLE,
        'ENV_LOCAL_REPO': ENV_LOCAL_REPO,
        'PACKAGES_CONF': PACKAGES_CONF,
        'SYSTEM_SETTINGS_CONF': SYSTEM_SETTINGS_CONF,
        'PACKAGES_SERVICE': PACKAGES_SERVICE,
        'AUTOMATION_STATE': AUTOMATION_STATE,
        'AUTOMATION_THREAD': AUTOMATION_THREAD,
        'EXTENSIONS_INSTALL_LOCK': EXTENSIONS_INSTALL_LOCK,
        'INIT_JOBS': INIT_JOBS,
        'INIT_JOBS_LOCK': INIT_JOBS_LOCK,
        'platform': platform,
        'render_template': render_template,
        'send_from_directory': send_from_directory,
        '_urlquote': _urlquote,
        'ensure_user_scripts_available': ensure_user_scripts_available,
        'find_script': find_script,
        'find_conf_file': find_conf_file,
        'load_env_dict': load_env_dict,
        'read_packages': read_packages,
        'parse_system_settings_conf': parse_system_settings_conf,
        'parse_extensions_conf': parse_extensions_conf,
        'scan_local_extensions': scan_local_extensions,
        'uninstall_extension': uninstall_extension,
        'check_homebrew': check_homebrew,
        'check_chocolatey': check_chocolatey,
        'check_debian': check_debian,
        '_run_script_with_optional_admin': _run_script_with_optional_admin,
        '_sync_env_to_repo_if_possible': _sync_env_to_repo_if_possible,
        '_ensure_env_local_complete': _ensure_env_local_complete,
        '_runtime_src_dir': _runtime_src_dir,
        '_actions_service': _actions_service,
        '_automation_service': _automation_service,
        '_run_update_script': _run_update_script,
        '_env_map': _env_map,
        '_shared_root_dir': _shared_root_dir,
        '_shared_conf_path': _shared_conf_path,
        '_config_target_path': _config_target_path,
        '_default_export_path': _default_export_path,
        '_export_configuration': _export_configuration,
        '_auto_update_status_for_os': _auto_update_status_for_os,
        '_sync_update_cron_from_env': _sync_update_cron_from_env,
        '_apply_update_cron_job': _apply_update_cron_job,
        '_remove_update_cron_job': _remove_update_cron_job,
        '_read_crontab_lines': _read_crontab_lines,
        '_str_to_bool': _str_to_bool,
        '_run_init_from_zip_job': _run_init_from_zip_job,
        '_run_init_from_shared_job': _run_init_from_shared_job,
        'start_automation_scheduler_if_needed': start_automation_scheduler_if_needed,
        'USE_CASES': use_cases,
    }
    for key, value in state_values.items():
        setattr(STATE, key, value)


_populate_state()
register_blueprints(app, STATE)


@app.before_request
def _refresh_state_before_request():
    _populate_state()


if __name__ == '__main__':
    boot_svc.run_main(STATE)
