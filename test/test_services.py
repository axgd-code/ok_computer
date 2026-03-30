from pathlib import Path
import threading
from unittest import mock
import zipfile

import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
UI_DIR = ROOT_DIR / 'ui'
sys.path.insert(0, str(UI_DIR))

from actions_service import ActionsService
from automation_service import AutomationService


class DummyLogger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass


def test_automation_service_exports_available_configuration(tmp_path):
    env_local = tmp_path / '.env.local'
    env_local.write_text('SYNC_DIR=""\n')

    src = tmp_path / 'src'
    src.mkdir()
    packages_conf = src / 'packages.conf'
    packages_conf.write_text('brew|git|git|Git\n')
    extensions_conf = src / 'extensions.conf'
    extensions_conf.write_text('chrome|abc|Example\n')
    settings_conf = src / 'system_settings.conf'
    settings_conf.write_text('dock_autohide|true|true|true|Dock\n')
    dotfile_src = tmp_path / '.zshrc'
    dotfile_src.write_text('export TEST_DOTFILE=1\n')

    service = AutomationService(
        logger=DummyLogger(),
        load_env_dict_fn=lambda: [{'key': 'SYNC_DIR', 'value': str(tmp_path)}],
        env_local_getter=lambda: env_local,
        packages_conf_getter=lambda: packages_conf,
        find_conf_file_fn=lambda name: src / name,
        base_dir_getter=lambda: tmp_path,
        system_settings_conf_path_fn=lambda: settings_conf,
        export_dotfiles_entries_fn=lambda: [(dotfile_src, 'dotfiles/.zshrc')],
        run_update_script_fn=lambda timeout=300: {'code': 0},
        cron_available_fn=lambda: True,
        read_crontab_lines_fn=lambda: [],
        cron_update_tag='# OKC_AUTO_UPDATE',
    )

    out = tmp_path / 'export.zip'
    result = service.export_configuration(out)

    assert result['status'] == 'ok'
    assert out.exists()
    assert set(result['files']) == {'.env.local', 'packages.conf', 'extensions.conf', 'system_settings.conf', 'dotfiles/.zshrc'}
    with zipfile.ZipFile(out, 'r') as zf:
        assert 'dotfiles/.zshrc' in set(zf.namelist())


def test_actions_service_update_script_missing_returns_checked_paths():
    service = ActionsService(
        logger=DummyLogger(),
        base_dir_getter=lambda: Path('/tmp/project'),
        env_local_getter=lambda: Path('/tmp/project/.env.local'),
        runtime_src_dir_fn=lambda: Path('/tmp/project/src'),
        sync_env_to_repo_fn=lambda: None,
        find_script_fn=lambda name: (None, ['/tmp/project/src/update.sh']),
        run_script_with_optional_admin_fn=lambda *args, **kwargs: {'code': 0},
        remove_package_from_conf_fn=lambda app_name: {'removed_count': 0, 'path': '/tmp/project/src/packages.conf'},
        load_env_dict_fn=lambda: [],
    )

    result = service.run_update_script(timeout=12)

    assert result['error'] == 'update script not found'
    assert result['checked'] == ['/tmp/project/src/update.sh']


def test_actions_service_remove_package_can_skip_uninstall(tmp_path):
    conf_path = tmp_path / 'packages.conf'
    conf_path.write_text('brew|git|git|Git\n')

    def remove_package_from_conf(app_name):
        return {'removed_count': 1, 'path': str(conf_path)}

    service = ActionsService(
        logger=DummyLogger(),
        base_dir_getter=lambda: tmp_path,
        env_local_getter=lambda: tmp_path / '.env.local',
        runtime_src_dir_fn=lambda: tmp_path / 'src',
        sync_env_to_repo_fn=lambda: None,
        find_script_fn=lambda name: (tmp_path / 'src' / name, []),
        run_script_with_optional_admin_fn=lambda *args, **kwargs: {'code': 0},
        remove_package_from_conf_fn=remove_package_from_conf,
        load_env_dict_fn=lambda: [],
    )

    result, status = service.run_package_remove('git', run_uninstall=False)

    assert status == 200
    assert result['status'] == 'ok'
    assert result['removed'] == 1
    assert result['uninstall'] == 'skipped'


def test_actions_service_dotfiles_status_and_manual_flow(tmp_path):
    sync_dir = tmp_path / 'shared'
    sync_dir.mkdir()
    home_zshrc = tmp_path / '.zshrc'
    home_zshrc.write_text('export DOTFILES_TEST=1\n')

    service = ActionsService(
        logger=DummyLogger(),
        base_dir_getter=lambda: tmp_path,
        env_local_getter=lambda: tmp_path / '.env.local',
        runtime_src_dir_fn=lambda: tmp_path / 'src',
        sync_env_to_repo_fn=lambda: None,
        find_script_fn=lambda name: (tmp_path / 'src' / name, []),
        run_script_with_optional_admin_fn=lambda *args, **kwargs: {'code': 0},
        remove_package_from_conf_fn=lambda app_name: {'removed_count': 0, 'path': str(tmp_path / 'packages.conf')},
        load_env_dict_fn=lambda: [
            {'key': 'SYNC_DIR', 'value': str(sync_dir)},
            {'key': 'ENABLE_DOTFILES_SYNC', 'value': 'true'},
        ],
    )

    with mock.patch('actions_service.Path.home', return_value=tmp_path):
        status = service.get_dotfiles_status()
        assert status['automatic'] is False
        assert status['requires_cron'] is False
        assert status['sync_dir_configured'] is True
        assert status['preferred_workflow'] == 'drive'

        result, code = service.run_dotfiles_action('init')
        assert code == 200
        assert result['count'] >= 1
        assert (sync_dir / 'ok_computer_shared' / 'dotfiles' / '.zshrc').exists()

        home_zshrc.unlink()
        restored, restored_code = service.run_dotfiles_action('restore')
        assert restored_code == 200
        assert '.zshrc' in restored['restored']
        assert home_zshrc.read_text() == 'export DOTFILES_TEST=1\n'


