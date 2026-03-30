"""Comprehensive end-to-end API tests for ui/app.py.

These tests target the Flask API surface (route-level behavior), while mocking
external/system dependencies (network, subprocess, OS dialogs) to stay reliable.
"""

import json
import importlib.util
import shutil
import sys
import zipfile
from pathlib import Path
from unittest import mock

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
UI_DIR = ROOT_DIR / "ui"

_APP_SPEC = importlib.util.spec_from_file_location("okc_ui_app", UI_DIR / "app.py")
assert _APP_SPEC and _APP_SPEC.loader
okc_app = importlib.util.module_from_spec(_APP_SPEC)
_APP_SPEC.loader.exec_module(okc_app)


class _FakeResp:
    def __init__(self, status_code=200, text="", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json_data = json_data

    def json(self):
        if self._json_data is None:
            raise ValueError("No json payload")
        return self._json_data


@pytest.fixture
def isolated_project(tmp_path):
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)

    real_src = ROOT_DIR / "src"
    to_copy = [
        "packages.conf",
        "packages.conf.example",
        "extensions.conf",
        "extensions.conf.example",
        "system_settings.conf",
        "system_settings.conf.example",
        "update.sh",
        "app.sh",
        "import_installed.sh",
        "setup_browsers.sh",
        "init_conf_macOs.sh",
        "init_conf_windows.sh",
        "init_conf_linux.sh",
        "init.sh",
        "wifi_from_keychain.sh",
        "cron_auto_update.sh",
    ]
    for name in to_copy:
        f = real_src / name
        if f.exists():
            shutil.copy2(str(f), str(src / name))

    env_example = ROOT_DIR / ".env.example"
    if env_example.exists():
        shutil.copy2(str(env_example), str(tmp_path / ".env.example"))
    else:
        (tmp_path / ".env.example").write_text("SYNC_DIR=\"\"\nAUTO_UPDATE_ENABLED=false\n")

    (tmp_path / "logs").mkdir(exist_ok=True)

    with (
        mock.patch.object(okc_app, "BASE_DIR", tmp_path),
        mock.patch.object(okc_app, "USER_APP_DIR", tmp_path),
        mock.patch.object(okc_app, "USER_SRC_DIR", src),
        mock.patch.object(okc_app, "ENV_LOCAL_HOME", tmp_path / ".env.local"),
        mock.patch.object(okc_app, "ENV_LOCAL_REPO", tmp_path / ".env.local.repo"),
        mock.patch.object(okc_app, "ENV_LOCAL", tmp_path / ".env.local"),
        mock.patch.object(okc_app, "ENV_EXAMPLE", tmp_path / ".env.example"),
        mock.patch.object(okc_app, "PACKAGES_CONF", src / "packages.conf"),
        mock.patch.object(okc_app, "SYSTEM_SETTINGS_CONF", src / "system_settings.conf"),
        mock.patch.object(okc_app.act_svc.Path, "home", return_value=tmp_path),
        mock.patch.object(okc_app.auto_svc.Path, "home", return_value=tmp_path),
    ):
        okc_app.INIT_JOBS.clear()
        yield tmp_path


@pytest.fixture
def client(isolated_project):
    okc_app.app.config["TESTING"] = True
    with okc_app.app.test_client() as c:
        yield c


def test_routes_index_and_static(client):
    with mock.patch.object(okc_app, "render_template", return_value="ok"):
        resp = client.get("/")
    assert resp.status_code == 200

    static_resp = client.get("/static/does-not-exist.js")
    assert static_resp.status_code == 404


