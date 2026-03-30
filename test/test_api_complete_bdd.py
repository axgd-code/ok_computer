"""BDD matrix for broad API coverage using feature file scenarios."""

import importlib.util
import shutil
import zipfile
from pathlib import Path
from unittest import mock

import pytest
from pytest_bdd import given, when, then, parsers, scenarios

ROOT_DIR = Path(__file__).resolve().parents[1]
UI_DIR = ROOT_DIR / "ui"
_APP_SPEC = importlib.util.spec_from_file_location("okc_ui_app", UI_DIR / "app.py")
assert _APP_SPEC and _APP_SPEC.loader
okc_app = importlib.util.module_from_spec(_APP_SPEC)
_APP_SPEC.loader.exec_module(okc_app)

scenarios("features/api_complete_coverage.feature")


@pytest.fixture
def isolated_project(tmp_path):
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)

    for name in (
        "packages.conf",
        "extensions.conf",
        "system_settings.conf",
        "update.sh",
        "app.sh",
        "import_installed.sh",
        "setup_browsers.sh",
        "wifi_from_keychain.sh",
        "init_conf_macOs.sh",
        "init_conf_windows.sh",
        "init_conf_linux.sh",
    ):
        f = ROOT_DIR / "src" / name
        if f.exists():
            shutil.copy2(str(f), str(src / name))

    env_example = ROOT_DIR / ".env.example"
    if env_example.exists():
        shutil.copy2(str(env_example), str(tmp_path / ".env.example"))
    else:
        (tmp_path / ".env.example").write_text("SYNC_DIR=\"\"\nAUTO_UPDATE_ENABLED=false\n")

    with (
        mock.patch.object(okc_app, "BASE_DIR", tmp_path),
        mock.patch.object(okc_app, "USER_APP_DIR", tmp_path),
        mock.patch.object(okc_app, "USER_SRC_DIR", src),
        mock.patch.object(okc_app, "ENV_LOCAL", tmp_path / ".env.local"),
        mock.patch.object(okc_app, "ENV_LOCAL_REPO", tmp_path / ".env.local.repo"),
        mock.patch.object(okc_app, "ENV_EXAMPLE", tmp_path / ".env.example"),
        mock.patch.object(okc_app, "PACKAGES_CONF", src / "packages.conf"),
        mock.patch.object(okc_app, "SYSTEM_SETTINGS_CONF", src / "system_settings.conf"),
        mock.patch.object(okc_app, "_run_script_with_optional_admin", return_value={"code": 0, "stdout": "ok", "stderr": ""}),
        mock.patch.object(okc_app, "check_homebrew", return_value=True),
        mock.patch.object(okc_app, "check_chocolatey", return_value=False),
        mock.patch.object(okc_app, "check_debian", return_value=True),
        mock.patch.object(okc_app, "_sync_update_cron_from_env", return_value={"applied": True}),
        mock.patch.object(okc_app, "_apply_update_cron_job", return_value=None),
        mock.patch.object(okc_app, "_remove_update_cron_job", return_value=None),
        mock.patch.object(okc_app, "_auto_update_status_for_os", return_value={"enabled": False, "mode": "cron"}),
    ):
        yield tmp_path


@pytest.fixture
def client(isolated_project):
    okc_app.app.config["TESTING"] = True
    with okc_app.app.test_client() as c:
        yield c


@pytest.fixture
def ctx(client, isolated_project):
    export_zip = isolated_project / "bdd_export.zip"
    seed_zip = isolated_project / "seed.zip"
    with zipfile.ZipFile(seed_zip, "w") as zf:
        zf.writestr(".env.local", "SYNC_DIR=\"\"\n")
        zf.writestr("packages.conf", "brew|git|git|Git\n")
        zf.writestr("extensions.conf", "chrome|abc|ext\n")
        zf.writestr("system_settings.conf", "dock_autohide|true|true|true|Dock\n")
    return {
        "client": client,
        "last_response": None,
        "export_zip": export_zip,
        "seed_zip": seed_zip,
    }


@given("an isolated API test client")
def given_client_ready(ctx):
    assert ctx["client"] is not None


@when(parsers.parse('I call GET "{path}"'))
def when_call_get(ctx, path):
    ctx["last_response"] = ctx["client"].get(path)


@when(parsers.parse('I call POST "{path}"'))
def when_call_post(ctx, path):
    ctx["last_response"] = ctx["client"].post(path)


@when(parsers.parse('I call POST "{path}" with json payload'))
def when_call_post_json(ctx, path):
    ctx["last_response"] = ctx["client"].post(path, json={"level": "INFO", "message": "bdd"})


@when(parsers.parse('I call POST "{path}" with lines payload'))
def when_call_post_lines(ctx, path):
    payload = {"lines": ["sample|a|b|c|desc"]}
    ctx["last_response"] = ctx["client"].post(path, json=payload)


@when(parsers.parse('I call POST "{path}" with install payload'))
def when_call_post_install(ctx, path):
    ctx["last_response"] = ctx["client"].post(path, json={"app": "git"})


@when(parsers.parse('I call POST "{path}" with export payload'))
def when_call_post_export(ctx, path):
    ctx["client"].post("/api/env/init")
    ctx["last_response"] = ctx["client"].post(path, json={"outputPath": str(ctx["export_zip"])})


@when(parsers.parse('I call POST "{path}" with enable payload'))
def when_call_post_enable(ctx, path):
    ctx["last_response"] = ctx["client"].post(path, json={"enabled": True})


@when(parsers.parse('I call POST "{path}" with missing db payload'))
def when_call_post_missing_db(ctx, path):
    ctx["last_response"] = ctx["client"].post(path, json={"password": "secret"})


@when(parsers.parse('I call POST "{path}" with missing password payload'))
def when_call_post_missing_password(ctx, path):
    ctx["last_response"] = ctx["client"].post(path, json={"db": "/tmp/a.kdbx"})


@then(parsers.parse('the API response status code should be {status:d}'))
def then_status_code(ctx, status):
    assert ctx["last_response"] is not None
    assert ctx["last_response"].status_code == status


@then("the API response should be json")
def then_json(ctx):
    assert ctx["last_response"].is_json


@then("configured extensions should include metadata links or icons")
def then_extensions_config_have_metadata(ctx):
    payload = ctx["last_response"].get_json()
    assert isinstance(payload, list)
    if not payload:
        return

    has_metadata = any(
        (
            (item.get("official_url") or item.get("chrome_url") or item.get("firefox_url"))
            or (item.get("icon_url") or item.get("chrome_icon_url") or item.get("firefox_icon_url"))
        )
        for item in payload
        if isinstance(item, dict)
    )
    assert has_metadata


@then("scanned extensions should include metadata links or icons")
def then_extensions_scan_have_metadata(ctx):
    payload = ctx["last_response"].get_json()
    assert isinstance(payload, list)
    if not payload:
        return

    has_metadata = any(
        (item.get("official_url") or item.get("icon_url"))
        for item in payload
        if isinstance(item, dict)
    )
    assert has_metadata
