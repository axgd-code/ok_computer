from types import SimpleNamespace
from pathlib import Path
import sys
import importlib

ROOT_DIR = Path(__file__).resolve().parents[1]
UI_DIR = ROOT_DIR / 'ui'
sys.path.insert(0, str(UI_DIR))

ExtensionsUseCases = importlib.import_module('application.use_cases.extensions_use_cases').ExtensionsUseCases
PackagesUseCases = importlib.import_module('application.use_cases.packages_use_cases').PackagesUseCases
ValidationError = importlib.import_module('shared.errors').ValidationError


class _FakePackageSearchPort:
    def search(self, query, urlquote_fn):
        return {
            'query': query,
            'results': [
                {
                    'name': 'git',
                    'desc': 'Git',
                    'homebrew': True,
                    'homebrew_type': 'brew',
                    'chocolatey': True,
                    'apt': True,
                    'mac': 'git',
                    'win': 'git',
                    'linux': 'git',
                }
            ],
        }


class _FakeExtensionSearchPort:
    def search(self, query):
        return {
            'chrome': [{'id': 'abc', 'name': query, 'publisher': 'x', 'url': 'https://example'}],
            'firefox': [{'slug': 'abc', 'name': query, 'publisher': 'x', 'url': 'https://example'}],
        }


def _base_state():
    return SimpleNamespace(
        read_packages=lambda: [{'type': 'brew', 'mac': 'git', 'win': 'git', 'desc': 'Git'}],
        PACKAGES_SERVICE=SimpleNamespace(enrich_packages_with_availability=lambda p: p),
        check_homebrew=lambda name: True,
        check_chocolatey=lambda name: False,
        check_debian=lambda name: True,
        _actions_service=lambda: SimpleNamespace(
            run_package_update=lambda app: ({'status': 'ok', 'app': app}, 200),
            run_package_remove=lambda app, run_uninstall=True: ({'status': 'ok', 'app': app, 'run_uninstall': run_uninstall}, 200),
        ),
        _urlquote=lambda v: v,
        scan_local_extensions=lambda: [{'id': '1'}],
        parse_extensions_conf=lambda: [{'mode': 'chrome'}],
        find_conf_file=lambda name: None,
        BASE_DIR='.',
        EXTENSIONS_INSTALL_LOCK=SimpleNamespace(
            acquire=lambda blocking=False: True,
            release=lambda: None,
        ),
        find_script=lambda name: ('/tmp/setup_browsers.sh', []),
        _run_script_with_optional_admin=lambda script, timeout=None, require_admin=False: {'code': 0},
        uninstall_extension=lambda browser, ext_id: {'status': 'ok', 'browser': browser, 'id': ext_id},
    )


def test_packages_use_case_search_uses_port():
    state = _base_state()
    uc = PackagesUseCases(state, search_port=_FakePackageSearchPort())

    result = uc.search_packages('git')

    assert result.status == 200
    assert result.payload['query'] == 'git'
    assert result.payload['results'][0]['name'] == 'git'


def test_packages_use_case_search_requires_query():
    state = _base_state()
    uc = PackagesUseCases(state, search_port=_FakePackageSearchPort())

    try:
        uc.search_packages('')
    except ValidationError as exc:
        assert 'missing q parameter' in str(exc)
    else:
        assert False, 'ValidationError expected'


def test_extensions_use_case_search_uses_port():
    state = _base_state()
    uc = ExtensionsUseCases(state, search_port=_FakeExtensionSearchPort())

    result = uc.search_extensions('ublock')

    assert result.status == 200
    assert result.payload['chrome'][0]['name'] == 'ublock'
    assert result.payload['firefox'][0]['name'] == 'ublock'


def test_extensions_use_case_search_empty_query_returns_empty_lists():
    state = _base_state()
    uc = ExtensionsUseCases(state, search_port=_FakeExtensionSearchPort())

    result = uc.search_extensions('')

    assert result.status == 200
    assert result.payload == {'chrome': [], 'firefox': []}