def test_api_log(client):
    resp = client.post("/api/log", json={"level": "INFO", "message": "hello"})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_env_endpoints(client):
    exists_before = client.get("/api/env/exists").get_json()
    assert exists_before["exists"] is False

    init_resp = client.post("/api/env/init")
    assert init_resp.status_code == 200

    env_get = client.get("/api/env")
    assert env_get.status_code == 200
    data = env_get.get_json()
    assert isinstance(data, list)
    assert any(item["key"] == "SYNC_DIR" for item in data)

    env_post = client.post("/api/env", json={"SYNC_DIR": "/tmp/sync"})
    assert env_post.status_code == 200
    assert env_post.get_json()["status"] == "ok"

    location = client.get("/api/env/location").get_json()
    assert location["exists"] is True
    assert location["path"].endswith(".env.local")


def test_open_path_endpoint(client):
    missing = client.post("/api/open-path", json={})
    assert missing.status_code == 400

    with mock.patch("subprocess.Popen") as popen_mock:
        ok = client.post("/api/open-path", json={"path": "/tmp"})
        assert ok.status_code == 200
        assert ok.get_json()["status"] == "ok"
        assert popen_mock.called


def test_scripts_sync_endpoint(client):
    with mock.patch.object(okc_app, "ensure_user_scripts_available", return_value=["/tmp/a.sh"]):
        resp = client.post("/api/scripts/sync")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["copied_count"] == 1


def test_browse_endpoint(client):
    with (
        mock.patch("platform.system", return_value="Darwin"),
        mock.patch("subprocess.run", return_value=mock.Mock(returncode=0, stdout="/tmp/dir/\n", stderr="")),
    ):
        ok = client.post("/api/browse", json={"mode": "dir", "title": "Pick"})
        assert ok.status_code == 200
        assert ok.get_json()["path"] == "/tmp/dir"


def test_packages_and_availability(client):
    plain = client.get("/api/packages")
    assert plain.status_code == 200
    assert isinstance(plain.get_json(), list)

    with mock.patch.object(okc_app, "check_debian", return_value=True):
        avail = client.get("/api/packages?withAvailability=1")
    assert avail.status_code == 200
    data = avail.get_json()
    if data:
        assert "apt_available" in data[0]


def test_check_endpoint(client):
    bad = client.get("/api/check")
    assert bad.status_code == 400

    with (
        mock.patch.object(okc_app, "check_homebrew", return_value=True),
        mock.patch.object(okc_app, "check_chocolatey", return_value=False),
        mock.patch.object(okc_app, "check_debian", return_value=False),
    ):
        ok = client.get("/api/check?app=git")
    assert ok.status_code == 200
    result = ok.get_json()
    assert result["available"] is True
    assert result["sources"]["homebrew"] is True


def test_icon_endpoint(client):
    fallback = client.get("/api/icon?name=git")
    assert fallback.status_code == 200
    assert "url" in fallback.get_json()

    def fake_get(url, timeout=0, **kwargs):
        if "api/cask" in url:
            return _FakeResp(200, text='{"token":"x"}', json_data={"homepage": "https://git-scm.com"})
        return _FakeResp(404, text="")

    with mock.patch("requests.get", side_effect=fake_get):
        ok = client.get("/api/icon?name=git")
    assert ok.status_code == 200
    assert "google.com/s2/favicons" in ok.get_json()["url"]


def test_search_endpoint(client):
    missing = client.get("/api/search")
    assert missing.status_code == 400

    def fake_get(url, timeout=0, **kwargs):
        if "api/formula/git.json" in url:
            return _FakeResp(200, json_data={"name": "git", "desc": "Git VCS"})
        if "api/cask/git.json" in url:
            return _FakeResp(404, text="")
        if "community.chocolatey.org/packages" in url:
            return _FakeResp(200, text='data-package-id="git"')
        if "packages.debian.org/search" in url:
            return _FakeResp(200, text="<h3>Package git </h3>")
        if "api/formula.json" in url:
            return _FakeResp(200, json_data=[])
        if "api/cask.json" in url:
            return _FakeResp(200, json_data=[])
        return _FakeResp(404, text="")

    with mock.patch("requests.get", side_effect=fake_get):
        ok = client.get("/api/search?q=git")
    assert ok.status_code == 200
    payload = ok.get_json()
    assert payload["query"] == "git"
    assert isinstance(payload["results"], list)


