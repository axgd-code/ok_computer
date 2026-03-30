import os
import platform
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
import app_config as cfg


TRACKED_DOTFILES = (
    '.bashrc',
    '.zshrc',
    '.gitconfig',
    '.git-credentials',
    '.vimrc',
    '.ssh/config',
    '.ssh/authorized_keys',
    '.config/nvim',
    '.config/helix',
    '.config/starship.toml',
    '.config/alacritty',
    '.config/kitty',
)

SHARED_CONFIG_FILES = (
    'packages.conf',
    'extensions.conf',
    'system_settings.conf',
)


class ActionsService:
    def __init__(
        self,
        logger,
        base_dir_getter,
        env_local_getter,
        runtime_src_dir_fn,
        sync_env_to_repo_fn,
        find_script_fn,
        run_script_with_optional_admin_fn,
        remove_package_from_conf_fn,
        load_env_dict_fn,
    ):
        self.logger = logger
        self.base_dir_getter = base_dir_getter
        self.env_local_getter = env_local_getter
        self.runtime_src_dir_fn = runtime_src_dir_fn
        self.sync_env_to_repo_fn = sync_env_to_repo_fn
        self.find_script_fn = find_script_fn
        self.run_script_with_optional_admin_fn = run_script_with_optional_admin_fn
        self.remove_package_from_conf_fn = remove_package_from_conf_fn
        self.load_env_dict_fn = load_env_dict_fn

    def _env_map(self):
        values = {}
        for item in self.load_env_dict_fn() or []:
            key = item.get('key') if isinstance(item, dict) else None
            if key:
                values[key] = item.get('value', '')
        return values

    def _path_exists(self, path):
        path = Path(path)
        return path.exists() or path.is_symlink()

    def _home_dir(self):
        return Path.home()

    def _sync_dir(self):
        raw = self._env_map().get('SYNC_DIR', '')
        return Path(raw).expanduser() if raw else None

    def _shared_root_dir(self):
        sync_dir = self._sync_dir()
        if not sync_dir:
            return None
        return cfg.resolve_shared_root(sync_dir)

    def _dotfiles_storage_dir(self):
        shared_root = self._shared_root_dir()
        if not shared_root:
            return None
        return shared_root / 'dotfiles'

    def _tracked_home_path(self, relative_path):
        return self._home_dir() / relative_path

    def _runtime_src_dir(self):
        return Path(self.runtime_src_dir_fn())

    def _runtime_config_path(self, name):
        return self._runtime_src_dir() / name

    def _shared_config_path(self, name):
        shared_root = self._shared_root_dir()
        if not shared_root:
            return None
        return shared_root / name

    def _tracked_sync_path(self, relative_path):
        dotfiles_dir = self._dotfiles_storage_dir()
        if not dotfiles_dir:
            return None
        return dotfiles_dir / Path(relative_path).name

    def _remove_path(self, path):
        path = Path(path)
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)

    def _copy_path(self, src, dst):
        src = Path(src)
        dst = Path(dst)
        if dst.exists() or dst.is_symlink():
            self._remove_path(dst)
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=False)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    def _backup_path_for(self, path):
        base = Path(f'{path}.backup')
        if not self._path_exists(base):
            return base
        index = 1
        while True:
            candidate = Path(f'{path}.backup.{index}')
            if not self._path_exists(candidate):
                return candidate
            index += 1

    def tracked_dotfiles(self):
        return TRACKED_DOTFILES

    def tracked_shared_configs(self):
        return SHARED_CONFIG_FILES

    def _preferred_dotfiles_workflow(self):
        raw = str(self._env_map().get('DOTFILES_SYNC_MODE', 'drive')).strip().lower()
        return raw if raw in ('drive', 'zip') else 'drive'

    def get_dotfiles_status(self):
        env = self._env_map()
        sync_dir = self._sync_dir()
        shared_root = self._shared_root_dir()
        dotfiles_dir = self._dotfiles_storage_dir()
        tracked = []
        linked_count = 0
        present_count = 0
        synced_count = 0

        for relative_path in self.tracked_dotfiles():
            home_path = self._tracked_home_path(relative_path)
            sync_path = self._tracked_sync_path(relative_path)
            present = self._path_exists(home_path)
            linked = home_path.is_symlink()
            synced = bool(sync_path and self._path_exists(sync_path))
            if present:
                present_count += 1
            if linked:
                linked_count += 1
            if synced:
                synced_count += 1

            entry = {
                'path': relative_path,
                'home_path': str(home_path),
                'present': present,
                'linked': linked,
                'sync_present': synced,
                'sync_path': str(sync_path) if sync_path else '',
            }
            if linked:
                try:
                    entry['link_target'] = str(home_path.resolve())
                except Exception:
                    entry['link_target'] = ''
            tracked.append(entry)

        sync_dir_exists = bool(sync_dir and sync_dir.exists() and sync_dir.is_dir())
        dotfiles_dir_exists = bool(dotfiles_dir and dotfiles_dir.exists() and dotfiles_dir.is_dir())
        return {
            'enabled': str(env.get('ENABLE_DOTFILES_SYNC', 'false')).strip().lower() in ('1', 'true', 'yes', 'on'),
            'mode': 'manual',
            'preferred_workflow': self._preferred_dotfiles_workflow(),
            'available_workflows': ['drive', 'zip'],
            'automatic': False,
            'requires_cron': False,
            'zip_export_supported': True,
            'zip_import_supported': True,
            'sync_dir': str(sync_dir) if sync_dir else '',
            'shared_root_dir': str(shared_root) if shared_root else '',
            'sync_dir_configured': bool(sync_dir),
            'sync_dir_exists': sync_dir_exists,
            'shared_root_exists': bool(shared_root and shared_root.exists() and shared_root.is_dir()),
            'dotfiles_dir': str(dotfiles_dir) if dotfiles_dir else '',
            'dotfiles_dir_exists': dotfiles_dir_exists,
            'tracked_count': len(tracked),
            'present_count': present_count,
            'linked_count': linked_count,
            'synced_count': synced_count,
            'tracked': tracked,
        }

    def get_shared_config_status(self):
        sync_dir = self._sync_dir()
        shared_root = self._shared_root_dir()
        runtime_src = self._runtime_src_dir()
        tracked = []
        local_count = 0
        shared_count = 0

        for name in self.tracked_shared_configs():
            local_path = self._runtime_config_path(name)
            shared_path = self._shared_config_path(name)
            local_present = self._path_exists(local_path)
            shared_present = bool(shared_path and self._path_exists(shared_path))
            if local_present:
                local_count += 1
            if shared_present:
                shared_count += 1
            tracked.append({
                'name': name,
                'local_path': str(local_path),
                'local_present': local_present,
                'shared_path': str(shared_path) if shared_path else '',
                'shared_present': shared_present,
            })

        return {
            'sync_dir': str(sync_dir) if sync_dir else '',
            'shared_root_dir': str(shared_root) if shared_root else '',
            'runtime_src_dir': str(runtime_src),
            'sync_dir_configured': bool(sync_dir),
            'sync_dir_exists': bool(sync_dir and sync_dir.exists() and sync_dir.is_dir()),
            'shared_root_exists': bool(shared_root and shared_root.exists() and shared_root.is_dir()),
            'tracked_count': len(tracked),
            'local_count': local_count,
            'shared_count': shared_count,
            'tracked': tracked,
        }

    def _require_sync_dir(self):
        sync_dir = self._sync_dir()
        shared_root = self._shared_root_dir()
        if not sync_dir or not shared_root:
            raise ValueError('SYNC_DIR is not configured in .env.local')
        if not sync_dir.exists() or not sync_dir.is_dir():
            raise ValueError(f'SYNC_DIR does not exist: {sync_dir}')
        return shared_root

    def _sync_shared_configs(self):
        shared_root = self._require_sync_dir()
        shared_root.mkdir(parents=True, exist_ok=True)
        synced = []
        skipped = []
        for name in self.tracked_shared_configs():
            source_path = self._runtime_config_path(name)
            if not self._path_exists(source_path):
                skipped.append(name)
                continue
            target_path = self._shared_config_path(name)
            self._copy_path(source_path, target_path)
            synced.append(name)
        return {
            'status': 'ok',
            'action': 'sync',
            'message': f'Synchronized {len(synced)} shared configuration files',
            'synced': synced,
            'skipped': skipped,
            'count': len(synced),
            'shared_root_dir': str(shared_root),
        }

    def _restore_shared_configs(self):
        self._require_sync_dir()
        runtime_src = self._runtime_src_dir()
        runtime_src.mkdir(parents=True, exist_ok=True)
        restored = []
        skipped = []
        for name in self.tracked_shared_configs():
            source_path = self._shared_config_path(name)
            if not source_path or not self._path_exists(source_path):
                skipped.append(name)
                continue
            target_path = self._runtime_config_path(name)
            self._copy_path(source_path, target_path)
            restored.append(name)
        return {
            'status': 'ok',
            'action': 'restore',
            'message': f'Restored {len(restored)} shared configuration files locally',
            'restored': restored,
            'skipped': skipped,
            'count': len(restored),
            'runtime_src_dir': str(runtime_src),
        }

    def run_shared_config_action(self, action):
        normalized = (action or '').strip().lower()
        if normalized == 'sync':
            return self._sync_shared_configs(), 200
        if normalized == 'restore':
            return self._restore_shared_configs(), 200
        return {'error': f'Unsupported shared config action: {action}'}, 400

    def _run_dotfiles_init(self):
        self._require_sync_dir()
        dotfiles_dir = self._dotfiles_storage_dir()
        dotfiles_dir.mkdir(parents=True, exist_ok=True)
        copied = []
        for relative_path in self.tracked_dotfiles():
            home_path = self._tracked_home_path(relative_path)
            if not self._path_exists(home_path):
                continue
            sync_path = self._tracked_sync_path(relative_path)
            self._copy_path(home_path, sync_path)
            copied.append(relative_path)
        return {
            'status': 'ok',
            'action': 'init',
            'message': f'Dotfiles initialized to {dotfiles_dir}',
            'copied': copied,
            'count': len(copied),
        }

    def _run_dotfiles_setup(self):
        self._require_sync_dir()
        dotfiles_dir = self._dotfiles_storage_dir()
        if not dotfiles_dir.exists() or not dotfiles_dir.is_dir():
            raise ValueError(f'Dotfiles folder does not exist: {dotfiles_dir}')
        linked = []
        skipped = []
        for relative_path in self.tracked_dotfiles():
            sync_path = self._tracked_sync_path(relative_path)
            if not self._path_exists(sync_path):
                skipped.append(relative_path)
                continue
            home_path = self._tracked_home_path(relative_path)
            home_path.parent.mkdir(parents=True, exist_ok=True)
            if self._path_exists(home_path) and not home_path.is_symlink():
                backup_path = self._backup_path_for(home_path)
                shutil.move(str(home_path), str(backup_path))
            if not home_path.is_symlink():
                home_path.symlink_to(sync_path)
            linked.append(relative_path)
        return {
            'status': 'ok',
            'action': 'setup',
            'message': f'Setup complete with {len(linked)} symlinks created or refreshed',
            'linked': linked,
            'skipped': skipped,
            'count': len(linked),
        }

    def _run_dotfiles_sync(self):
        self._require_sync_dir()
        dotfiles_dir = self._dotfiles_storage_dir()
        dotfiles_dir.mkdir(parents=True, exist_ok=True)
        copied = []
        skipped = []
        for relative_path in self.tracked_dotfiles():
            home_path = self._tracked_home_path(relative_path)
            if not self._path_exists(home_path):
                skipped.append(relative_path)
                continue
            if home_path.is_symlink():
                skipped.append(relative_path)
                continue
            sync_path = self._tracked_sync_path(relative_path)
            self._copy_path(home_path, sync_path)
            copied.append(relative_path)
        return {
            'status': 'ok',
            'action': 'sync',
            'message': f'Synchronized {len(copied)} dotfiles to shared storage',
            'copied': copied,
            'skipped': skipped,
            'count': len(copied),
        }

    def _run_dotfiles_restore(self):
        self._require_sync_dir()
        dotfiles_dir = self._dotfiles_storage_dir()
        if not dotfiles_dir.exists() or not dotfiles_dir.is_dir():
            raise ValueError(f'Dotfiles folder does not exist: {dotfiles_dir}')
        restored = []
        skipped = []
        for relative_path in self.tracked_dotfiles():
            sync_path = self._tracked_sync_path(relative_path)
            if not self._path_exists(sync_path):
                skipped.append(relative_path)
                continue
            home_path = self._tracked_home_path(relative_path)
            home_path.parent.mkdir(parents=True, exist_ok=True)
            if home_path.is_symlink():
                skipped.append(relative_path)
                continue
            if self._path_exists(home_path):
                backup_path = self._backup_path_for(home_path)
                shutil.move(str(home_path), str(backup_path))
            self._copy_path(sync_path, home_path)
            restored.append(relative_path)
        return {
            'status': 'ok',
            'action': 'restore',
            'message': f'Restored {len(restored)} dotfiles from shared storage',
            'restored': restored,
            'skipped': skipped,
            'count': len(restored),
        }

    def run_dotfiles_action(self, action):
        normalized = (action or '').strip().lower()
        if normalized == 'init':
            return self._run_dotfiles_init(), 200
        if normalized == 'setup':
            return self._run_dotfiles_setup(), 200
        if normalized == 'sync':
            return self._run_dotfiles_sync(), 200
        if normalized == 'restore':
            return self._run_dotfiles_restore(), 200
        return {'error': f'Unsupported dotfiles action: {action}'}, 400

    def _restore_dotfiles_from_shared_storage(self):
        dotfiles_dir = self._dotfiles_storage_dir()
        if not dotfiles_dir or not dotfiles_dir.exists() or not dotfiles_dir.is_dir():
            return []
        result = self._run_dotfiles_restore()
        return result.get('restored', [])

    def _run_init_installers(self):
        init_script, _ = self.find_script_fn('init.sh')
        if not init_script:
            raise RuntimeError('init.sh not found')
        init_result = self.run_script_with_optional_admin_fn(init_script, require_admin=True)

        ext_script, _ = self.find_script_fn('setup_browsers.sh')
        sysname = platform.system().lower()
        if ext_script and 'darwin' in sysname:
            ext_result = self.run_script_with_optional_admin_fn(ext_script, require_admin=True)
        else:
            ext_result = {
                'code': 0,
                'stdout': 'Browser extension setup skipped on this OS',
                'stderr': '',
            }
        return init_result, ext_result

    def dotfiles_export_entries(self):
        entries = []
        for relative_path in self.tracked_dotfiles():
            home_path = self._tracked_home_path(relative_path)
            if not self._path_exists(home_path):
                continue
            if home_path.is_dir():
                for child in home_path.rglob('*'):
                    if child.is_dir():
                        continue
                    arcname = str(Path('dotfiles') / relative_path / child.relative_to(home_path))
                    entries.append((child, arcname))
            else:
                arcname = str(Path('dotfiles') / relative_path)
                entries.append((home_path, arcname))
        return entries

    def restore_dotfiles_from_zip(self, extracted_root):
        extracted_root = Path(extracted_root)
        restored = []
        zip_root = extracted_root / 'dotfiles'
        if not zip_root.exists() or not zip_root.is_dir():
            return restored
        for relative_path in self.tracked_dotfiles():
            preferred_src = zip_root / relative_path
            fallback_src = zip_root / Path(relative_path).name
            src = preferred_src if self._path_exists(preferred_src) else fallback_src
            if not self._path_exists(src):
                continue
            home_path = self._tracked_home_path(relative_path)
            home_path.parent.mkdir(parents=True, exist_ok=True)
            if home_path.is_symlink():
                continue
            if self._path_exists(home_path):
                backup_path = self._backup_path_for(home_path)
                shutil.move(str(home_path), str(backup_path))
            self._copy_path(src, home_path)
            restored.append(relative_path)
        return restored

    def _default_path_env(self):
        run_env = os.environ.copy()
        run_env['PATH'] = cfg.ACTIONS_PATH_PREFIX + ':' + run_env.get('PATH', '/usr/bin:/bin')
        return run_env

    def run_update_script(self, timeout=300):
        script, checked = self.find_script_fn('update.sh')
        if not script:
            return {'error': 'update script not found', 'checked': checked}
        try:
            return self.run_script_with_optional_admin_fn(script, timeout=timeout, require_admin=True)
        except subprocess.TimeoutExpired:
            return {'error': f'update.sh timed out after {timeout}s'}
        except Exception as exc:
            return {'error': str(exc)}

    def run_install_action(self, app_name):
        script, checked = self.find_script_fn('app.sh')
        if not script:
            return {'error': 'app.sh not found', 'checked': checked}, 500
        try:
            result = self.run_script_with_optional_admin_fn(script, args=['install', app_name], require_admin=True)
            return result, 200
        except Exception as exc:
            return {'error': str(exc)}, 500

    def run_import_installed_action(self):
        script_name = 'import_installed.sh'
        script, checked = self.find_script_fn(script_name)
        if not script:
            return {'error': f'{script_name} script not found', 'checked': checked}, 500

        try:
            result = self.run_script_with_optional_admin_fn(
                script,
                args=['--skip-cross-check'],
                timeout=cfg.ACTIONS_IMPORT_TIMEOUT_SEC,
                require_admin=False,
                extra_env={'PACKAGES_CONF_DIR': str(self.runtime_src_dir_fn())},
            )
            result['used'] = str(script)
            return result, 200
        except subprocess.TimeoutExpired:
            return {'error': f'import_installed.sh timed out after {cfg.ACTIONS_IMPORT_TIMEOUT_SEC}s'}, 500
        except Exception as exc:
            return {'error': str(exc)}, 500

    def _update_init_job(self, init_jobs, init_jobs_lock, job_id, progress=None, step=None, message=None, done=None, ok=None):
        with init_jobs_lock:
            state = init_jobs.get(job_id, {})
            if progress is not None:
                state['progress'] = progress
            if step is not None:
                state['step'] = step
            if message is not None:
                state['message'] = message
            if done is not None:
                state['done'] = done
            if ok is not None:
                state['ok'] = ok
            init_jobs[job_id] = state

    def run_init_from_zip_job(self, job_id, zip_path, init_jobs, init_jobs_lock):
        try:
            self._update_init_job(init_jobs, init_jobs_lock, job_id, progress=5, step='extract', message='Extracting zip...')
            work = Path(tempfile.mkdtemp(prefix='okc_init_'))
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(work)

            env_src = work / '.env.local'
            pkg_src = work / 'packages.conf'
            ext_src = work / 'extensions.conf'
            settings_src = work / 'system_settings.conf'

            self._update_init_job(init_jobs, init_jobs_lock, job_id, progress=20, step='copy', message='Copying configuration files...')
            runtime_src = self.runtime_src_dir_fn()
            runtime_src.mkdir(parents=True, exist_ok=True)
            env_local = Path(self.env_local_getter())
            env_map = self._env_map()
            shared_root = cfg.resolve_shared_root(env_map.get('SYNC_DIR', '')) if env_map.get('SYNC_DIR') else None

            def _write_conf(name, source_path):
                if not source_path.exists():
                    return
                if shared_root and shared_root.parent.exists():
                    shared_root.mkdir(parents=True, exist_ok=True)
                    target = shared_root / name
                else:
                    target = runtime_src / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(source_path.read_text())

            if env_src.exists():
                env_local.write_text(env_src.read_text())
                self.sync_env_to_repo_fn()
            _write_conf('packages.conf', pkg_src)
            _write_conf('extensions.conf', ext_src)
            _write_conf('system_settings.conf', settings_src)
            restored_dotfiles = self.restore_dotfiles_from_zip(work)

            self._update_init_job(init_jobs, init_jobs_lock, job_id, progress=45, step='install_packages', message='Installing packages from configuration...')
            init_result, ext_result = self._run_init_installers()

            shutil.rmtree(work, ignore_errors=True)
            ok = (init_result.get('code') == 0 and ext_result.get('code') == 0)
            message = 'Initialization completed.' if ok else 'Initialization finished with errors.'
            self._update_init_job(init_jobs, init_jobs_lock, job_id, progress=100, step='done', message=message, done=True, ok=ok)
            with init_jobs_lock:
                init_jobs[job_id]['logs'] = {
                    'init': {
                        'code': init_result.get('code'),
                        'stdout': init_result.get('stdout', ''),
                        'stderr': init_result.get('stderr', ''),
                        'error': init_result.get('error', ''),
                    },
                    'extensions': {
                        'code': ext_result.get('code'),
                        'stdout': ext_result.get('stdout', ''),
                        'stderr': ext_result.get('stderr', ''),
                        'error': ext_result.get('error', ''),
                    },
                    'dotfiles': {
                        'restored': restored_dotfiles,
                        'count': len(restored_dotfiles),
                    },
                }
        except Exception as exc:
            self._update_init_job(
                init_jobs,
                init_jobs_lock,
                job_id,
                progress=100,
                step='error',
                message=f'Initialization failed: {exc}',
                done=True,
                ok=False,
            )

    def run_init_from_shared_job(self, job_id, init_jobs, init_jobs_lock):
        try:
            shared_root = self._require_sync_dir()
            self._update_init_job(init_jobs, init_jobs_lock, job_id, progress=10, step='copy', message='Restoring shared configuration files...')
            restored_configs = self._restore_shared_configs()
            restored_dotfiles = []
            dotfiles_dir = self._dotfiles_storage_dir()
            if dotfiles_dir and dotfiles_dir.exists() and dotfiles_dir.is_dir():
                self._update_init_job(init_jobs, init_jobs_lock, job_id, progress=30, step='dotfiles', message='Restoring dotfiles from shared storage...')
                restored_dotfiles = self._restore_dotfiles_from_shared_storage()

            if not restored_configs.get('restored') and not restored_dotfiles:
                raise RuntimeError(f'No shared configuration found in {shared_root}')

            self._update_init_job(init_jobs, init_jobs_lock, job_id, progress=45, step='install_packages', message='Installing packages from shared configuration...')
            init_result, ext_result = self._run_init_installers()

            ok = (init_result.get('code') == 0 and ext_result.get('code') == 0)
            message = 'Initialization from shared drive completed.' if ok else 'Initialization from shared drive finished with errors.'
            self._update_init_job(init_jobs, init_jobs_lock, job_id, progress=100, step='done', message=message, done=True, ok=ok)
            with init_jobs_lock:
                init_jobs[job_id]['logs'] = {
                    'shared_configs': {
                        'restored': restored_configs.get('restored', []),
                        'skipped': restored_configs.get('skipped', []),
                        'count': restored_configs.get('count', 0),
                    },
                    'init': {
                        'code': init_result.get('code'),
                        'stdout': init_result.get('stdout', ''),
                        'stderr': init_result.get('stderr', ''),
                        'error': init_result.get('error', ''),
                    },
                    'extensions': {
                        'code': ext_result.get('code'),
                        'stdout': ext_result.get('stdout', ''),
                        'stderr': ext_result.get('stderr', ''),
                        'error': ext_result.get('error', ''),
                    },
                    'dotfiles': {
                        'restored': restored_dotfiles,
                        'count': len(restored_dotfiles),
                    },
                }
        except Exception as exc:
            self._update_init_job(
                init_jobs,
                init_jobs_lock,
                job_id,
                progress=100,
                step='error',
                message=f'Initialization failed: {exc}',
                done=True,
                ok=False,
            )

    def run_package_update(self, app_name):
        script, checked = self.find_script_fn('app.sh')
        if not script:
            return {'error': 'app.sh not found', 'checked': checked}, 500
        try:
            result = subprocess.run(
                ['bash', str(script), 'install', app_name],
                capture_output=True,
                text=True,
                env=self._default_path_env(),
            )
            return {'code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}, 200
        except Exception as exc:
            return {'error': str(exc)}, 500

    def run_package_remove(self, app_name, run_uninstall=True):
        removed = self.remove_package_from_conf_fn(app_name)
        if removed.get('error'):
            return {'error': removed['error']}, 500

        if not run_uninstall:
            return {
                'status': 'ok',
                'removed': removed.get('removed_count', 0),
                'path': removed.get('path'),
                'uninstall': 'skipped',
            }, 200

        script, checked = self.find_script_fn('app.sh')
        if not script:
            return {
                'status': 'ok',
                'removed': removed.get('removed_count', 0),
                'path': removed.get('path'),
                'warning': 'app.sh not found, skipped uninstall',
                'checked': checked,
            }, 200

        try:
            result = subprocess.run(
                ['bash', str(script), 'uninstall', app_name],
                capture_output=True,
                text=True,
                env=self._default_path_env(),
                timeout=cfg.ACTIONS_UNINSTALL_TIMEOUT_SEC,
            )
            return {
                'status': 'ok',
                'removed': removed.get('removed_count', 0),
                'path': removed.get('path'),
                'code': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
            }, 200
        except subprocess.TimeoutExpired:
            return {
                'status': 'ok',
                'removed': removed.get('removed_count', 0),
                'path': removed.get('path'),
                'warning': f'uninstall command timed out after {cfg.ACTIONS_UNINSTALL_TIMEOUT_SEC}s',
            }, 200
        except Exception as exc:
            return {
                'status': 'ok',
                'removed': removed.get('removed_count', 0),
                'path': removed.get('path'),
                'warning': f'uninstall failed: {exc}',
            }, 200

    def run_wifi_export(self, db_path, password):
        if not db_path:
            env_list = self.load_env_dict_fn()
            env_map = {item['key']: item.get('value', '') for item in env_list if isinstance(item, dict)}
            db_path = env_map.get('WIFI_KDBX_DB', '')

        if not db_path:
            return {'error': 'No DB path provided and WIFI_KDBX_DB not set'}, 400
        if not password:
            return {'error': 'Password is required'}, 400

        script = Path(self.base_dir_getter()) / 'src' / 'wifi_from_keychain.sh'
        if not script.exists():
            return {'error': 'wifi_from_keychain.sh script not found'}, 500

        run_env = self._default_path_env()
        run_env['KEEPASS_DB_PASS'] = password

        try:
            result = subprocess.run(
                ['bash', str(script), '--db', db_path],
                env=run_env,
                capture_output=True,
                text=True,
                timeout=cfg.ACTIONS_WIFI_EXPORT_TIMEOUT_SEC,
            )
            return {'stdout': result.stdout, 'stderr': result.stderr, 'code': result.returncode}, 200
        except subprocess.TimeoutExpired:
            return {'error': f'wifi-export timed out after {cfg.ACTIONS_WIFI_EXPORT_TIMEOUT_SEC}s'}, 500
        except Exception as exc:
            return {'error': str(exc)}, 500
