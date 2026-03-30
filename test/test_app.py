"""
Tests for the ok_computer Flask UI backend (ui/app.py).

Specifications tested:
  - SPEC-001: find_script() resolves scripts in dev mode and PyInstaller mode
  - SPEC-002: find_conf_file() resolves configuration files robustly
  - SPEC-003: GET /api/packages returns configured packages from packages.conf
  - SPEC-004: GET /api/env returns settings with defaults from .env.example
  - SPEC-005: GET /api/env includes example values parsed from comments
  - SPEC-006: POST /api/env creates .env.local and persists settings
  - SPEC-007: POST /api/action/update finds and runs update.sh
  - SPEC-008: POST /api/action/import-installed finds and runs import_installed.sh
  - SPEC-009: POST /api/action/install finds and runs app.sh
  - SPEC-010: GET /api/extensions resolves extensions.conf from correct path
  - SPEC-011: .env.local is auto-created from .env.example on first GET /api/env
  - SPEC-012: read_packages() correctly parses TYPE|MAC|WIN|DESC format
  - SPEC-013: load_env_dict() returns non-empty schema when .env.example exists

Run with:  pytest test/test_app.py -v
"""

import json
import os
import sys
import tempfile
import shutil
from pathlib import Path
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Bootstrap: ensure `ui/` is importable
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parents[1]
UI_DIR = ROOT_DIR / 'ui'
sys.path.insert(0, str(UI_DIR))

# Import the Flask app module (ui/app.py)
import app as okc_app  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """Flask test client."""
    okc_app.app.config['TESTING'] = True
    with okc_app.app.test_client() as c:
        yield c


@pytest.fixture
def tmp_project(tmp_path):
    """Create a minimal project structure in a temp directory.
    Returns the root path.  Monkey-patches BASE_DIR / ENV_LOCAL / etc.
    """
    src_dir = tmp_path / 'src'
    src_dir.mkdir()

    # Copy real files for testing
    real_src = ROOT_DIR / 'src'
    for name in ('packages.conf', 'packages.conf.example', 'extensions.conf',
                 'extensions.conf.example', 'update.sh', 'import_installed.sh',
                 'app.sh', 'setup_browsers.sh'):
        real_file = real_src / name
        if real_file.exists():
            shutil.copy2(str(real_file), str(src_dir / name))

    # Copy .env.example
    env_example_src = ROOT_DIR / '.env.example'
    if env_example_src.exists():
        shutil.copy2(str(env_example_src), str(tmp_path / '.env.example'))

    # Ensure .env.local does NOT exist at start
    env_local = tmp_path / '.env.local'
    if env_local.exists():
        env_local.unlink()

    logs_dir = tmp_path / 'logs'
    logs_dir.mkdir(exist_ok=True)

    # Patch module-level paths
    with mock.patch.object(okc_app, 'BASE_DIR', tmp_path), \
         mock.patch.object(okc_app, 'ENV_LOCAL', tmp_path / '.env.local'), \
         mock.patch.object(okc_app, 'ENV_LOCAL_REPO', tmp_path / '.env.local.repo'), \
         mock.patch.object(okc_app, 'ENV_EXAMPLE', tmp_path / '.env.example'), \
         mock.patch.object(okc_app, 'PACKAGES_CONF', tmp_path / 'src' / 'packages.conf'):
        yield tmp_path


# ---------------------------------------------------------------------------
# SPEC-001: find_script() resolution
# ---------------------------------------------------------------------------

class TestFindScript:
    """SPEC-001: find_script() resolves scripts in dev mode and PyInstaller mode."""

    def test_finds_script_in_dev_mode(self, tmp_project):
        """The script is found via BASE_DIR/src/."""
        script, checked = okc_app.find_script('update.sh')
        assert script is not None, f"update.sh not found. Checked: {checked}"
        assert script.exists()
        assert script.name == 'update.sh'

    def test_returns_none_for_missing_script(self, tmp_project):
        """Non-existent scripts return (None, checked_list)."""
        script, checked = okc_app.find_script('nonexistent_script.sh')
        assert script is None
        assert len(checked) > 0

    def test_finds_import_installed_script(self, tmp_project):
        """import_installed.sh is resolved."""
        script, _ = okc_app.find_script('import_installed.sh')
        assert script is not None

    def test_finds_app_sh(self, tmp_project):
        """app.sh is resolved."""
        script, _ = okc_app.find_script('app.sh')
        assert script is not None