def test_packages_add_update_remove(client, isolated_project):
    add_bad = client.post("/api/packages/add", json={"mac": "-", "win": "-"})
    assert add_bad.status_code == 400

    add_ok = client.post("/api/packages/add", json={"type": "brew", "mac": "foo-e2e", "win": "-", "desc": "test"})
    assert add_ok.status_code == 200
    assert add_ok.get_json()["status"] == "ok"

    add_dup = client.post("/api/packages/add", json={"type": "brew", "mac": "foo-e2e", "win": "-", "desc": "dup"})
    assert add_dup.status_code == 409

    with mock.patch("subprocess.run", return_value=mock.Mock(returncode=0, stdout="ok", stderr="")):
        upd = client.post("/api/packages/update", json={"app": "foo-e2e"})
    assert upd.status_code == 200
    assert upd.get_json()["code"] == 0

    rem_missing = client.post("/api/packages/remove", json={})
    assert rem_missing.status_code == 400

    rem_skip = client.post("/api/packages/remove", json={"app": "foo-e2e", "runUninstall": False})
    assert rem_skip.status_code == 200
    assert rem_skip.get_json()["uninstall"] == "skipped"


def test_system_settings_endpoints(client, isolated_project):
    get_resp = client.get("/api/system-settings")
    assert get_resp.status_code == 200
    payload = get_resp.get_json()
    assert isinstance(payload, list)
    assert any(item['key'] == 'dock_autohide' for item in payload)

    # Ensure parser exposes type and shared value
    item = next((i for i in payload if i['key'] == 'dock_autohide'), None)
    assert item is not None
    assert item['type'] == 'boolean'
    assert item['value'] in ('true', 'false')

    bad = client.post("/api/system-settings/update", json={"lines": "nope"})
    assert bad.status_code == 400

    lines = ["dock_autohide|true|true|true|Auto-hide dock"]
    upd = client.post("/api/system-settings/update", json={"lines": lines})
    assert upd.status_code == 200
    body = upd.get_json()
    assert body["status"] == "ok"
    assert Path(body["path"]).exists()

    with (
        mock.patch("platform.system", return_value="Darwin"),
        mock.patch.object(okc_app, "find_script", return_value=(isolated_project / "src" / "init_conf_macOs.sh", [])),
        mock.patch.object(okc_app, "_run_script_with_optional_admin", return_value={"code": 0, "stdout": "ok", "stderr": ""}),
    ):
        apply_ok = client.post("/api/system-settings/apply")
    assert apply_ok.status_code == 200
    assert apply_ok.get_json()["code"] == 0