def test_automation_service_prefers_shared_exports_dir(tmp_path):
    shared_drive = tmp_path / 'drive'
    shared_drive.mkdir()

    service = AutomationService(
        logger=DummyLogger(),
        load_env_dict_fn=lambda: [{'key': 'SYNC_DIR', 'value': str(shared_drive)}],
        env_local_getter=lambda: tmp_path / '.env.local',
        packages_conf_getter=lambda: tmp_path / 'packages.conf',
        find_conf_file_fn=lambda name: None,
        base_dir_getter=lambda: tmp_path,
        system_settings_conf_path_fn=lambda: tmp_path / 'system_settings.conf',
        export_dotfiles_entries_fn=lambda: [],
        run_update_script_fn=lambda timeout=300: {'code': 0},
        cron_available_fn=lambda: True,
        read_crontab_lines_fn=lambda: [],
        cron_update_tag='# OKC_AUTO_UPDATE',
    )

    assert service.default_export_dir() == shared_drive / 'ok_computer_shared' / 'exports'


def test_actions_service_dotfiles_status_uses_zip_workflow_when_configured(tmp_path):
    service = ActionsService(
        logger=DummyLogger(),
        base_dir_getter=lambda: tmp_path,
        env_local_getter=lambda: tmp_path / '.env.local',
        runtime_src_dir_fn=lambda: tmp_path / 'src',
        sync_env_to_repo_fn=lambda: None,
        find_script_fn=lambda name: (tmp_path / 'src' / name, []),
        run_script_with_optional_admin_fn=lambda *args, **kwargs: {'code': 0},
        remove_package_from_conf_fn=lambda app_name: {'removed_count': 0, 'path': str(tmp_path / 'packages.conf')},
        load_env_dict_fn=lambda: [
            {'key': 'DOTFILES_SYNC_MODE', 'value': 'zip'},
        ],
    )

    with mock.patch('actions_service.Path.home', return_value=tmp_path):
        status = service.get_dotfiles_status()
        assert status['preferred_workflow'] == 'zip'


def test_actions_service_shared_config_sync_restore_and_init_from_shared(tmp_path):
    sync_dir = tmp_path / 'shared-drive'
    sync_dir.mkdir()
    runtime_src = tmp_path / 'src'
    runtime_src.mkdir()
    (runtime_src / 'packages.conf').write_text('brew|git|git|Git\n')
    (runtime_src / 'extensions.conf').write_text('chrome|abc|Example\n')
    (runtime_src / 'system_settings.conf').write_text('dock_autohide|true|true|true|Dock\n')
    (tmp_path / '.zshrc').write_text('export OKC_SHARED_INIT=1\n')

    service = ActionsService(
        logger=DummyLogger(),
        base_dir_getter=lambda: tmp_path,
        env_local_getter=lambda: tmp_path / '.env.local',
        runtime_src_dir_fn=lambda: runtime_src,
        sync_env_to_repo_fn=lambda: None,
        find_script_fn=lambda name: (tmp_path / 'src' / name, []),
        run_script_with_optional_admin_fn=lambda *args, **kwargs: {'code': 0, 'stdout': 'ok', 'stderr': ''},
        remove_package_from_conf_fn=lambda app_name: {'removed_count': 0, 'path': str(runtime_src / 'packages.conf')},
        load_env_dict_fn=lambda: [
            {'key': 'SYNC_DIR', 'value': str(sync_dir)},
            {'key': 'ENABLE_DOTFILES_SYNC', 'value': 'true'},
        ],
    )

    with mock.patch('actions_service.Path.home', return_value=tmp_path):
        status = service.get_shared_config_status()
        assert status['tracked_count'] == 3
        assert status['local_count'] == 3
        assert status['shared_count'] == 0

        synced, synced_code = service.run_shared_config_action('sync')
        assert synced_code == 200
        assert synced['count'] == 3
        assert (sync_dir / 'ok_computer_shared' / 'packages.conf').exists()

        for name in ('packages.conf', 'extensions.conf', 'system_settings.conf'):
            (runtime_src / name).unlink()

        restored, restored_code = service.run_shared_config_action('restore')
        assert restored_code == 200
        assert restored['count'] == 3
        assert (runtime_src / 'extensions.conf').exists()

        jobs = {}
        jobs_lock = threading.Lock()
        service.run_dotfiles_action('init')
        (tmp_path / '.zshrc').unlink()
        service.run_init_from_shared_job('job-1', jobs, jobs_lock)

        assert jobs['job-1']['done'] is True
        assert jobs['job-1']['ok'] is True
        assert jobs['job-1']['logs']['shared_configs']['count'] == 3
        assert jobs['job-1']['logs']['dotfiles']['count'] == 1
        assert (tmp_path / '.zshrc').read_text() == 'export OKC_SHARED_INIT=1\n'