# ---------------------------------------------------------------------------
# SPEC-002: find_conf_file() resolution
# ---------------------------------------------------------------------------

class TestFindConfFile:
    """SPEC-002: find_conf_file() resolves configuration files robustly."""

    def test_finds_packages_conf(self, tmp_project):
        path = okc_app.find_conf_file('packages.conf')
        assert path is not None
        assert path.exists()

    def test_finds_extensions_conf(self, tmp_project):
        path = okc_app.find_conf_file('extensions.conf')
        # May be None if extensions.conf was not copied; check existence
        if (tmp_project / 'src' / 'extensions.conf').exists():
            assert path is not None

    def test_returns_none_for_missing_conf(self, tmp_project):
        path = okc_app.find_conf_file('does_not_exist.conf')
        assert path is None


# ---------------------------------------------------------------------------
# SPEC-003: GET /api/packages returns configured packages
# ---------------------------------------------------------------------------

class TestApiPackages:
    """SPEC-003: Configured packages are returned from packages.conf."""

    def test_returns_packages_list(self, client, tmp_project):
        resp = client.get('/api/packages')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) > 0, "Expected at least one package from packages.conf"

    def test_package_has_required_fields(self, client, tmp_project):
        resp = client.get('/api/packages')
        data = resp.get_json()
        for pkg in data:
            assert 'type' in pkg
            assert 'mac' in pkg
            assert 'win' in pkg
            assert 'desc' in pkg

    def test_package_types_are_valid(self, client, tmp_project):
        resp = client.get('/api/packages')
        data = resp.get_json()
        valid_types = {'brew', 'cask', 'tap', 'mas'}
        for pkg in data:
            assert pkg['type'] in valid_types, f"Invalid type: {pkg['type']}"


# ---------------------------------------------------------------------------
# SPEC-012: read_packages() parsing
# ---------------------------------------------------------------------------

class TestReadPackages:
    """SPEC-012: read_packages() correctly parses TYPE|MAC|WIN|DESC format."""

    def test_parses_standard_line(self, tmp_project):
        pkgs = okc_app.read_packages()
        assert any(p['mac'] == 'git' for p in pkgs), "Expected 'git' in packages"

    def test_skips_comments_and_empty_lines(self, tmp_project):
        pkgs = okc_app.read_packages()
        for p in pkgs:
            assert not p['type'].startswith('#')

    def test_handles_missing_config_gracefully(self, tmp_project):
        # Remove packages.conf
        conf = tmp_project / 'src' / 'packages.conf'
        if conf.exists():
            conf.unlink()
        # Also remove packages.conf.example if it exists
        example = tmp_project / 'src' / 'packages.conf.example'
        if example.exists():
            example.unlink()
        pkgs = okc_app.read_packages()
        assert isinstance(pkgs, list)


# ---------------------------------------------------------------------------
# SPEC-004/005/011/013: GET /api/env (settings)
# ---------------------------------------------------------------------------

class TestApiEnvGet:
    """SPEC-004/005/011/013: Settings endpoint returns defaults from .env.example."""

    def test_returns_settings_list(self, client, tmp_project):
        resp = client.get('/api/env')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) > 0, "Expected settings from .env.example"

    def test_settings_have_keys(self, client, tmp_project):
        """SPEC-013: load_env_dict() returns non-empty schema."""
        resp = client.get('/api/env')
        data = resp.get_json()
        keys = [item['key'] for item in data]
        assert 'SYNC_DIR' in keys
        assert 'AUTO_UPDATE_HOUR' in keys
        assert 'ENABLE_DOTFILES_SYNC' in keys
        assert 'DOTFILES_SYNC_MODE' in keys

    def test_settings_have_default_values(self, client, tmp_project):
        """SPEC-004: Non-empty defaults from .env.example are preserved."""
        resp = client.get('/api/env')
        data = resp.get_json()
        env_map = {item['key']: item for item in data}
        # These have non-empty defaults in .env.example
        assert env_map['AUTO_UPDATE_HOUR']['value'] == '21'
        assert env_map['AUTO_UPDATE_MINUTE']['value'] == '0'
        assert env_map['ENABLE_DOTFILES_SYNC']['value'] == 'false'
        assert env_map['DOTFILES_SYNC_MODE']['value'] == 'drive'
        assert env_map['WIFI_KDBX_GROUP']['value'] == 'Wifi'

    def test_settings_include_examples(self, client, tmp_project):
        """SPEC-005: Example values from comments are included."""
        resp = client.get('/api/env')
        data = resp.get_json()
        env_map = {item['key']: item for item in data}
        # SYNC_DIR should have examples from commented lines
        sync = env_map.get('SYNC_DIR', {})
        examples = sync.get('examples', [])
        assert len(examples) > 0, "Expected example values for SYNC_DIR"
        assert any('OneDrive' in ex or 'Synology' in ex or 'Dropbox' in ex for ex in examples)

    def test_auto_creates_env_local(self, client, tmp_project):
        """SPEC-011: .env.local is auto-created from .env.example on first GET."""
        env_local = tmp_project / '.env.local'
        assert not env_local.exists(), "Precondition: .env.local should not exist"
        client.get('/api/env')
        assert env_local.exists(), ".env.local should have been auto-created"


