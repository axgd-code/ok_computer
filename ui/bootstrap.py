import argparse
import multiprocessing
import os
import platform
import socket
import sys
import threading
from pathlib import Path

import webview
import app_config as cfg


class FileDialogApi:
    def __init__(self):
        self.window = None

    def open_file(self, title='Select file'):
        try:
            if self.window:
                result = webview.create_file_dialog(self.window, webview.OPEN_DIALOG)
                if isinstance(result, (list, tuple)):
                    return result[0] if result else ''
                return result or ''
        except Exception:
            pass
        return ''

    def open_dir(self, title='Select folder'):
        try:
            if self.window:
                result = webview.create_file_dialog(self.window, webview.FOLDER_DIALOG)
                if isinstance(result, (list, tuple)):
                    return result[0] if result else ''
                return result or ''
        except Exception:
            pass
        return ''


def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(('localhost', port)) == 0


def start_server(state, port):
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    state.app.run(host='0.0.0.0', port=port, debug=debug, threaded=True)


def _handle_cron_cli(state, args):
    try:
        copied = state.ensure_user_scripts_available()
        if copied:
            print(f'Copied {len(copied)} files to persistent scripts dir: {state.USER_SRC_DIR}')
    except Exception as exc:
        print(f'Failed to sync persistent scripts: {exc}')

    if args.cron_install:
        try:
            state._apply_update_cron_job()
            print('Cron job installed successfully')
            print('  Schedule: Every minute')
            runner_script, _ = state.find_script('cron_auto_update.sh')
            if runner_script:
                print(f'  Script: {runner_script}')
            print('\nTo enable: set AUTO_UPDATE_ENABLED=true in ~/.env.local')
        except Exception as exc:
            print(f'Failed to install cron job: {exc}', file=sys.stderr)
            return 1
    elif args.cron_remove:
        try:
            state._remove_update_cron_job()
            print('Cron job removed successfully')
        except Exception as exc:
            print(f'Failed to remove cron job: {exc}', file=sys.stderr)
            return 1
    elif args.cron_status:
        try:
            status = state._auto_update_status_for_os()
            if status.get('enabled'):
                print('Cron job is INSTALLED and ENABLED')
                print(f"  Mode: {status.get('mode', 'unknown')}")
                print(f"  Target: {status.get('target', 'unknown')}")
                try:
                    lines = state._read_crontab_lines()
                    for line in lines:
                        if 'OKC_AUTO_UPDATE' in line:
                            print(f'\n  Cron entry:\n    {line}')
                except Exception:
                    pass
            else:
                print('Cron job is not installed')
                if status.get('error'):
                    print(f'  Error: {status.get("error")}')
        except Exception as exc:
            print(f'Failed to check cron status: {exc}', file=sys.stderr)
            return 1
    return 0


def _sync_startup_state(state):
    try:
        copied = state.ensure_user_scripts_available()
        if copied:
            state.app.logger.info('Copied %d files to persistent scripts dir: %s', len(copied), state.USER_SRC_DIR)
    except Exception as exc:
        state.app.logger.warning('Failed to sync persistent scripts: %s', exc)

    try:
        cron_sync = state._sync_update_cron_from_env()
        state.app.logger.info('Auto-update cron sync result: %s', cron_sync)
    except Exception as exc:
        state.app.logger.warning('Auto-update cron sync failed: %s', exc)

    state.start_automation_scheduler_if_needed()


def _pick_port():
    port = int(os.environ.get('PORT', 5000))
    if is_port_in_use(port):
        if port == 5000:
            port = 5001
        while is_port_in_use(port):
            port += 1
            if port > 5010:
                break
    return port


def _set_macos_app_icon(state):
    if platform.system().lower() != 'darwin':
        return
    try:
        from AppKit import NSApplication, NSImage
        from Foundation import NSBundle, NSProcessInfo

        # Try to replace the default "Python" app name in the macOS menu bar.
        try:
            NSProcessInfo.processInfo().setProcessName_(cfg.APP_DISPLAY_NAME)
            bundle = NSBundle.mainBundle()
            if bundle:
                info = bundle.infoDictionary()
                if info is not None:
                    info['CFBundleName'] = cfg.APP_DISPLAY_NAME
                    info['CFBundleDisplayName'] = cfg.APP_DISPLAY_NAME
        except Exception:
            pass

        icon_candidates = [
            Path(state.__file__).resolve().parent / 'assets' / 'logo.icns',
            Path(state.__file__).resolve().parent / 'assets' / 'logo.png',
            state.BASE_DIR / 'ui' / 'assets' / 'logo.icns',
        ]
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            icon_candidates.append(Path(meipass) / 'logo.icns')
        icon_path = next((path for path in icon_candidates if path.exists()), None)
        if icon_path:
            app_instance = NSApplication.sharedApplication()
            image = NSImage.alloc().initWithContentsOfFile_(str(icon_path))
            if image:
                app_instance.setApplicationIconImage_(image)
    except Exception:
        pass


def _start_webview(state, port):
    api = FileDialogApi()
    _set_macos_app_icon(state)
    try:
        window = webview.create_window(
            cfg.APP_DISPLAY_NAME,
            f'http://localhost:{port}',
            js_api=api,
            width=cfg.WEBVIEW_WINDOW_WIDTH,
            height=cfg.WEBVIEW_WINDOW_HEIGHT,
        )
        api.window = window
    except TypeError:
        window = webview.create_window(
            cfg.APP_DISPLAY_NAME,
            f'http://localhost:{port}',
            width=cfg.WEBVIEW_WINDOW_WIDTH,
            height=cfg.WEBVIEW_WINDOW_HEIGHT,
        )
    is_debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    webview.start(debug=is_debug)
    return window


def run_main(state):
    parser = argparse.ArgumentParser(description='OK Computer - System Configuration Manager')
    parser.add_argument('--cron-install', action='store_true', help='Install cron job and exit')
    parser.add_argument('--cron-remove', '--cron-uninstall', action='store_true', dest='cron_remove', help='Remove cron job and exit')
    parser.add_argument('--cron-status', action='store_true', help='Show cron job status and exit')
    args, _unknown = parser.parse_known_args()

    if args.cron_install or args.cron_remove or args.cron_status:
        raise SystemExit(_handle_cron_cli(state, args))

    multiprocessing.freeze_support()
    _sync_startup_state(state)
    port = _pick_port()
    thread = threading.Thread(target=start_server, args=(state, port), daemon=True)
    thread.start()
    _start_webview(state, port)
