import os
import platform
import subprocess

from dotenv import set_key
from flask import Blueprint, jsonify, request
import app_config as cfg
from api import dto


def create_preferences_blueprint(state):
    bp = Blueprint('preferences_routes', __name__)

    @bp.route('/api/system-settings')
    def api_system_settings():
        try:
            result = state.USE_CASES.preferences.get_system_settings()
            return dto.success(result.payload, result.status)
        except Exception as exc:
            return dto.from_exception(exc)

    @bp.route('/api/system-settings/update', methods=['POST'])
    def api_system_settings_update():
        try:
            data = request.json or {}
            lines = data.get('lines')
            if not isinstance(lines, list):
                return jsonify({'error': 'invalid payload, expected {lines: [..]}'}), 400
            result = state.USE_CASES.preferences.update_system_settings(lines)
            return dto.success(result.payload, result.status)
        except Exception as exc:
            return dto.from_exception(exc)

    @bp.route('/api/system-settings/apply', methods=['POST'])
    def api_system_settings_apply():
        try:
            sysname = platform.system().lower()
            if 'darwin' in sysname:
                script_name = 'init_conf_macOs.sh'
            elif 'windows' in sysname or os.name == 'nt':
                script_name = 'init_conf_windows.sh'
            elif 'linux' in sysname:
                script_name = 'init_conf_linux.sh'
            else:
                return jsonify({'error': f'unsupported operating system: {sysname}'}), 400

            script, checked = state.find_script(script_name)
            if not script:
                return jsonify({'error': f'{script_name} not found', 'checked': checked}), 500

            require_admin = 'darwin' in sysname
            result = state._run_script_with_optional_admin(
                script,
                timeout=cfg.ROUTE_SYSTEM_SETTINGS_APPLY_TIMEOUT_SEC,
                require_admin=require_admin,
            )
            status = 200
            if result.get('error') == 'administrator authentication canceled by user':
                status = 401
            elif result.get('error'):
                status = 500
            return jsonify(result), status
        except subprocess.TimeoutExpired:
            return jsonify({'error': f'system settings apply timed out after {cfg.ROUTE_SYSTEM_SETTINGS_APPLY_TIMEOUT_SEC}s'}), 504
        except Exception as exc:
            return jsonify({'error': str(exc)}), 500

    @bp.route('/api/env', methods=['GET', 'POST'])
    def api_env():
        try:
            if request.method == 'GET':
                result = state.USE_CASES.preferences.get_env()
                return dto.success(result.payload, result.status)
            result = state.USE_CASES.preferences.update_env(request.json or {})
            return dto.success(result.payload, result.status)
        except Exception as exc:
            return dto.from_exception(exc)

    @bp.route('/api/env/exists')
    def api_env_exists():
        try:
            return jsonify({'exists': state.ENV_LOCAL.exists()})
        except Exception as exc:
            return jsonify({'error': str(exc)}), 500

    @bp.route('/api/env/init', methods=['POST'])
    def api_env_init():
        try:
            if state.ENV_EXAMPLE.exists():
                state.ENV_LOCAL.write_text(state.ENV_EXAMPLE.read_text())
            else:
                state.ENV_LOCAL.write_text('')
            state._sync_env_to_repo_if_possible()
            return jsonify({'status': 'ok'})
        except Exception as exc:
            return jsonify({'error': str(exc)}), 500

    @bp.route('/api/env/location')
    def api_env_location():
        try:
            return jsonify({'path': str(state.ENV_LOCAL), 'dir': str(state.ENV_LOCAL.parent), 'exists': state.ENV_LOCAL.exists()})
        except Exception as exc:
            return jsonify({'error': str(exc)}), 500

    return bp
