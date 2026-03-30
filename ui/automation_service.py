import os
import time
import zipfile
from datetime import datetime
from pathlib import Path
import app_config as cfg


class AutomationService:
    def __init__(
        self,
        logger,
        load_env_dict_fn,
        env_local_getter,
        packages_conf_getter,
        find_conf_file_fn,
        base_dir_getter,
        system_settings_conf_path_fn,
        export_dotfiles_entries_fn,
        run_update_script_fn,
        cron_available_fn,
        read_crontab_lines_fn,
        cron_update_tag,
    ):
        self.logger = logger
        self.load_env_dict_fn = load_env_dict_fn
        self.env_local_getter = env_local_getter
        self.packages_conf_getter = packages_conf_getter
        self.find_conf_file_fn = find_conf_file_fn
        self.base_dir_getter = base_dir_getter
        self.system_settings_conf_path_fn = system_settings_conf_path_fn
        self.export_dotfiles_entries_fn = export_dotfiles_entries_fn
        self.run_update_script_fn = run_update_script_fn
        self.cron_available_fn = cron_available_fn
        self.read_crontab_lines_fn = read_crontab_lines_fn
        self.cron_update_tag = cron_update_tag

    def _shared_root(self, env):
        sync_dir = env.get('SYNC_DIR', '')
        return cfg.resolve_shared_root(sync_dir) if sync_dir else None

    def env_map(self):
        env_items = self.load_env_dict_fn()
        values = {}
        for item in env_items:
            key = item.get('key')
            if key:
                values[key] = item.get('value', '')
        return values

    def default_export_dir(self):
        env = self.env_map()
        shared_root = self._shared_root(env)
        candidates = [
            str(shared_root / 'exports') if shared_root and shared_root.parent.exists() else '',
            env.get('PACKAGES_CONF_DIR', ''),
            str(Path.home()),
        ]
        for raw in candidates:
            if not raw:
                continue
            path = Path(raw).expanduser()
            if path.exists() and path.is_dir():
                return path
            if shared_root and path == (shared_root / 'exports') and shared_root.parent.exists():
                return path
        return Path.home()

    def default_export_path(self):
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return self.default_export_dir() / f'ok_computer_export_{stamp}.zip'

    def export_configuration(self, out_path):
        out_path = Path(out_path).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        env_local = Path(self.env_local_getter())
        env_candidates = [Path.home() / '.env.local', env_local]
        env_src = next((path for path in env_candidates if path.exists()), None)
        packages_conf = Path(self.packages_conf_getter())
        pkg_src = packages_conf if packages_conf.exists() else self.find_conf_file_fn('packages.conf')
        base_dir = Path(self.base_dir_getter())
        ext_src = self.find_conf_file_fn('extensions.conf') or (base_dir / 'src' / 'extensions.conf')
        settings_src = self.system_settings_conf_path_fn()
        dotfiles_entries = self.export_dotfiles_entries_fn() if self.export_dotfiles_entries_fn else []

        files_added = []
        with zipfile.ZipFile(out_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            if env_src and Path(env_src).exists():
                zf.write(env_src, arcname='.env.local')
                files_added.append('.env.local')
            if pkg_src and Path(pkg_src).exists():
                zf.write(Path(pkg_src), arcname='packages.conf')
                files_added.append('packages.conf')
            if ext_src and Path(ext_src).exists():
                zf.write(Path(ext_src), arcname='extensions.conf')
                files_added.append('extensions.conf')
            if settings_src and Path(settings_src).exists():
                zf.write(Path(settings_src), arcname='system_settings.conf')
                files_added.append('system_settings.conf')
            for src, arcname in dotfiles_entries:
                zf.write(Path(src), arcname=arcname)
                files_added.append(arcname)

        if not files_added:
            raise FileNotFoundError('No configuration files found to export')

        self.logger.info('Configuration exported to %s with files=%s', out_path, files_added)
        return {'status': 'ok', 'path': str(out_path), 'files': files_added}

    def update_state(self, automation_state, automation_lock, **kwargs):
        with automation_lock:
            automation_state.update(kwargs)

    def safe_iso_now(self):
        return datetime.now().isoformat(timespec='seconds')

    def run_scheduled_update(self, automation_state, automation_lock, timeout=None):
        with automation_lock:
            if automation_state.get('update_running'):
                return
            automation_state['update_running'] = True
        try:
            effective_timeout = cfg.AUTOMATION_SCHEDULED_UPDATE_TIMEOUT_SEC if timeout is None else timeout
            result = self.run_update_script_fn(timeout=effective_timeout)
            ok = ('error' not in result) and (result.get('code', 1) == 0)
            message = result.get('error') or f"code={result.get('code', 'n/a')}"
            self.update_state(
                automation_state,
                automation_lock,
                last_update_at=self.safe_iso_now(),
                last_update_ok=ok,
                last_update_message=message,
            )
        finally:
            self.update_state(automation_state, automation_lock, update_running=False)

    def run_scheduled_export(self, automation_state, automation_lock, path_override=None):
        with automation_lock:
            if automation_state.get('export_running'):
                return
            automation_state['export_running'] = True
        try:
            out_path = Path(path_override).expanduser() if path_override else self.default_export_path()
            result = self.export_configuration(out_path)
            self.update_state(
                automation_state,
                automation_lock,
                last_export_at=self.safe_iso_now(),
                last_export_ok=True,
                last_export_message='ok',
                last_export_path=result.get('path', ''),
            )
        except Exception as exc:
            self.update_state(
                automation_state,
                automation_lock,
                last_export_at=self.safe_iso_now(),
                last_export_ok=False,
                last_export_message=str(exc),
            )
        finally:
            self.update_state(automation_state, automation_lock, export_running=False)

    def automation_loop(self, automation_state, automation_lock):
        self.logger.info('Autonomous automation scheduler started')
        self.update_state(automation_state, automation_lock, started=True)
        while True:
            try:
                pass
            except Exception as exc:
                self.logger.warning('Automation scheduler loop error: %s', exc)
            time.sleep(cfg.AUTOMATION_LOOP_SLEEP_SEC)

    def str_to_bool(self, raw, default=False):
        if raw is None:
            return default
        return str(raw).strip().lower() in ('1', 'true', 'yes', 'on')

    def auto_update_status_for_os(self):
        sysname = os.name
        import platform

        platform_name = platform.system().lower()
        if 'windows' in platform_name or sysname == 'nt':
            return {'enabled': False, 'mode': 'task-scheduler', 'target': 'PackagesAutoUpdate'}

        if not self.cron_available_fn():
            return {'enabled': False, 'mode': 'cron', 'target': 'crontab', 'available': False}

        try:
            lines = self.read_crontab_lines_fn()
            enabled = any(self.cron_update_tag in (line or '') for line in lines)
            return {'enabled': enabled, 'mode': 'cron', 'target': 'crontab', 'available': True}
        except Exception as exc:
            return {'enabled': False, 'mode': 'cron', 'target': 'crontab', 'error': str(exc)}
