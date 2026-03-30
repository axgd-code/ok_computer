"""Playwright BDD tests for browser-level UI workflows.

These tests are skipped automatically if Playwright or browser binaries are unavailable.
"""

import importlib.util
import shutil
import socket
import threading
from pathlib import Path
from unittest import mock

import pytest
from pytest_bdd import given, when, then, parsers, scenarios
from werkzeug.serving import make_server

try:
    from playwright.sync_api import sync_playwright  # type: ignore[reportMissingImports]
except Exception:  # pragma: no cover
    sync_playwright = None


ROOT_DIR = Path(__file__).resolve().parents[1]
UI_DIR = ROOT_DIR / "ui"
_APP_SPEC = importlib.util.spec_from_file_location("okc_ui_app", UI_DIR / "app.py")
assert _APP_SPEC and _APP_SPEC.loader
okc_app = importlib.util.module_from_spec(_APP_SPEC)
_APP_SPEC.loader.exec_module(okc_app)

scenarios("features/ui_playwright.feature")


@pytest.fixture
def isolated_project(tmp_path):
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)

    real_src = ROOT_DIR / "src"
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
        f = real_src / name
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
    ):
        yield tmp_path


@pytest.fixture
def web_server(isolated_project):
    # Bind an ephemeral localhost port.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    host, port = sock.getsockname()
    sock.close()

    server = make_server(host, port, okc_app.app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield f"http://{host}:{port}"

    server.shutdown()
    thread.join(timeout=2)


@pytest.fixture
def ui_ctx(web_server):
    if sync_playwright is None:
        pytest.skip("Playwright is not installed in this environment")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"Playwright browser not available: {exc}")

        page = browser.new_page()
        page.goto(web_server, wait_until="networkidle")
        yield {"base_url": web_server, "page": page}
        browser.close()


@given("the test web server is running")
def given_server_running(web_server):
    assert web_server.startswith("http://")


@given("a browser page is open on the application")
def given_browser_open(ui_ctx):
    assert ui_ctx["page"].title() is not None


@then("I should see the main navigation tabs")
def then_tabs_visible(ui_ctx):
    page = ui_ctx["page"]
    for label in ["1. Initialization", "2. Customization", "3. Export"]:
        expect = page.get_by_text(label, exact=False)
        assert expect.count() > 0


@when(parsers.parse('I open the "{tab_id}" tab'))
def when_open_tab(ui_ctx, tab_id):
    page = ui_ctx["page"]
    page.evaluate(f"switchTab('{tab_id}')")


@then(parsers.parse('the tab content "{tab_id}" is visible'))
def then_tab_content_visible(ui_ctx, tab_id):
    page = ui_ctx["page"]
    cls = page.eval_on_selector(f"#{tab_id}", "el => el.className")
    assert "active" in cls


@when(parsers.parse('I set environment key "{key}" to "{value}"'))
def when_set_env_key(ui_ctx, key, value):
    page = ui_ctx["page"]
    selector = f"#env-form input[data-key='{key}']"
    page.wait_for_selector(selector, timeout=5000)
    page.fill(selector, value)


@when("I save environment settings")
def when_save_env(ui_ctx):
    page = ui_ctx["page"]
    page.evaluate("saveEnv()")
    page.wait_for_timeout(300)


@then(parsers.parse('environment key "{key}" should equal "{value}"'))
def then_env_key_equals(ui_ctx, key, value):
    page = ui_ctx["page"]
    page.reload(wait_until="networkidle")
    page.evaluate("switchTab('customization')")
    selector = f"#env-form input[data-key='{key}']"
    page.wait_for_selector(selector, timeout=5000)
    actual = page.eval_on_selector(selector, "el => el.value")
    assert actual == value


@when(parsers.parse('I update the first system setting description to "{value}"'))
def when_update_first_system_desc(ui_ctx, value):
    page = ui_ctx["page"]
    page.wait_for_selector("#system-settings-list tbody tr input[data-field='desc']", timeout=5000)
    page.fill("#system-settings-list tbody tr input[data-field='desc']", value)


@when("I save system settings")
def when_save_system_settings(ui_ctx):
    page = ui_ctx["page"]
    page.evaluate("saveSystemSettings()")
    page.wait_for_timeout(300)


@when("I apply system settings")
def when_apply_system_settings(ui_ctx):
    page = ui_ctx["page"]
    page.evaluate("applySystemSettings()")
    page.wait_for_selector("#system-settings-output", timeout=5000)


@then(parsers.parse('system settings output should contain "{fragment}"'))
def then_system_output_contains(ui_ctx, fragment):
    page = ui_ctx["page"]
    text = page.inner_text("#system-settings-output")
    assert fragment in text


@when(parsers.parse('I search for "{query}" in mode "{mode}"'))
def when_search(ui_ctx, query, mode):
    page = ui_ctx["page"]
    page.select_option("#search-kind", mode)
    page.fill("#search-input", query)
    page.click("#search-btn")
    page.wait_for_timeout(600)


@then("the search results area is visible")
def then_search_visible(ui_ctx):
    page = ui_ctx["page"]
    assert page.is_visible("#search-results")


@then("the first boolean system setting row contains a shared checkbox")
def then_system_setting_checkbox(ui_ctx):
    page = ui_ctx["page"]
    page.wait_for_selector("#system-settings-list tbody tr input[data-field='value'][type='checkbox']", timeout=5000)
    checkbox = page.query_selector("#system-settings-list tbody tr input[data-field='value'][type='checkbox']")
    assert checkbox is not None
    assert checkbox.get_attribute('type') == 'checkbox'


@when("I check the first boolean system setting's shared checkbox")
def when_check_mac_checkbox(ui_ctx):
    page = ui_ctx["page"]
    checkbox = page.query_selector("#system-settings-list tbody tr input[data-field='value'][type='checkbox']")
    assert checkbox is not None
    if not checkbox.is_checked():
        checkbox.check()


@when("I refresh extensions list")
def when_refresh_extensions(ui_ctx):
    page = ui_ctx["page"]
    page.evaluate("refreshExtensions()")
    page.wait_for_timeout(400)


@when("I save extensions list")
def when_save_extensions(ui_ctx):
    page = ui_ctx["page"]
    page.evaluate("saveExtensions()")
    page.wait_for_timeout(300)


@then("extensions output should be available or list remains visible")
def then_extensions_state(ui_ctx):
    page = ui_ctx["page"]
    assert page.is_visible("#extensions-list")


@then("extension rows should expose at least one icon")
def then_extensions_have_icons(ui_ctx):
    page = ui_ctx["page"]
    page.wait_for_selector("#extensions-list table", timeout=5000)
    icons = page.query_selector_all("#extensions-list tbody tr td img")
    assert len(icons) > 0


@then("extension rows should expose official extension links")
def then_extensions_have_official_links(ui_ctx):
    page = ui_ctx["page"]
    links = page.query_selector_all("#extensions-list tbody tr td a[href]")
    assert len(links) > 0

    hrefs = [link.get_attribute("href") or "" for link in links]
    assert any(("chrome.google.com/webstore/detail" in h) or ("addons.mozilla.org/firefox/addon" in h) for h in hrefs)
