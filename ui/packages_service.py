import concurrent.futures
from pathlib import Path

import requests
import app_config as cfg


class PackagesService:
    def __init__(self, logger):
        self.logger = logger

    def read_packages(self, packages_conf, find_conf_file_fn):
        packages = []
        conf_path = Path(packages_conf) if Path(packages_conf).exists() else find_conf_file_fn('packages.conf')
        if not conf_path:
            conf_path = find_conf_file_fn('packages.conf.example')
        if conf_path and Path(conf_path).exists():
            self.logger.info('read_packages using: %s', conf_path)
            with Path(conf_path).open() as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split('|')
                    if len(parts) < 4:
                        continue
                    packages.append({
                        'type': parts[0],
                        'mac': parts[1],
                        'win': parts[2],
                        'desc': parts[3],
                    })
        else:
            self.logger.warning('read_packages: no packages.conf found')
        return packages

    def remove_package_from_conf(self, app_name, packages_conf, find_conf_file_fn):
        conf_path = Path(packages_conf) if Path(packages_conf).exists() else find_conf_file_fn('packages.conf')
        if not conf_path or not Path(conf_path).exists():
            return {'error': 'packages.conf not found'}

        original_lines = Path(conf_path).read_text().splitlines()
        kept = []
        removed = 0
        for raw in original_lines:
            line = raw.strip()
            if not line or line.startswith('#'):
                kept.append(raw)
                continue
            parts = line.split('|')
            if len(parts) < 3:
                kept.append(raw)
                continue
            mac = parts[1].strip()
            win = parts[2].strip()
            if app_name in (mac, win):
                removed += 1
                continue
            kept.append(raw)

        if removed > 0:
            out = '\n'.join(kept).rstrip('\n') + '\n'
            Path(conf_path).write_text(out)

        return {'removed_count': removed, 'path': str(conf_path)}

    def check_debian(self, app):
        try:
            url = f'https://packages.debian.org/search?keywords={app}&searchon=names&suite=stable&section=all'
            r = requests.get(url, timeout=cfg.PKG_DEBIAN_TIMEOUT_SEC)
            if r.status_code == 200 and 'Exact hits' in r.text:
                return True
        except Exception:
            pass
        return False

    def enrich_packages_with_availability(self, packages):
        pkgs = [dict(pkg) for pkg in packages]
        for pkg in pkgs:
            pkg['apt_available'] = False
            pkg['linux'] = '-'

        to_check = []
        for pkg in pkgs:
            base = pkg.get('mac') if pkg.get('mac') and pkg.get('mac') != '-' else pkg.get('win')
            if not base or base == '-':
                continue
            to_check.append((pkg, base))

        to_check = to_check[: min(len(to_check), cfg.PKG_ENRICH_MAX_ITEMS)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=cfg.PKG_ENRICH_WORKERS) as executor:
            future_map = {executor.submit(self.check_debian, base): pkg for pkg, base in to_check}
            for future in concurrent.futures.as_completed(future_map, timeout=cfg.PKG_ENRICH_COMPLETED_TIMEOUT_SEC):
                pkg = future_map.get(future)
                try:
                    apt_ok = future.result(timeout=cfg.PKG_ENRICH_RESULT_TIMEOUT_SEC)
                except Exception:
                    apt_ok = False
                if pkg:
                    base = pkg.get('mac') if pkg.get('mac') and pkg.get('mac') != '-' else pkg.get('win')
                    pkg['apt_available'] = bool(apt_ok)
                    pkg['linux'] = base if apt_ok else '-'
        return pkgs
