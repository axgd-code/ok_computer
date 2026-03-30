from domain.models import ApiResult
from shared.errors import ValidationError
from application.ports import ExtensionSearchPort


class ExtensionsUseCases:
    def __init__(self, state, search_port: ExtensionSearchPort | None = None):
        self.state = state
        self.search_port = search_port

    def scan_local(self):
        return ApiResult(self.state.scan_local_extensions(), status=200)

    def list_configured(self):
        return ApiResult(self.state.parse_extensions_conf(), status=200)

    def update_config(self, lines):
        ext_file = self.state._config_target_path('extensions.conf')
        ext_file.parent.mkdir(parents=True, exist_ok=True)
        ext_file.write_text('\n'.join(lines) + '\n')
        return ApiResult({'status': 'ok'}, status=200)

    def install_configured(self, timeout):
        if not self.state.EXTENSIONS_INSTALL_LOCK.acquire(blocking=False):
            return ApiResult({'error': 'extensions install already running'}, status=409)
        try:
            script, checked = self.state.find_script('setup_browsers.sh')
            if not script:
                return ApiResult({'error': 'setup_browsers.sh not found', 'checked': checked}, status=500)
            result = self.state._run_script_with_optional_admin(script, timeout=timeout, require_admin=True)
            status = 200
            if result.get('error') == 'administrator authentication canceled by user':
                status = 401
            return ApiResult(result, status=status)
        finally:
            self.state.EXTENSIONS_INSTALL_LOCK.release()

    def uninstall(self, browser, ext_id):
        if not browser or not ext_id:
            raise ValidationError('missing browser or id parameter')
        result = self.state.uninstall_extension(browser, ext_id)
        status = 200 if result.get('status') == 'ok' else 400
        return ApiResult(result, status=status)

    def search_extensions(self, query):
        if not query:
            return ApiResult({'chrome': [], 'firefox': []}, status=200)
        if self.search_port is None:
            return ApiResult({'chrome': [], 'firefox': []}, status=200)
        payload = self.search_port.search(query)
        return ApiResult(payload, status=200)
