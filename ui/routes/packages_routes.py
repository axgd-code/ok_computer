import re

import requests
from flask import Blueprint, jsonify, request
import app_config as cfg
from api import dto


def create_packages_blueprint(state):
    bp = Blueprint('packages_routes', __name__)

    @bp.route('/api/packages')
    def api_packages():
        try:
            include_availability = request.args.get('withAvailability', '0') == '1'
            result = state.USE_CASES.packages.list_packages(include_availability=include_availability)
            return dto.success(result.payload, result.status)
        except Exception as exc:
            return dto.from_exception(exc)

    @bp.route('/api/check')
    def api_check():
        try:
            result = state.USE_CASES.packages.check_package(request.args.get('app'))
            return dto.success(result.payload, result.status)
        except Exception as exc:
            return dto.from_exception(exc)

    @bp.route('/api/icon')
    def api_icon():
        name = request.args.get('name')
        if not name or name == '-':
            return jsonify({'url': ''})

        fallback = f'https://ui-avatars.com/api/?name={name}&background=e1e1e1&color=333&size=64&font-size=0.4&length=2'
        try:
            response = requests.get(f'https://formulae.brew.sh/api/cask/{name}.json', timeout=cfg.ROUTE_PKG_ICON_TIMEOUT_SEC)
            if response.status_code == 200:
                homepage = response.json().get('homepage')
                if homepage:
                    return jsonify({'url': f'https://www.google.com/s2/favicons?domain={homepage}&sz=64'})
        except Exception:
            pass

        try:
            url = f"https://community.chocolatey.org/api/v2/Packages()?$filter=tolower(Id) eq '{name.lower()}'&$select=IconUrl"
            response = requests.get(url, timeout=cfg.ROUTE_PKG_ICON_TIMEOUT_SEC)
            if response.status_code == 200:
                match = re.search(r'<d:IconUrl>(.+?)</d:IconUrl>', response.text)
                if match:
                    return jsonify({'url': match.group(1)})
        except Exception:
            pass

        return jsonify({'url': fallback})

    @bp.route('/api/search')
    def api_search():
        try:
            result = state.USE_CASES.packages.search_packages(request.args.get('q', '').strip())
            return dto.success(result.payload, result.status)
        except Exception as exc:
            return dto.from_exception(exc)

    @bp.route('/api/packages/add', methods=['POST'])
    def api_packages_add():
        data = request.json or {}
        allowed_types = {'brew', 'cask', 'tap', 'mas', 'pip', 'npm', 'apt'}

        def _clean(value):
            return (value or '').replace('|', '').replace('\n', '').replace('\r', '').strip()

        pkg_type = _clean(data.get('type')) or 'brew'
        if pkg_type not in allowed_types:
            pkg_type = 'brew'
        mac = _clean(data.get('mac')) or '-'
        win = _clean(data.get('win')) or '-'
        desc = _clean(data.get('desc'))

        if mac == '-' and win == '-':
            return jsonify({'error': 'At least mac or win name is required'}), 400

        conf_path = state.find_conf_file('packages.conf') or state._config_target_path('packages.conf')
        if not conf_path:
            return jsonify({'error': 'packages.conf not found'}), 500

        conf_path.parent.mkdir(parents=True, exist_ok=True)
        if not conf_path.exists():
            conf_path.write_text('')

        with conf_path.open() as handle:
            content = handle.read()
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            parts = stripped.split('|')
            if len(parts) >= 3:
                if mac != '-' and parts[1].strip() == mac:
                    return jsonify({'error': f"'{mac}' is already in packages.conf"}), 409
                if win != '-' and parts[2].strip() == win:
                    return jsonify({'error': f"'{win}' is already in packages.conf"}), 409

        new_line = f'{pkg_type}|{mac}|{win}|{desc}\n'
        with conf_path.open('a') as handle:
            handle.write(new_line)
        state.app.logger.info('Package added to %s: %s', conf_path, new_line.strip())
        return jsonify({'status': 'ok', 'line': new_line.strip(), 'path': str(conf_path)})

    @bp.route('/api/packages/update', methods=['POST'])
    def api_packages_update():
        try:
            data = request.json or {}
            result = state.USE_CASES.packages.update_package((data.get('app') or '').strip())
            return dto.success(result.payload, result.status)
        except Exception as exc:
            return dto.from_exception(exc)

    @bp.route('/api/packages/remove', methods=['POST'])
    def api_packages_remove():
        try:
            data = request.json or {}
            result = state.USE_CASES.packages.remove_package(
                (data.get('app') or '').strip(),
                run_uninstall=bool(data.get('runUninstall', True)),
            )
            return dto.success(result.payload, result.status)
        except Exception as exc:
            return dto.from_exception(exc)

    return bp
