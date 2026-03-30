import threading
import uuid
from pathlib import Path

from dotenv import set_key
from flask import Blueprint, jsonify, request
import app_config as cfg
from api import dto


def create_actions_blueprint(state):
    bp = Blueprint('actions_routes', __name__)

    @bp.route('/api/action/update', methods=['POST'])
    def api_action_update():
        try:
            result = state.USE_CASES.actions.run_update(timeout=cfg.ROUTE_ACTION_UPDATE_TIMEOUT_SEC)
            return dto.success(result.payload, result.status)
        except Exception as exc:
            return dto.from_exception(exc)

    @bp.route('/api/action/install', methods=['POST'])
    def api_action_install():
        try:
            data = request.json or {}
            result = state.USE_CASES.actions.run_install(data.get('app'))
            return dto.success(result.payload, result.status)
        except Exception as exc:
            return dto.from_exception(exc)

    @bp.route('/api/action/import-installed', methods=['POST'])
    def api_action_import_installed():
        try:
            result = state.USE_CASES.actions.run_import_installed()
            return dto.success(result.payload, result.status)
        except Exception as exc:
            return dto.from_exception(exc)

    @bp.route('/api/export/default-path')
    def api_export_default_path():
        path = state._default_export_path()
        return jsonify({'default_dir': str(path.parent), 'default_path': str(path)})

    @bp.route('/api/automation/status')
    def api_automation_status():
        env = state._env_map()
        auto_update_os_status = state._auto_update_status_for_os()
        return jsonify({
            'scheduler_started': bool(state.AUTOMATION_THREAD and state.AUTOMATION_THREAD.is_alive()),
            'auto_update_enabled': state._str_to_bool(env.get('AUTO_UPDATE_ENABLED', 'false')),
            'auto_update_system': auto_update_os_status,
            'state': state.AUTOMATION_STATE,
        })

    @bp.route('/api/action/export-config', methods=['POST'])
    def api_action_export_config():
        data = request.json or {}
        out_path_raw = (data.get('outputPath') or '').strip()
        out_path = Path(out_path_raw).expanduser() if out_path_raw else state._default_export_path()
        try:
            result = state._export_configuration(out_path)
            return jsonify(result)
        except FileNotFoundError as exc:
            return jsonify({'error': str(exc)}), 404
        except Exception as exc:
            return jsonify({'error': f'Export failed: {exc}'}), 500

    @bp.route('/api/dotfiles/status')
    def api_dotfiles_status():
        try:
            return jsonify(state._actions_service().get_dotfiles_status())
        except Exception as exc:
            return jsonify({'error': str(exc)}), 500

    @bp.route('/api/shared-config/status')
    def api_shared_config_status():
        try:
            return jsonify(state._actions_service().get_shared_config_status())
        except Exception as exc:
            return jsonify({'error': str(exc)}), 500

    @bp.route('/api/action/dotfiles', methods=['POST'])
    def api_action_dotfiles():
        data = request.json or {}
        result, status = state._actions_service().run_dotfiles_action(data.get('action'))
        return jsonify(result), status

    @bp.route('/api/action/shared-config', methods=['POST'])
    def api_action_shared_config():
        data = request.json or {}
        result, status = state._actions_service().run_shared_config_action(data.get('action'))
        return jsonify(result), status

    @bp.route('/api/auto-update/status')
    def api_auto_update_status():
        try:
            return jsonify(state._auto_update_status_for_os())
        except Exception as exc:
            return jsonify({'error': str(exc)}), 500

    @bp.route('/api/auto-update/toggle', methods=['POST'])
    def api_auto_update_toggle():
        data = request.json or {}
        enabled = bool(data.get('enabled'))
        try:
            state._ensure_env_local_complete()
            set_key(str(state.ENV_LOCAL), 'AUTO_UPDATE_ENABLED', 'true' if enabled else 'false')
            state._sync_env_to_repo_if_possible()
            sync = state._sync_update_cron_from_env()
            return jsonify({'status': 'ok', 'enabled': enabled, 'cron': sync})
        except Exception as exc:
            return jsonify({'error': str(exc)}), 500

    @bp.route('/api/auto-update/cron-install', methods=['POST'])
    def api_auto_update_cron_install():
        try:
            cron_result = state._apply_update_cron_job()
            return jsonify({'status': 'ok', 'cron': cron_result})
        except Exception as exc:
            return jsonify({'error': str(exc)}), 500

    @bp.route('/api/auto-update/cron-remove', methods=['POST'])
    def api_auto_update_cron_remove():
        try:
            cron_result = state._remove_update_cron_job()
            return jsonify({'status': 'ok', 'cron': cron_result})
        except Exception as exc:
            return jsonify({'error': str(exc)}), 500

    @bp.route('/api/action/init-from-zip', methods=['POST'])
    def api_action_init_from_zip():
        try:
            data = request.json or {}
            result = state.USE_CASES.actions.init_from_zip((data.get('zipPath') or '').strip())
            return dto.success(result.payload, result.status)
        except Exception as exc:
            return dto.from_exception(exc)

    @bp.route('/api/action/init-from-shared', methods=['POST'])
    def api_action_init_from_shared():
        try:
            result = state.USE_CASES.actions.init_from_shared()
            return dto.success(result.payload, result.status)
        except Exception as exc:
            return dto.from_exception(exc)

    @bp.route('/api/action/init-status/<job_id>')
    def api_action_init_status(job_id):
        try:
            result = state.USE_CASES.actions.init_status(job_id)
            return dto.success(result.payload, result.status)
        except Exception as exc:
            return dto.from_exception(exc)

    @bp.route('/api/action/wifi-export', methods=['POST'])
    def api_action_wifi_export():
        data = request.json or {}
        result, status = state._actions_service().run_wifi_export(data.get('db'), data.get('password'))
        return jsonify(result), status

    return bp