def test_extensions_endpoints(client, isolated_project):
    get_resp = client.get("/api/extensions")
    assert get_resp.status_code == 200
    configured = get_resp.get_json()
    assert isinstance(configured, list)
    if configured:
        first = configured[0]
        assert any(k in first for k in ("official_url", "chrome_url", "firefox_url", "official_urls"))

    scan = client.get("/api/extensions/scan")
    assert scan.status_code == 200
    scanned = scan.get_json()
    assert isinstance(scanned, list)
    if scanned:
        assert "official_url" in scanned[0]
        assert "icon_url" in scanned[0]

    bad_upd = client.post("/api/extensions/update", json={"lines": "nope"})
    assert bad_upd.status_code == 400

    good_upd = client.post("/api/extensions/update", json={"lines": ["chrome|abc123|my ext"]})
    assert good_upd.status_code == 200
    assert good_upd.get_json()["status"] == "ok"

    def ext_get(url, timeout=0, **kwargs):
        if "addons.mozilla.org/api/v5/addons/search" in url:
            return _FakeResp(200, json_data={"results": [{"slug": "ublock-origin", "name": {"en-US": "uBlock"}, "authors": [{"name": "Ray"}], "url": "https://addons.mozilla.org"}]})
        if "chrome.google.com/webstore/search" in url:
            html = 'data-item-id="abcdefghijklmnopabcdefghijklmnop"'
            return _FakeResp(200, text=html)
        if "chrome.google.com/webstore/detail" in url:
            return _FakeResp(200, text="<meta property=\"og:title\" content=\"uBlock - Chrome Web Store\">")
        return _FakeResp(404, text="")

    with mock.patch("requests.get", side_effect=ext_get):
        search = client.get("/api/extensions/search?q=ublock")
    assert search.status_code == 200
    search_data = search.get_json()
    assert "chrome" in search_data and "firefox" in search_data

    with (
        mock.patch.object(okc_app, "find_script", return_value=(isolated_project / "src" / "setup_browsers.sh", [])),
        mock.patch.object(okc_app, "_run_script_with_optional_admin", return_value={"code": 0, "stdout": "ok", "stderr": ""}),
    ):
        install = client.post("/api/extensions/install")
    assert install.status_code == 200

    missing_un = client.post("/api/extensions/uninstall", json={"browser": ""})
    assert missing_un.status_code == 400

    with mock.patch.object(okc_app, "uninstall_extension", return_value={"status": "ok", "message": "done"}):
        un_ok = client.post("/api/extensions/uninstall", json={"browser": "chrome", "id": "abc"})
    assert un_ok.status_code == 200


def test_extensions_scan_contract_firefox_guid_slug_mapping(client, isolated_project):
    profile = isolated_project / "Library" / "Application Support" / "Firefox" / "Profiles" / "abcd.default"
    profile.mkdir(parents=True, exist_ok=True)
    ext_json = profile / "extensions.json"
    ext_json.write_text(json.dumps({
        "addons": [
            {
                "id": "uBlock0@raymondhill.net",
                "type": "extension",
                "defaultLocale": {"name": "uBlock Origin"},
            }
        ]
    }))

    def mozilla_get(url, params=None, timeout=0, **kwargs):
        if "/api/v5/addons/addon/uBlock0%40raymondhill.net/" in url:
            return _FakeResp(404, json_data={})
        if "/api/v5/addons/search/" in url:
            return _FakeResp(200, json_data={
                "results": [
                    {"guid": "other@addon", "slug": "other-addon", "name": {"en-US": "Other"}},
                    {
                        "guid": "uBlock0@raymondhill.net",
                        "slug": "ublock-origin",
                        "name": {"en-US": "uBlock Origin"},
                        "icon_url": "https://addons.mozilla.org/user-media/addon_icons/607/607454-64.png",
                    },
                ]
            })
        if "/api/v5/addons/addon/ublock-origin/" in url:
            return _FakeResp(404, json_data={})
        return _FakeResp(404, json_data={})

    with (
        mock.patch.object(okc_app.ext_svc.Path, "home", return_value=isolated_project),
        mock.patch.object(okc_app.ext_svc.requests, "get", side_effect=mozilla_get),
    ):
        scan = client.get("/api/extensions/scan")

    assert scan.status_code == 200
    scanned = scan.get_json()
    assert isinstance(scanned, list)
    firefox_items = [x for x in scanned if x.get("browser") == "firefox" and x.get("id") == "uBlock0@raymondhill.net"]
    assert firefox_items, "Expected firefox addon from extensions.json"
    addon = firefox_items[0]
    assert addon.get("slug") == "ublock-origin"
    assert addon.get("official_url", "").endswith("/ublock-origin/")
    assert addon.get("icon_url", "").startswith("https://addons.mozilla.org/")


