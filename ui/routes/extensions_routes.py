import subprocess

from flask import Blueprint, jsonify, request
import app_config as cfg
from api import dto


def create_extensions_blueprint(state):
    bp = Blueprint('extensions_routes', __name__)

    @bp.route('/api/extensions/scan')
    def api_extensions_scan():
        try:
            result = state.USE_CASES.extensions.scan_local()
            return dto.success(result.payload, result.status)
        except Exception as exc:
            state.app.logger.exception('extensions scan failed')
            return dto.from_exception(exc)

    @bp.route('/api/extensions')
    def api_extensions():
        try:
            result = state.USE_CASES.extensions.list_configured()
            return dto.success(result.payload, result.status)
        except Exception as exc:
            return dto.from_exception(exc)

    @bp.route('/api/extensions/update', methods=['POST'])
    def api_extensions_update():
        try:
            data = request.json or {}
            lines = data.get('lines')
            if not isinstance(lines, list):
                return jsonify({'error': 'invalid payload, expected {lines: [..]}'}), 400
            result = state.USE_CASES.extensions.update_config(lines)
            return dto.success(result.payload, result.status)
        except Exception as exc:
            return dto.from_exception(exc)

    @bp.route('/api/extensions/search')
    def api_extensions_search():
        try:
            query = request.args.get('q', '').strip()
            result = state.USE_CASES.extensions.search_extensions(query)
            return dto.success(result.payload, result.status)
        except Exception as exc:
            return dto.from_exception(exc)

    @bp.route('/api/extensions/install', methods=['POST'])
    def api_extensions_install():
        try:
            result = state.USE_CASES.extensions.install_configured(timeout=cfg.ROUTE_EXT_INSTALL_TIMEOUT_SEC)
            return dto.success(result.payload, result.status)
        except subprocess.TimeoutExpired as exc:
            return jsonify({
                'error': f'extensions install timed out after {cfg.ROUTE_EXT_INSTALL_TIMEOUT_SEC} seconds',
                'stdout': exc.stdout or '',
                'stderr': exc.stderr or '',
            }), 504
        except Exception as exc:
            return dto.from_exception(exc)

    @bp.route('/api/sudo/status')
    def api_sudo_status():
        try:
            if state.platform.system().lower() == 'darwin':
                return jsonify({
                    'available': True,
                    'interactivePrompt': True,
                    'message': 'Administrator password can be requested with a GUI prompt when needed.',
                })
            result = subprocess.run(['sudo', '-n', 'true'], capture_output=True, text=True)
            if result.returncode == 0:
                return jsonify({'available': True, 'interactivePrompt': False})
            return jsonify({
                'available': False,
                'interactivePrompt': False,
                'message': 'sudo session is not available in non-interactive mode.',
            })
        except Exception as exc:
            return jsonify({'available': False, 'message': str(exc)})

    @bp.route('/api/extensions/uninstall', methods=['POST'])
    def api_extensions_uninstall():
        try:
            data = request.json or {}
            browser = data.get('browser', '').lower()
            ext_id = data.get('id', '').strip()
            result = state.USE_CASES.extensions.uninstall(browser, ext_id)
            return dto.success(result.payload, result.status)
        except Exception as exc:
            return dto.from_exception(exc)

    return bp
