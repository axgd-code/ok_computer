import os
import platform
import subprocess
from pathlib import Path

from flask import Blueprint, jsonify, request
import app_config as cfg
from api import dto


def create_core_blueprint(state):
    bp = Blueprint('core_routes', __name__)

    @bp.route('/api/log', methods=['POST'])
    def api_log():
        try:
            data = request.json or {}
            level = (data.get('level') or 'INFO').upper()
            message = data.get('message') or data.get('msg') or data.get('m') or data.get('message', '')
            meta = data.get('meta')
            if level == 'ERROR':
                state.app.logger.error(message + (f' | meta={meta}' if meta else ''))
            elif level in ('WARN', 'WARNING'):
                state.app.logger.warning(message + (f' | meta={meta}' if meta else ''))
            else:
                state.app.logger.info(message + (f' | meta={meta}' if meta else ''))
            return jsonify({'status': 'ok'})
        except Exception as exc:
            return jsonify({'error': str(exc)}), 500

    @bp.route('/')
    def index():
        return state.render_template('index.html')

    @bp.route('/api/open-path', methods=['POST'])
    def api_open_path():
        try:
            data = request.json or {}
            result = state.USE_CASES.core.open_path((data.get('path') or '').strip())
            return dto.success(result.payload, result.status)
        except Exception as exc:
            return dto.from_exception(exc)

    @bp.route('/api/scripts/sync', methods=['POST'])
    def api_scripts_sync():
        try:
            result = state.USE_CASES.core.sync_scripts()
            return dto.success(result.payload, result.status)
        except Exception as exc:
            return dto.from_exception(exc)

    @bp.route('/api/browse', methods=['POST'])
    def api_browse():
        data = request.json or {}
        mode = data.get('mode', 'dir')
        title = data.get('title', 'Select')
        try:
            if platform.system() == 'Darwin':
                if mode == 'file':
                    script = f'POSIX path of (choose file with prompt "{title}")'
                else:
                    script = f'POSIX path of (choose folder with prompt "{title}")'
                result = subprocess.run(
                    ['osascript', '-e', script],
                    capture_output=True,
                    text=True,
                    timeout=cfg.ROUTE_BROWSE_TIMEOUT_SEC,
                )
                if result.returncode == 0:
                    chosen = result.stdout.strip().rstrip('/')
                    return jsonify({'path': chosen})
                return jsonify({'cancelled': True})

            try:
                import tkinter as tk
                from tkinter import filedialog

                root = tk.Tk()
                root.withdraw()
                root.attributes('-topmost', True)
                if mode == 'file':
                    chosen = filedialog.askopenfilename(title=title)
                else:
                    chosen = filedialog.askdirectory(title=title)
                root.destroy()
                if chosen:
                    return jsonify({'path': str(Path(chosen))})
                return jsonify({'cancelled': True})
            except Exception:
                return jsonify({'error': 'native_picker_not_supported'})
        except subprocess.TimeoutExpired:
            return jsonify({'cancelled': True})
        except Exception as exc:
            return jsonify({'error': str(exc)}), 500

    @bp.route('/static/<path:p>')
    def static_files(p):
        return state.send_from_directory(os.path.join(os.path.dirname(state.__file__), 'static'), p)

    return bp