def test_sudo_status_endpoint(client):
    with mock.patch("platform.system", return_value="Darwin"):
        darwin = client.get("/api/sudo/status")
    assert darwin.status_code == 200
    assert darwin.get_json()["interactivePrompt"] is True

    with (
        mock.patch("platform.system", return_value="Linux"),
        mock.patch("subprocess.run", return_value=mock.Mock(returncode=0, stdout="", stderr="")),
    ):
        linux = client.get("/api/sudo/status")
    assert linux.status_code == 200
    assert linux.get_json()["available"] is True


def test_action_update_install_import(client, isolated_project):
    with mock.patch.object(okc_app, "_run_script_with_optional_admin", return_value={"code": 0, "stdout": "ok", "stderr": ""}):
        upd = client.post("/api/action/update")
    assert upd.status_code == 200

    missing = client.post("/api/action/install", json={})
    assert missing.status_code == 400

    with (
        mock.patch.object(okc_app, "find_script", return_value=(isolated_project / "src" / "app.sh", [])),
        mock.patch.object(okc_app, "_run_script_with_optional_admin", return_value={"code": 0, "stdout": "ok", "stderr": ""}),
    ):
        ins = client.post("/api/action/install", json={"app": "git"})
    assert ins.status_code == 200

    with (
        mock.patch.object(okc_app, "find_script", return_value=(isolated_project / "src" / "import_installed.sh", [])),
        mock.patch.object(okc_app, "_run_script_with_optional_admin", return_value={"code": 0, "stdout": "ok", "stderr": ""}),
    ):
        imp = client.post("/api/action/import-installed")
    assert imp.status_code == 200
    assert imp.get_json()["code"] == 0


def test_export_and_automation_endpoints(client, isolated_project):
    client.post("/api/env/init")
    (isolated_project / '.zshrc').write_text('export ZIP_DOTFILE=1\n')

    default_path = client.get("/api/export/default-path")
    assert default_path.status_code == 200
    assert default_path.get_json()["default_path"].endswith(".zip")

    out = isolated_project / "my_export.zip"
    export = client.post("/api/action/export-config", json={"outputPath": str(out)})
    assert export.status_code == 200
    assert out.exists()

    with zipfile.ZipFile(out, "r") as zf:
        names = set(zf.namelist())
    assert ".env.local" in names
    assert "packages.conf" in names
    assert "extensions.conf" in names
    assert "system_settings.conf" in names
    assert "dotfiles/.zshrc" in names

    with mock.patch.object(okc_app, "_auto_update_status_for_os", return_value={"enabled": False, "mode": "cron"}):
        auto = client.get("/api/automation/status")
    assert auto.status_code == 200
    body = auto.get_json()
    assert "auto_update_enabled" in body
    assert "state" in body
    assert "auto_update_interval_minutes" not in body
    assert "auto_export_enabled" not in body


def test_env_endpoint_hides_legacy_settings(client):
    client.post("/api/env/init")

    response = client.get("/api/env")

    assert response.status_code == 200
    keys = {item["key"] for item in response.get_json()}
    assert "AUTO_UPDATE_INTERVAL_MINUTES" not in keys
    assert "AUTO_EXPORT_ENABLED" not in keys
    assert "AUTO_EXPORT_PATH" not in keys
    assert "AUTO_EXPORT_FILE_PREFIX" not in keys
    assert "SYNC_TYPE" not in keys
    assert "WIFI_KDBX_DRY_RUN" not in keys


def test_auto_update_endpoints(client):
    with mock.patch.object(okc_app, "_auto_update_status_for_os", return_value={"enabled": False, "mode": "cron"}):
        status = client.get("/api/auto-update/status")
    assert status.status_code == 200

    with mock.patch.object(okc_app, "_sync_update_cron_from_env", return_value={"applied": True}):
        toggle = client.post("/api/auto-update/toggle", json={"enabled": True})
    assert toggle.status_code == 200
    assert toggle.get_json()["enabled"] is True

    with mock.patch.object(okc_app, "_apply_update_cron_job", return_value=None):
        install = client.post("/api/auto-update/cron-install")
    assert install.status_code == 200

    with mock.patch.object(okc_app, "_remove_update_cron_job", return_value=None):
        remove = client.post("/api/auto-update/cron-remove")
    assert remove.status_code == 200