# ---------------------------------------------------------------------------
# SPEC-006: POST /api/env creates/persists .env.local
# ---------------------------------------------------------------------------

class TestApiEnvPost:
    """SPEC-006: POST /api/env creates .env.local and persists settings."""

    def test_saves_settings_to_env_local(self, client, tmp_project):
        resp = client.post('/api/env',
                           data=json.dumps({'SYNC_DIR': '/test/path', 'AUTO_UPDATE_HOUR': '22'}),
                           content_type='application/json')
        assert resp.status_code == 200
        result = resp.get_json()
        assert result.get('status') == 'ok'
        assert 'path' in result

        # Verify the file was created and contains the values
        env_local = tmp_project / '.env.local'
        assert env_local.exists()


class TestAppPathResolution:
    def test_resolve_app_paths_prefers_project_env_when_running_from_project_root(self, tmp_path, monkeypatch):
        project_root = tmp_path / 'project'
        project_root.mkdir()
        (project_root / 'src').mkdir()
        (project_root / '.env.example').write_text('SYNC_DIR=""\n')
        (project_root / '.env.local').write_text('SYNC_DIR="/project-sync"\n')
        home_dir = tmp_path / 'home'
        home_dir.mkdir()
        (home_dir / '.env.local').write_text('SYNC_DIR="/home-sync"\n')

        monkeypatch.chdir(project_root)

        paths = okc_app.cfg.resolve_app_paths(base_dir=project_root, home=home_dir)

        assert paths.env_local == project_root / '.env.local'

    def test_resolve_app_paths_falls_back_to_home_env_outside_project_context(self, tmp_path, monkeypatch):
        app_root = tmp_path / 'dist' / 'ok_computer_ui'
        app_root.mkdir(parents=True)
        home_dir = tmp_path / 'home'
        home_dir.mkdir()
        (home_dir / '.env.local').write_text('SYNC_DIR="/home-sync"\n')
        outside_dir = tmp_path / 'outside'
        outside_dir.mkdir()

        monkeypatch.chdir(outside_dir)

        paths = okc_app.cfg.resolve_app_paths(base_dir=app_root, home=home_dir)

        assert paths.env_local == home_dir / '.env.local'

    def test_persisted_values_survive_reload(self, client, tmp_project):
        """After POST, a subsequent GET returns the saved values."""
        client.post('/api/env',
                     data=json.dumps({'SYNC_DIR': '/my/sync/dir'}),
                     content_type='application/json')
        resp = client.get('/api/env')
        data = resp.get_json()
        env_map = {item['key']: item for item in data}
        assert env_map['SYNC_DIR']['value'] == '/my/sync/dir'

    def test_save_completes_missing_schema_keys(self, client, tmp_project):
        """Saving settings should complete .env.local with missing keys from .env.example."""
        env_local = tmp_project / '.env.local'
        env_local.write_text('SYNC_DIR="/already/set"\n')

        resp = client.post('/api/env',
                           data=json.dumps({'SYNC_DIR': '/new/path'}),
                           content_type='application/json')
        assert resp.status_code == 200

        content = env_local.read_text()
        assert 'SYNC_DIR' in content
        assert '/new/path' in content
        # Keys from .env.example should be present even if they were missing before.
        assert 'AUTO_UPDATE_HOUR' in content
        assert 'AUTO_UPDATE_MINUTE' in content
        assert 'ENABLE_DOTFILES_SYNC' in content

    def test_save_keeps_unposted_schema_defaults(self, client, tmp_project):
        """Unposted keys keep schema defaults after save, while posted key changes are applied."""
        env_local = tmp_project / '.env.local'
        env_local.write_text('SYNC_DIR=""\n')

        client.post('/api/env',
                    data=json.dumps({'SYNC_DIR': '/filled/path'}),
                    content_type='application/json')

        resp = client.get('/api/env')
        assert resp.status_code == 200
        data = resp.get_json()
        env_map = {item['key']: item for item in data}
        assert env_map['SYNC_DIR']['value'] == '/filled/path'
        assert env_map['AUTO_UPDATE_HOUR']['value'] == '21'
        assert env_map['AUTO_UPDATE_MINUTE']['value'] == '0'


