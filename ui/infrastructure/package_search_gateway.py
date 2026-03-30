import concurrent.futures
import re

import requests

import app_config as cfg


class PackageSearchGateway:
    def search(self, query, urlquote_fn):
        hb_results, ch_results, apt_results = [], [], []

        def _hb_formula():
            query_lower = query.lower()
            exact_found = False
            try:
                response = requests.get(
                    f'https://formulae.brew.sh/api/formula/{urlquote_fn(query)}.json',
                    timeout=cfg.ROUTE_PKG_HB_EXACT_TIMEOUT_SEC,
                )
                if response.status_code == 200:
                    data = response.json()
                    hb_results.append({'name': data.get('name', query), 'desc': data.get('desc', ''), 'htype': 'brew'})
                    exact_found = True
            except Exception:
                pass

            if exact_found:
                return

            try:
                response = requests.get('https://formulae.brew.sh/api/formula.json', timeout=cfg.ROUTE_PKG_HB_INDEX_TIMEOUT_SEC)
                if response.status_code == 200 and isinstance(response.json(), list):
                    added = 0
                    for item in response.json():
                        name = item.get('name', '')
                        desc = item.get('desc', '') or ''
                        if not name:
                            continue
                        if query_lower in name.lower() or query_lower in desc.lower():
                            hb_results.append({'name': name, 'desc': desc, 'htype': 'brew'})
                            added += 1
                            if added >= cfg.ROUTE_PKG_HB_RESULT_LIMIT:
                                break
            except Exception:
                pass

        def _hb_cask():
            query_lower = query.lower()
            exact_found = False
            try:
                response = requests.get(
                    f'https://formulae.brew.sh/api/cask/{urlquote_fn(query)}.json',
                    timeout=cfg.ROUTE_PKG_HB_EXACT_TIMEOUT_SEC,
                )
                if response.status_code == 200:
                    data = response.json()
                    name = data.get('token') or query
                    raw_names = data.get('name', [])
                    desc = data.get('desc', '') or (raw_names[0] if isinstance(raw_names, list) and raw_names else '')
                    hb_results.append({'name': name, 'desc': desc, 'htype': 'cask'})
                    exact_found = True
            except Exception:
                pass

            if exact_found:
                return

            try:
                response = requests.get('https://formulae.brew.sh/api/cask.json', timeout=cfg.ROUTE_PKG_HB_INDEX_TIMEOUT_SEC)
                if response.status_code == 200 and isinstance(response.json(), list):
                    added = 0
                    for item in response.json():
                        token = item.get('token', '') or ''
                        names = item.get('name', [])
                        desc = item.get('desc', '') or ''
                        first_name = names[0] if isinstance(names, list) and names else ''
                        haystack = ' '.join([token, first_name, desc]).lower()
                        if not token:
                            continue
                        if query_lower in haystack:
                            hb_results.append({'name': token, 'desc': desc or first_name, 'htype': 'cask'})
                            added += 1
                            if added >= cfg.ROUTE_PKG_HB_RESULT_LIMIT:
                                break
            except Exception:
                pass

        def _chocolatey():
            try:
                url = f'https://community.chocolatey.org/packages?q={urlquote_fn(query)}'
                response = requests.get(url, timeout=cfg.ROUTE_PKG_CHOCOLATEY_TIMEOUT_SEC, headers={'User-Agent': 'Mozilla/5.0'})
                if response.status_code == 200:
                    ids = re.findall(r'data-package-id="([^"]+)"', response.text)
                    seen = set()
                    for package_id in ids[: cfg.ROUTE_PKG_CHOCOLATEY_RESULT_LIMIT]:
                        if package_id.lower() not in seen:
                            seen.add(package_id.lower())
                            ch_results.append({'name': package_id, 'desc': ''})
            except Exception:
                pass

        def _apt():
            try:
                url = (
                    f'https://packages.debian.org/search?'
                    f'keywords={urlquote_fn(query)}&searchon=names&suite=stable&section=all'
                )
                response = requests.get(url, timeout=cfg.ROUTE_PKG_APT_TIMEOUT_SEC)
                if response.status_code == 200:
                    packages = re.findall(r'<h3>\s*Package\s+([^\s<]+)\s*</h3>', response.text)
                    seen = set()
                    for package in packages[: cfg.ROUTE_PKG_APT_RESULT_LIMIT]:
                        if package not in seen:
                            seen.add(package)
                            apt_results.append({'name': package})
            except Exception:
                pass

        with concurrent.futures.ThreadPoolExecutor(max_workers=cfg.ROUTE_PKG_SEARCH_WORKERS) as executor:
            concurrent.futures.wait(
                [executor.submit(fn) for fn in (_hb_formula, _hb_cask, _chocolatey, _apt)],
                timeout=cfg.ROUTE_PKG_SEARCH_WAIT_TIMEOUT_SEC,
            )

        merged = {}
        for item in hb_results:
            key = item['name'].lower()
            if key not in merged:
                merged[key] = {
                    'name': item['name'],
                    'desc': item['desc'],
                    'homebrew': True,
                    'homebrew_type': item['htype'],
                    'chocolatey': False,
                    'apt': False,
                    'mac': item['name'],
                    'win': '-',
                    'linux': '-',
                }
            else:
                merged[key]['homebrew'] = True
                merged[key]['homebrew_type'] = item['htype']
                merged[key]['mac'] = item['name']
        for item in ch_results:
            key = item['name'].lower()
            if key not in merged:
                merged[key] = {
                    'name': item['name'],
                    'desc': item.get('desc', ''),
                    'homebrew': False,
                    'homebrew_type': None,
                    'chocolatey': True,
                    'apt': False,
                    'mac': '-',
                    'win': item['name'],
                    'linux': '-',
                }
            else:
                merged[key]['chocolatey'] = True
                merged[key]['win'] = item['name']
                if not merged[key]['desc']:
                    merged[key]['desc'] = item.get('desc', '')
        for item in apt_results:
            key = item['name'].lower()
            if key not in merged:
                merged[key] = {
                    'name': item['name'],
                    'desc': '',
                    'homebrew': False,
                    'homebrew_type': None,
                    'chocolatey': False,
                    'apt': True,
                    'mac': '-',
                    'win': '-',
                    'linux': item['name'],
                }
            else:
                merged[key]['apt'] = True
                merged[key]['linux'] = item['name']

        return {'query': query, 'results': list(merged.values())}