def test_init_from_zip_and_status(client, isolated_project):
    missing = client.post("/api/action/init-from-zip", json={})
    assert missing.status_code == 400

    not_found = client.post("/api/action/init-from-zip", json={"zipPath": str(isolated_project / "none.zip")})
    assert not_found.status_code == 404

    zip_path = isolated_project / "seed.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(".env.local", "SYNC_DIR=\"\"\n")
        zf.writestr("packages.conf", "brew|git|git|Git\n")
        zf.writestr("extensions.conf", "chrome|abc|ext\n")
        zf.writestr("system_settings.conf", "dock_autohide|true|true|true|Dock\n")

    with mock.patch("threading.Thread") as th_cls:
        th_inst = mock.Mock()
        th_cls.return_value = th_inst
        started = client.post("/api/action/init-from-zip", json={"zipPath": str(zip_path)})
    assert started.status_code == 200
    data = started.get_json()
    assert data["status"] == "started"
    assert "jobId" in data
    assert th_inst.start.called

    existing = client.get(f"/api/action/init-status/{data['jobId']}")
    assert existing.status_code == 200

    unknown = client.get("/api/action/init-status/unknown-id")
    assert unknown.status_code == 404


def test_dotfiles_endpoints_and_restore_from_zip(client, isolated_project):
    client.post('/api/env/init')
    sync_dir = isolated_project / 'shared-sync'
    sync_dir.mkdir()
    (isolated_project / '.zshrc').write_text('export LOCAL_DOTFILES=1\n')

    env_resp = client.post('/api/env', json={
        'SYNC_DIR': str(sync_dir),
        'ENABLE_DOTFILES_SYNC': 'true',
        'DOTFILES_SYNC_MODE': 'zip',
    })
    assert env_resp.status_code == 200

    status = client.get('/api/dotfiles/status')
    assert status.status_code == 200
    status_data = status.get_json()
    assert status_data['automatic'] is False
    assert status_data['requires_cron'] is False
    assert status_data['sync_dir_configured'] is True
    assert status_data['preferred_workflow'] == 'zip'
    assert status_data['shared_root_dir'].endswith('ok_computer_shared')

    init_dotfiles = client.post('/api/action/dotfiles', json={'action': 'init'})
    assert init_dotfiles.status_code == 200
    assert (sync_dir / 'ok_computer_shared' / 'dotfiles' / '.zshrc').exists()

    zip_path = isolated_project / 'dotfiles-seed.zip'
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr('.env.local', f'SYNC_DIR="{sync_dir}"\nENABLE_DOTFILES_SYNC=true\n')
        zf.writestr('packages.conf', 'brew|git|git|Git\n')
        zf.writestr('extensions.conf', 'chrome|abc|ext\n')
        zf.writestr('system_settings.conf', 'dock_autohide|true|true|true|Dock\n')
        zf.writestr('dotfiles/.zshrc', 'export RESTORED_FROM_ZIP=1\n')

    if (isolated_project / '.zshrc').exists():
        (isolated_project / '.zshrc').unlink()

    class InlineThread:
        def __init__(self, target=None, args=None, daemon=None, name=None):
            self.target = target
            self.args = args or ()

        def start(self):
            self.target(*self.args)

    with (
        mock.patch('threading.Thread', InlineThread),
        mock.patch.object(okc_app, 'find_script', side_effect=lambda name: (isolated_project / 'src' / name, [])),
        mock.patch.object(okc_app, '_run_script_with_optional_admin', return_value={'code': 0, 'stdout': 'ok', 'stderr': ''}),
        mock.patch('platform.system', return_value='Linux'),
    ):
        started = client.post('/api/action/init-from-zip', json={'zipPath': str(zip_path)})

    assert started.status_code == 200
    job_id = started.get_json()['jobId']
    job_status = client.get(f'/api/action/init-status/{job_id}')
    assert job_status.status_code == 200
    payload = job_status.get_json()
    assert payload['done'] is True
    assert payload['ok'] is True
    assert payload['logs']['dotfiles']['count'] == 1
    assert (isolated_project / '.zshrc').read_text() == 'export RESTORED_FROM_ZIP=1\n'


