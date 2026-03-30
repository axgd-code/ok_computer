"""
pytest-bdd step definitions for test/features/quickactions.feature

Run with:
    pytest test/test_quickactions_bdd.py -v
or with feature output:
    pytest test/test_quickactions_bdd.py -v --gherkin-terminal-reporter
"""
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest import mock

import pytest
from pytest_bdd import given, when, then, scenarios, parsers

# ---------------------------------------------------------------------------
# Bootstrap import
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parents[1]
UI_DIR = ROOT_DIR / "ui"
sys.path.insert(0, str(UI_DIR))
import app as okc_app  # noqa: E402

# Bind all scenarios from the feature file
scenarios("features/quickactions.feature")


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    okc_app.app.config["TESTING"] = True
    with okc_app.app.test_client() as c:
        yield c


@pytest.fixture
def tmp_project(tmp_path):
    """Minimal project fixture — mirrors test_app.py tmp_project."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    real_src = ROOT_DIR / "src"
    for name in (
        "packages.conf", "packages.conf.example", "extensions.conf",
        "extensions.conf.example", "update.sh", "import_installed.sh",
        "app.sh", "setup_browsers.sh", "setup_auto_update.sh",
        "cron_auto_update.sh",
        "wifi_from_keychain.sh",
    ):
        real_file = real_src / name
        if real_file.exists():
            shutil.copy2(str(real_file), str(src_dir / name))

    env_example_src = ROOT_DIR / ".env.example"
    if env_example_src.exists():
        shutil.copy2(str(env_example_src), str(tmp_path / ".env.example"))

    env_local = tmp_path / ".env.local"
    if env_local.exists():
        env_local.unlink()

    (tmp_path / "logs").mkdir(exist_ok=True)

    with (
        mock.patch.object(okc_app, "BASE_DIR", tmp_path),
        mock.patch.object(okc_app, "USER_APP_DIR", tmp_path),
        mock.patch.object(okc_app, "USER_SRC_DIR", src_dir),
        mock.patch.object(okc_app, "ENV_LOCAL", tmp_path / ".env.local"),
        mock.patch.object(okc_app, "ENV_LOCAL_REPO", tmp_path / ".env.local.repo"),
        mock.patch.object(okc_app, "ENV_EXAMPLE", tmp_path / ".env.example"),
        mock.patch.object(okc_app, "PACKAGES_CONF", tmp_path / "src" / "packages.conf"),
        mock.patch.object(okc_app, "SYSTEM_SETTINGS_CONF", tmp_path / "src" / "system_settings.conf"),
        mock.patch.object(okc_app.Path, "home", return_value=tmp_path),
        mock.patch.object(okc_app.Path, "cwd", return_value=tmp_path),
    ):
        yield tmp_path


# ---------------------------------------------------------------------------
# State container shared between steps in one scenario
# ---------------------------------------------------------------------------

@pytest.fixture
def ctx():
    """Mutable context bag shared across steps within a scenario."""
    return {}


# ===========================================================================
# GIVEN steps
# ===========================================================================

@given("the application is running")
def app_running(client, tmp_project):
    resp = client.get("/")
    assert resp.status_code == 200


@given('a valid ".env.example" file exists')
def env_example_exists(tmp_project):
    assert (tmp_project / ".env.example").exists()


@given('a valid "packages.conf" file exists')
def packages_conf_exists(tmp_project):
    assert (tmp_project / "src" / "packages.conf").exists()


@given(parsers.parse('the script "{script_name}" does not exist'))
def script_does_not_exist(script_name, tmp_project, ctx):
    script_path = tmp_project / "src" / script_name
    if script_path.exists():
        script_path.unlink()
    ctx["missing_script"] = script_name


@given('".env.local" exists with some settings')
def env_local_with_settings(client, tmp_project):
    client.post("/api/env/init")
    assert (tmp_project / ".env.local").exists()


@given('".env.local" does not exist')
def env_local_missing(tmp_project):
    p = tmp_project / ".env.local"
    if p.exists():
        p.unlink()


@given('"packages.conf" does not exist')
def packages_conf_missing(tmp_project):
    for p in (tmp_project / "src" / "packages.conf", tmp_project / "src" / "packages.conf.example"):
        if p.exists():
            p.unlink()


@given('"extensions.conf" does not exist')
def extensions_conf_missing(tmp_project):
    p = tmp_project / "src" / "extensions.conf"
    if p.exists():
        p.unlink()


@given(parsers.parse('".env.local" has "{key}" set to "{value}"'))
def env_local_has_key(client, tmp_project, key, value):
    client.post("/api/env/init")
    client.post(
        "/api/env",
        data=json.dumps({key: value}),
        content_type="application/json",
    )


@given(parsers.parse('the script "{script_name}" is mocked to succeed'))
def script_mocked_to_succeed(script_name, ctx):
    ctx.setdefault("mocked_scripts", []).append(script_name)


@given("a valid configuration zip file exists at a temp path")
def valid_zip_at_temp_path(tmp_project, ctx):
    zip_path = tmp_project / "test_config.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        env_example = tmp_project / ".env.example"
        if env_example.exists():
            zf.write(env_example, arcname=".env.local")
        pkg = tmp_project / "src" / "packages.conf"
        if pkg.exists():
            zf.write(pkg, arcname="packages.conf")
    ctx["zip_path"] = str(zip_path)


@given("a background init job has been started")
def init_job_started(client, tmp_project, ctx):
    valid_zip_at_temp_path(tmp_project, ctx)
    resp = client.post(
        "/api/action/init-from-zip",
        data=json.dumps({"zipPath": ctx["zip_path"]}),
        content_type="application/json",
    )
    data = resp.get_json()
    assert "jobId" in data, f"No jobId in response: {data}"
    ctx["jobId"] = data["jobId"]


@given("auto-update is currently enabled")
def auto_update_enabled(ctx):
    ctx["auto_update_was_enabled"] = True


# ===========================================================================
# WHEN steps
# ===========================================================================

@when('I trigger "Run Update"')
def trigger_run_update(client, tmp_project, ctx):
    with mock.patch("subprocess.run") as mock_run:
        mock_run.return_value = mock.Mock(stdout="Update done", stderr="", returncode=0)
        if ctx.get("missing_script"):
            resp = client.post("/api/action/update")
        else:
            resp = client.post("/api/action/update")
        ctx["response"] = resp
        ctx["mock_run"] = mock_run


@when('I trigger "Import Installed"')
def trigger_import_installed(client, tmp_project, ctx):
    with mock.patch("subprocess.run") as mock_run:
        mock_run.return_value = mock.Mock(stdout="Done", stderr="", returncode=0)
        resp = client.post("/api/action/import-installed")
        ctx["response"] = resp
        ctx["mock_run"] = mock_run


@when('I trigger "Export Configuration" to a temp path')
def trigger_export_to_temp(client, tmp_project, ctx):
    out = tmp_project / "export_test.zip"
    resp = client.post(
        "/api/action/export-config",
        data=json.dumps({"outputPath": str(out)}),
        content_type="application/json",
    )
    ctx["response"] = resp
    ctx["output_path"] = out


@when('I trigger "Export Configuration" without specifying a path')
def trigger_export_no_path(client, tmp_project, ctx):
    resp = client.post(
        "/api/action/export-config",
        data=json.dumps({}),
        content_type="application/json",
    )
    ctx["response"] = resp
    if resp.status_code == 200:
        data = resp.get_json()
        ctx["output_path"] = Path(data.get("path", ""))


@when("I request the default export path")
def request_default_export_path(client, ctx):
    resp = client.get("/api/export/default-path")
    ctx["response"] = resp


@when('I trigger "Wi-Fi Export" without a DB path')
def trigger_wifi_no_db(client, tmp_project, ctx):
    resp = client.post(
        "/api/action/wifi-export",
        data=json.dumps({"password": "secret"}),
        content_type="application/json",
    )
    ctx["response"] = resp


@when('I trigger "Wi-Fi Export" with a DB path but no password')
def trigger_wifi_no_password(client, tmp_project, ctx):
    resp = client.post(
        "/api/action/wifi-export",
        data=json.dumps({"db": "/some/path.kdbx"}),
        content_type="application/json",
    )
    ctx["response"] = resp


@when('I trigger "Wi-Fi Export" without a DB path but with a password')
def trigger_wifi_no_db_with_password(client, tmp_project, ctx):
    with mock.patch("subprocess.run") as mock_run:
        mock_run.return_value = mock.Mock(stdout="ok", stderr="", returncode=0)
        resp = client.post(
            "/api/action/wifi-export",
            data=json.dumps({"password": "secret"}),
            content_type="application/json",
        )
        ctx["response"] = resp
        ctx["mock_run"] = mock_run


@when('I trigger "Wi-Fi Export" with valid DB path and password')
def trigger_wifi_valid(client, tmp_project, ctx):
    resp = client.post(
        "/api/action/wifi-export",
        data=json.dumps({"db": "/nonexistent/path.kdbx", "password": "secret"}),
        content_type="application/json",
    )
    ctx["response"] = resp


@when(parsers.parse('the script "{script_name}" does not exist'))
def script_not_exist_when(script_name, tmp_project, ctx):
    p = tmp_project / "src" / script_name
    if p.exists():
        p.unlink()


@when('I trigger "Init from Zip" without a zip path')
def trigger_init_zip_no_path(client, tmp_project, ctx):
    resp = client.post(
        "/api/action/init-from-zip",
        data=json.dumps({}),
        content_type="application/json",
    )
    ctx["response"] = resp


@when('I trigger "Init from Zip" with a non-existent zip path')
def trigger_init_zip_missing_file(client, tmp_project, ctx):
    resp = client.post(
        "/api/action/init-from-zip",
        data=json.dumps({"zipPath": "/definitely/not/there.zip"}),
        content_type="application/json",
    )
    ctx["response"] = resp


@when('I trigger "Init from Zip" with that zip path')
def trigger_init_zip_valid(client, tmp_project, ctx):
    zip_path = ctx.get("zip_path")
    assert zip_path, "zip_path not set in context"
    resp = client.post(
        "/api/action/init-from-zip",
        data=json.dumps({"zipPath": zip_path}),
        content_type="application/json",
    )
    ctx["response"] = resp


@when("I poll the job status")
def poll_job_status(client, ctx):
    job_id = ctx.get("jobId")
    assert job_id, "No jobId in context"
    resp = client.get(f"/api/action/init-status/{job_id}")
    ctx["status_response"] = resp


@when("I request the auto-update status")
def request_auto_update_status(client, ctx):
    resp = client.get("/api/auto-update/status")
    ctx["response"] = resp


@when("I toggle auto-update to enabled")
def toggle_auto_update_on(client, tmp_project, ctx):
    with mock.patch("subprocess.run") as mock_run:
        mock_run.return_value = mock.Mock(stdout="ok", stderr="", returncode=0)
        resp = client.post(
            "/api/auto-update/toggle",
            data=json.dumps({"enabled": True}),
            content_type="application/json",
        )
        ctx["response"] = resp
        ctx["mock_run"] = mock_run


@when("I toggle auto-update to disabled")
def toggle_auto_update_off(client, tmp_project, ctx):
    with mock.patch("subprocess.run") as mock_run:
        mock_run.return_value = mock.Mock(stdout="", stderr="", returncode=0)
        resp = client.post(
            "/api/auto-update/toggle",
            data=json.dumps({"enabled": False}),
            content_type="application/json",
        )
        ctx["response"] = resp


# ===========================================================================
# THEN steps
# ===========================================================================

@then("the response contains an exit code")
def response_has_exit_code(ctx):
    resp = ctx.get("response") or ctx.get("status_response")
    data = resp.get_json()
    assert "code" in data, f"'code' not in response: {data}"


@then("no backend error is returned")
def no_backend_error(ctx):
    resp = ctx.get("response")
    data = resp.get_json()
    assert "error" not in data or data["error"] is None, f"Unexpected error: {data.get('error')}"


@then("the response contains an error message")
def has_error_message(ctx):
    resp = ctx.get("response")
    data = resp.get_json()
    assert "error" in data and data["error"], f"Expected error in: {data}"


@then("the error message mentions the missing script")
def error_mentions_script(ctx):
    resp = ctx.get("response")
    data = resp.get_json()
    err = data.get("error", "")
    assert any(kw in err.lower() for kw in ("not found", "script", "missing", "update")), \
        f"Error doesn't mention script: {err}"


@then(parsers.parse('the backend invokes "{script_name}" with "{flag}"'))
def backend_invokes_script_with_flag(script_name, flag, ctx):
    mock_run = ctx.get("mock_run")
    assert mock_run and mock_run.called, f"{script_name} subprocess was not called"
    call_args = mock_run.call_args
    cmd = call_args[0][0] if call_args[0] else call_args[1].get("args", [])
    assert flag in cmd, f"Flag '{flag}' not found in cmd: {cmd}"


@then("a zip file is created at that path")
def zip_created(ctx):
    out = ctx.get("output_path")
    assert out and Path(out).exists(), f"Zip not found at {out}"


@then(parsers.parse("the zip contains \"{filename}\""))
def zip_contains_file(filename, ctx):
    out = ctx.get("output_path")
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    assert filename in names, f"'{filename}' not in zip ({names})"


@then(parsers.parse('the response status is "{status}"'))
def response_status_is(status, ctx):
    resp = ctx.get("response")
    if status.isdigit():
        assert resp.status_code == int(status), f"Expected HTTP {status}, got {resp.status_code}"
    else:
        data = resp.get_json()
        assert data.get("status") == status, f"Expected status='{status}', got: {data}"


@then("a zip file is created at the default location")
def zip_at_default_location(ctx):
    out = ctx.get("output_path")
    assert out and Path(out).exists(), f"Zip not found at default location: {out}"


@then(parsers.parse('the response contains a "{field}" field ending with "{suffix}"'))
def response_field_ends_with(field, suffix, ctx):
    resp = ctx.get("response")
    data = resp.get_json()
    assert field in data, f"'{field}' not in response: {data}"
    assert str(data[field]).endswith(suffix), f"'{data[field]}' does not end with '{suffix}'"


@then(parsers.parse('the response contains a "{field}" field'))
def response_has_field(field, ctx):
    resp = ctx.get("response") or ctx.get("status_response")
    data = resp.get_json()
    assert field in data, f"'{field}' not in response: {data}"


@then(parsers.parse('the response contains an "{field}" field'))
def response_has_field_article_an(field, ctx):
    resp = ctx.get("response") or ctx.get("status_response")
    data = resp.get_json()
    assert field in data, f"'{field}' not in response: {data}"


@then("the response contains an error message about the missing DB path")
def error_missing_db(ctx):
    resp = ctx.get("response")
    data = resp.get_json()
    err = data.get("error", "").lower()
    assert "db" in err or "path" in err or "wifi" in err, f"Unexpected error: {data.get('error')}"


@then("the response contains an error message about the missing password")
def error_missing_password(ctx):
    resp = ctx.get("response")
    data = resp.get_json()
    err = data.get("error", "").lower()
    assert "password" in err or "pass" in err, f"Unexpected error: {data.get('error')}"


@then(parsers.parse('the backend uses "{path}" as the DB path'))
def backend_uses_db_path(path, ctx):
    mock_run = ctx.get("mock_run")
    assert mock_run and mock_run.called, "subprocess.run was not called"
    call_args = mock_run.call_args
    cmd = call_args[0][0] if call_args[0] else call_args[1].get("args", [])
    assert path in cmd, f"Expected '{path}' in cmd: {cmd}"


@then("the response contains an error about the missing script")
def error_missing_script(ctx):
    resp = ctx.get("response")
    data = resp.get_json()
    assert "error" in data or resp.status_code in (400, 404, 500), \
        f"Expected error, got: {data}"


@then(parsers.parse("the response status is {code:d}"))
def response_http_status(code, ctx):
    resp = ctx.get("response")
    assert resp.status_code == code, f"Expected HTTP {code}, got {resp.status_code}"


@then(parsers.parse('the response contains a "{field}"'))
def response_has_field_alt(field, ctx):
    resp = ctx.get("response")
    data = resp.get_json()
    assert field in data, f"'{field}' not in response: {data}"


@then(parsers.parse('the response status field is "{value}"'))
def response_status_field(value, ctx):
    resp = ctx.get("response")
    data = resp.get_json()
    assert data.get("status") == value, f"Expected status='{value}', got {data}"


@then("the status contains a \"progress\" field")
def status_has_progress(ctx):
    resp = ctx.get("status_response")
    data = resp.get_json()
    assert "progress" in data, f"'progress' not in status: {data}"


@then("the status contains a \"done\" field")
def status_has_done(ctx):
    resp = ctx.get("status_response")
    data = resp.get_json()
    assert "done" in data, f"'done' not in status: {data}"


@then("the setup script is invoked")
def setup_script_invoked(ctx):
    mock_run = ctx.get("mock_run")
    assert mock_run and mock_run.called, "setup_auto_update.sh not invoked"


@then('the response "enabled" field is true')
def enabled_is_true(ctx):
    resp = ctx.get("response")
    data = resp.get_json()
    assert data.get("enabled") is True, f"expected enabled=True, got: {data}"


@then('the response "enabled" field is false')
def enabled_is_false(ctx):
    resp = ctx.get("response")
    data = resp.get_json()
    assert data.get("enabled") is False, f"expected enabled=False, got: {data}"