# ---------------------------------------------------------------------------
# SPEC-007: POST /api/action/update
# ---------------------------------------------------------------------------

class TestApiActionUpdate:
    """SPEC-007: POST /api/action/update finds and runs update.sh."""

    def test_finds_update_script(self, client, tmp_project):
        """The endpoint should find update.sh (not return 'script not found')."""
        # We mock subprocess.run to avoid actually running brew update
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value = mock.Mock(
                stdout='Update complete', stderr='', returncode=0)
            resp = client.post('/api/action/update')
            assert resp.status_code == 200
            data = resp.get_json()
            assert 'error' not in data, f"Unexpected error: {data.get('error')}"
            assert data.get('code') == 0

    def test_reports_error_when_script_missing(self, client, tmp_project):
        """If update.sh doesn't exist, returns a clear error with checked paths."""
        with mock.patch.object(okc_app, 'find_script', return_value=(None, ['/fake/path'])):
            resp = client.post('/api/action/update')
            data = resp.get_json()
            assert 'error' in data
            assert 'checked' in data


# ---------------------------------------------------------------------------
# SPEC-008: POST /api/action/import-installed
# ---------------------------------------------------------------------------

class TestApiActionImportInstalled:
    """SPEC-008: POST /api/action/import-installed finds and runs the import script."""

    def test_finds_import_script(self, client, tmp_project):
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value = mock.Mock(
                stdout='Done! Added 5 new packages', stderr='', returncode=0)
            resp = client.post('/api/action/import-installed')
            assert resp.status_code == 200
            data = resp.get_json()
            assert 'error' not in data, f"Unexpected error: {data.get('error')}"

    def test_passes_skip_cross_check_flag(self, client, tmp_project):
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value = mock.Mock(
                stdout='', stderr='', returncode=0)
            client.post('/api/action/import-installed')
            call_args = mock_run.call_args
            cmd = call_args[0][0] if call_args[0] else call_args[1].get('args', [])
            assert '--skip-cross-check' in cmd


# ---------------------------------------------------------------------------
# SPEC-009: POST /api/action/install
# ---------------------------------------------------------------------------

class TestApiActionInstall:
    """SPEC-009: POST /api/action/install finds and runs app.sh."""

    def test_finds_app_script(self, client, tmp_project):
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value = mock.Mock(
                stdout='Installed', stderr='', returncode=0)
            resp = client.post('/api/action/install',
                               data=json.dumps({'app': 'git'}),
                               content_type='application/json')
            assert resp.status_code == 200
            data = resp.get_json()
            assert 'error' not in data, f"Unexpected error: {data.get('error')}"

    def test_requires_app_name(self, client, tmp_project):
        resp = client.post('/api/action/install',
                           data=json.dumps({}),
                           content_type='application/json')
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# SPEC-010: GET /api/extensions resolves correct path
# ---------------------------------------------------------------------------

class TestApiExtensions:
    """SPEC-010: Extensions endpoint uses correct path (not BASE_DIR.parent)."""

    def test_returns_extensions_list(self, client, tmp_project):
        resp = client.get('/api/extensions')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_extensions_have_mode(self, client, tmp_project):
        resp = client.get('/api/extensions')
        data = resp.get_json()
        if len(data) > 0:
            for ext in data:
                assert 'mode' in ext