def test_shared_config_endpoints_and_init_from_shared(client, isolated_project):
    client.post('/api/env/init')
    sync_dir = isolated_project / 'shared-sync'
    sync_dir.mkdir()
    (isolated_project / '.zshrc').write_text('export SHARED_DRIVE_INIT=1\n')

    env_resp = client.post('/api/env', json={
        'SYNC_DIR': str(sync_dir),
        'ENABLE_DOTFILES_SYNC': 'true',
        'DOTFILES_SYNC_MODE': 'drive',
    })
    assert env_resp.status_code == 200

    status = client.get('/api/shared-config/status')
    assert status.status_code == 200
    status_data = status.get_json()
    assert status_data['tracked_count'] == 3
    assert status_data['local_count'] == 3
    assert status_data['shared_count'] == 0

    sync_resp = client.post('/api/action/shared-config', json={'action': 'sync'})
    assert sync_resp.status_code == 200
    assert (sync_dir / 'ok_computer_shared' / 'packages.conf').exists()

    dotfiles_init = client.post('/api/action/dotfiles', json={'action': 'init'})
    assert dotfiles_init.status_code == 200

    for name in ('packages.conf', 'extensions.conf', 'system_settings.conf'):
        path = isolated_project / 'src' / name
        if path.exists():
            path.unlink()
    if (isolated_project / '.zshrc').exists():
        (isolated_project / '.zshrc').unlink()

    restore_resp = client.post('/api/action/shared-config', json={'action': 'restore'})
    assert restore_resp.status_code == 200
    assert (isolated_project / 'src' / 'extensions.conf').exists()

    class InlineThread:
        def __init__(self, target=None, args=None, daemon=None, name=None):
            self.target = target
            self.args = args or ()

        def start(self):
            self.target(*self.args)

    with (
        mock.patch('threading.Thread', InlineThread),
        mock.patch.object(okc_app, 'find_script', side_effect=lambda name: (isolated_project / 'src' / name, [])),
        mock.patch.object(okc_app, '_run_script_with_optional_admin', return_value={'code': 0, 'stdout': 'ok', 'stderr': ''}),
        mock.patch('platform.system', return_value='Linux'),
    ):
        started = client.post('/api/action/init-from-shared')

    assert started.status_code == 200
    job_id = started.get_json()['jobId']
    job_status = client.get(f'/api/action/init-status/{job_id}')
    assert job_status.status_code == 200
    payload = job_status.get_json()
    assert payload['done'] is True
    assert payload['ok'] is True
    assert payload['logs']['shared_configs']['count'] == 3
    assert payload['logs']['dotfiles']['count'] == 1
    assert (isolated_project / '.zshrc').read_text() == 'export SHARED_DRIVE_INIT=1\n'


def test_wifi_export_endpoint(client, isolated_project):
    no_db = client.post("/api/action/wifi-export", json={"password": "x"})
    assert no_db.status_code == 400

    no_pass = client.post("/api/action/wifi-export", json={"db": "/tmp/a.kdbx"})
    assert no_pass.status_code == 400

    script = isolated_project / "src" / "wifi_from_keychain.sh"
    assert script.exists()

    with mock.patch("subprocess.run", return_value=mock.Mock(returncode=0, stdout="ok", stderr="")):
        ok = client.post("/api/action/wifi-export", json={"db": "/tmp/a.kdbx", "password": "secret"})
    assert ok.status_code == 200
    assert ok.get_json()["code"] == 0