class TestFirefoxAddonResolution:
    """Reliability tests for Firefox GUID/slug resolution."""

    def _clear_cache(self):
        okc_app._fetch_firefox_addon_payload.cache_clear()
        okc_app._search_firefox_addons.cache_clear()

    def test_pick_search_result_prefers_exact_guid(self):
        results = [
            {'guid': 'other@x', 'slug': 'other', 'name': 'Other'},
            {'guid': 'uBlock0@raymondhill.net', 'slug': 'ublock-origin', 'name': 'uBlock Origin'},
        ]
        selected = okc_app._pick_firefox_search_result('uBlock0@raymondhill.net', 'uBlock Origin', results)
        assert selected.get('slug') == 'ublock-origin'

    def test_resolve_details_uses_direct_addon_endpoint(self):
        self._clear_cache()

        def fake_get(url, params=None, timeout=None):
            if '/api/v5/addons/addon/' in url:
                resp = mock.Mock()
                resp.status_code = 200
                resp.json.return_value = {
                    'guid': 'uBlock0@raymondhill.net',
                    'slug': 'ublock-origin',
                    'icon_url': 'https://addons.mozilla.org/user-media/addon_icons/607/607454-64.png',
                }
                return resp
            resp = mock.Mock()
            resp.status_code = 404
            resp.json.return_value = {}
            return resp

        with mock.patch.object(okc_app.requests, 'get', side_effect=fake_get):
            details = okc_app._resolve_firefox_addon_details('uBlock0@raymondhill.net', 'uBlock Origin')

        assert details['slug'] == 'ublock-origin'
        assert details['icon_url'].startswith('https://addons.mozilla.org/')
        assert details['official_url'].endswith('/ublock-origin/')

    def test_resolve_details_fallback_search_matches_guid_not_first_result(self):
        self._clear_cache()

        def fake_get(url, params=None, timeout=None):
            if '/api/v5/addons/addon/' in url:
                resp = mock.Mock()
                resp.status_code = 404
                resp.json.return_value = {}
                return resp
            if '/api/v5/addons/search/' in url:
                resp = mock.Mock()
                resp.status_code = 200
                resp.json.return_value = {
                    'results': [
                        {'guid': 'not-the-one@example.org', 'slug': 'wrong-addon', 'name': 'Wrong'},
                        {
                            'guid': 'uBlock0@raymondhill.net',
                            'slug': 'ublock-origin',
                            'name': 'uBlock Origin',
                            'icon_url': 'https://addons.mozilla.org/user-media/addon_icons/607/607454-64.png',
                        },
                    ]
                }
                return resp
            resp = mock.Mock()
            resp.status_code = 404
            resp.json.return_value = {}
            return resp

        with mock.patch.object(okc_app.requests, 'get', side_effect=fake_get):
            details = okc_app._resolve_firefox_addon_details('uBlock0@raymondhill.net', 'uBlock Origin')

        assert details['slug'] == 'ublock-origin'
        assert details['official_url'].endswith('/ublock-origin/')


# ---------------------------------------------------------------------------
# General / Integration
# ---------------------------------------------------------------------------

class TestIndexPage:
    def test_index_returns_html(self, client):
        resp = client.get('/')
        assert resp.status_code == 200

class TestApiEnvExists:
    def test_env_exists_returns_false_initially(self, client, tmp_project):
        """Before init, .env.local does not exist."""
        resp = client.get('/api/env/exists')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['exists'] is False

    def test_env_exists_returns_true_after_init(self, client, tmp_project):
        """After POST /api/env/init, .env.local exists."""
        client.post('/api/env/init')
        resp = client.get('/api/env/exists')
        data = resp.get_json()
        assert data['exists'] is True

class TestApiEnvInit:
    def test_env_init_creates_file(self, client, tmp_project):
        env_local = tmp_project / '.env.local'
        if env_local.exists():
            env_local.unlink()
        resp = client.post('/api/env/init')
        assert resp.status_code == 200
        assert env_local.exists()

    def test_env_init_copies_example_content(self, client, tmp_project):
        """The created file should contain keys from .env.example."""
        env_local = tmp_project / '.env.local'
        if env_local.exists():
            env_local.unlink()
        client.post('/api/env/init')
        content = env_local.read_text()
        assert 'SYNC_DIR' in content
        assert 'AUTO_UPDATE_HOUR' in content

    def test_env_init_reset_overwrites(self, client, tmp_project):
        """Calling init again resets to defaults (reset flow)."""
        env_local = tmp_project / '.env.local'
        # First init
        client.post('/api/env/init')
        # Save a custom value
        client.post('/api/env',
                     data=json.dumps({'SYNC_DIR': '/custom/path'}),
                     content_type='application/json')
        assert '/custom/path' in env_local.read_text() or "'/custom/path'" in env_local.read_text()
        # Reset
        client.post('/api/env/init')
        content = env_local.read_text()
        # After reset, SYNC_DIR should be back to empty default
        assert 'SYNC_DIR=""' in content


# ---------------------------------------------------------------------------
# New endpoints: export / auto-update / init from zip / package actions
# ---------------------------------------------------------------------------

class TestApiExportConfig:
    def test_export_default_path(self, client, tmp_project):
        resp = client.get('/api/export/default-path')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'default_path' in data

    def test_export_config_creates_zip(self, client, tmp_project):
        # Ensure files exist
        client.post('/api/env/init')
        resp = client.post('/api/action/export-config',
                           data=json.dumps({}),
                           content_type='application/json')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('status') == 'ok'
        assert Path(data['path']).exists()


class TestApiAutoUpdate:
    def test_auto_update_status(self, client, tmp_project):
        resp = client.get('/api/auto-update/status')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'enabled' in data

    def test_auto_update_toggle_enable_calls_script(self, client, tmp_project):
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value = mock.Mock(stdout='ok', stderr='', returncode=0)
            resp = client.post('/api/auto-update/toggle',
                               data=json.dumps({'enabled': True}),
                               content_type='application/json')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data.get('status') == 'ok'


class TestApiInitFromZip:
    def test_requires_zip_path(self, client, tmp_project):
        resp = client.post('/api/action/init-from-zip',
                           data=json.dumps({}),
                           content_type='application/json')
        assert resp.status_code == 400


class TestApiPackageActions:
    def test_packages_update_requires_app(self, client, tmp_project):
        resp = client.post('/api/packages/update',
                           data=json.dumps({}),
                           content_type='application/json')
        assert resp.status_code == 400

    def test_packages_remove_requires_app(self, client, tmp_project):
        resp = client.post('/api/packages/remove',
                           data=json.dumps({}),
                           content_type='application/json')
        assert resp.status_code == 400

    def test_packages_update_calls_subprocess(self, client, tmp_project):
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value = mock.Mock(stdout='ok', stderr='', returncode=0)
            resp = client.post('/api/packages/update',
                               data=json.dumps({'app': 'git'}),
                               content_type='application/json')
            assert resp.status_code == 200
            assert resp.get_json().get('code') == 0

    def test_packages_remove_deletes_conf_entry(self, client, tmp_project):
        """Removing a package deletes matching entry from packages.conf."""
        conf = tmp_project / 'src' / 'packages.conf'
        original = conf.read_text()
        assert 'git' in original

        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value = mock.Mock(stdout='ok', stderr='', returncode=0)
            resp = client.post('/api/packages/remove',
                               data=json.dumps({'app': 'git'}),
                               content_type='application/json')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('status') == 'ok'
        assert data.get('removed', 0) >= 1

        content = conf.read_text()
        assert 'brew|git|git|Git version control' not in content

    def test_packages_remove_returns_zero_when_not_found(self, client, tmp_project):
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value = mock.Mock(stdout='ok', stderr='', returncode=0)
            resp = client.post('/api/packages/remove',
                               data=json.dumps({'app': 'definitely-not-in-conf'}),
                               content_type='application/json')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('status') == 'ok'
        assert data.get('removed') == 0

    def test_packages_remove_runs_uninstall_by_default(self, client, tmp_project):
        """Default remove should perform both actions: uninstall and config update."""
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value = mock.Mock(stdout='ok', stderr='', returncode=0)
            resp = client.post('/api/packages/remove',
                               data=json.dumps({'app': 'git'}),
                               content_type='application/json')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('status') == 'ok'
        assert 'code' in data
        assert mock_run.called

    def test_packages_remove_with_uninstall_calls_subprocess(self, client, tmp_project):
        with mock.patch('subprocess.run') as mock_run:
            mock_run.return_value = mock.Mock(stdout='ok', stderr='', returncode=0)
            resp = client.post('/api/packages/remove',
                               data=json.dumps({'app': 'git', 'runUninstall': True}),
                               content_type='application/json')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('status') == 'ok'
        assert 'code' in data
        assert mock_run.called

    def test_packages_remove_can_skip_uninstall_when_requested(self, client, tmp_project):
        with mock.patch('subprocess.run') as mock_run:
            resp = client.post('/api/packages/remove',
                               data=json.dumps({'app': 'git', 'runUninstall': False}),
                               content_type='application/json')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('status') == 'ok'
        assert data.get('uninstall') == 'skipped'
        mock_run.assert_not_called()
