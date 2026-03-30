import base64
import concurrent.futures
import json
import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote as _urlquote

import requests
import app_config as cfg


def parse_extensions_conf(find_conf_file_fn, base_dir):
    ext_file = find_conf_file_fn('extensions.conf') or (base_dir / 'src' / 'extensions.conf')
    items = []

    def _chrome_url(ext_id):
        safe = (ext_id or '').strip()
        return f'https://chrome.google.com/webstore/detail/{safe}' if safe else ''

    def _firefox_url(slug_or_id):
        safe = (slug_or_id or '').strip()
        return f'https://addons.mozilla.org/firefox/addon/{safe}/' if safe else ''

    if not ext_file.exists():
        return items
    with ext_file.open() as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('|')
            if parts[0] == 'all' and len(parts) >= 4:
                chrome_id = parts[1].strip()
                firefox_id = parts[2].strip()
                chrome_url = _chrome_url(chrome_id)
                firefox_url = _firefox_url(firefox_id)
                items.append({
                    'mode': 'all',
                    'chrome': chrome_id,
                    'firefox': firefox_id,
                    'desc': parts[3].strip(),
                    'raw': line,
                    'chrome_url': chrome_url,
                    'firefox_url': firefox_url,
                    'official_urls': [u for u in (chrome_url, firefox_url) if u],
                })
            elif parts[0] in ('chrome', 'firefox', 'arc') and len(parts) >= 3:
                mode = parts[0]
                ext_id = parts[1].strip()
                page_url = _chrome_url(ext_id) if mode in ('chrome', 'arc') else _firefox_url(ext_id)
                items.append({
                    'mode': mode,
                    'id': ext_id,
                    'desc': parts[2].strip(),
                    'raw': line,
                    'official_url': page_url,
                    'official_urls': [page_url] if page_url else [],
                })
            else:
                items.append({'mode': 'unknown', 'raw': line})
    return items


def scan_chrome_family_extensions():
    """Scan common Chrome/Chromium/Brave extension folders."""
    results = []
    home = Path.home()
    candidates = []
    from platform import system
    sysname = system().lower()
    if 'darwin' in sysname:
        candidates = [
            home / 'Library' / 'Application Support' / 'Google' / 'Chrome',
            home / 'Library' / 'Application Support' / 'Chromium',
            home / 'Library' / 'Application Support' / 'BraveSoftware' / 'Brave-Browser',
        ]
    elif 'linux' in sysname:
        candidates = [
            home / '.config' / 'google-chrome',
            home / '.config' / 'chromium',
            home / '.config' / 'BraveSoftware' / 'Brave-Browser',
        ]
    elif 'windows' in sysname or sysname.startswith('win'):
        local = Path(os.environ.get('LOCALAPPDATA', home / 'AppData' / 'Local'))
        candidates = [
            local / 'Google' / 'Chrome' / 'User Data',
            local / 'Chromium' / 'User Data',
            local / 'BraveSoftware' / 'Brave-Browser' / 'User Data',
        ]
    else:
        candidates = [home]

    def _to_data_url(path_obj):
        try:
            suffix = path_obj.suffix.lower()
            if suffix == '.svg':
                mime = 'image/svg+xml'
            elif suffix == '.webp':
                mime = 'image/webp'
            elif suffix in ('.jpg', '.jpeg'):
                mime = 'image/jpeg'
            elif suffix == '.gif':
                mime = 'image/gif'
            else:
                mime = 'image/png'
            raw = path_obj.read_bytes()
            return f'data:{mime};base64,{base64.b64encode(raw).decode("ascii")}'
        except Exception:
            return ''

    def _pick_manifest_icon(manifest_obj, manifest_path):
        try:
            icons = manifest_obj.get('icons') if isinstance(manifest_obj, dict) else None
            if not isinstance(icons, dict) or not icons:
                return ''

            chosen = None
            keys = sorted(icons.keys(), key=lambda k: int(k) if str(k).isdigit() else 0, reverse=True)
            for k in keys:
                v = icons.get(k)
                if isinstance(v, str) and v.strip():
                    chosen = v.strip()
                    break
            if not chosen:
                return ''

            icon_path = (manifest_path.parent / chosen).resolve()
            if not icon_path.exists() or not icon_path.is_file():
                return ''
            return _to_data_url(icon_path)
        except Exception:
            return ''

    for base in candidates:
        ext_root = base / 'Default' / 'Extensions'
        if not ext_root.exists() and base.exists():
            for profile in base.iterdir():
                candidate = profile / 'Extensions'
                if candidate.exists():
                    ext_root = candidate
                    break
        if not ext_root.exists():
            continue
        for ext_id_dir in ext_root.iterdir():
            if not ext_id_dir.is_dir():
                continue
            try:
                versions = [p for p in ext_id_dir.iterdir() if p.is_dir()]
                if not versions:
                    manifest = ext_id_dir / 'manifest.json'
                else:
                    versions_sorted = sorted(versions, key=lambda p: p.name, reverse=True)
                    manifest = versions_sorted[0] / 'manifest.json'
                if manifest and manifest.exists():
                    with manifest.open() as fh:
                        m = json.load(fh)
                        raw_name = m.get('name') or m.get('short_name') or ''
                        raw_desc = m.get('description') or ''

                        def resolve_msg_token(token_key):
                            try:
                                default_loc = m.get('default_locale')
                                if default_loc:
                                    loc_file = ext_id_dir / '_locales' / default_loc / 'messages.json'
                                    if loc_file.exists():
                                        with loc_file.open() as lf:
                                            lm = json.load(lf)
                                            if token_key in lm and 'message' in lm[token_key]:
                                                return lm[token_key]['message']
                                loc_dir = ext_id_dir / '_locales'
                                if loc_dir.exists():
                                    for loc_sub in loc_dir.iterdir():
                                        cand = loc_sub / 'messages.json'
                                        if cand.exists():
                                            try:
                                                with cand.open() as cf:
                                                    cm = json.load(cf)
                                                    if token_key in cm and 'message' in cm[token_key]:
                                                        return cm[token_key]['message']
                                            except Exception:
                                                continue
                            except Exception:
                                pass
                            return None

                        def resolve_field(value):
                            if not isinstance(value, str):
                                return value
                            out = value
                            import re
                            for mtoken in re.findall(r'__MSG_([A-Za-z0-9_]+)__', value):
                                rep = resolve_msg_token(mtoken)
                                if rep:
                                    out = out.replace(f'__MSG_{mtoken}__', rep)
                            return out

                        resolved_name = resolve_field(raw_name)
                        resolved_desc = resolve_field(raw_desc)
                        icon_url = _pick_manifest_icon(m, manifest)
                        official_url = f'https://chrome.google.com/webstore/detail/{ext_id_dir.name}'
                        results.append({
                            'browser': 'chrome-like',
                            'id': ext_id_dir.name,
                            'name': resolved_name,
                            'description': resolved_desc,
                            'path': str(ext_id_dir),
                            'official_url': official_url,
                            'icon_url': icon_url,
                        })
            except Exception:
                continue
    return results


def _normalize_text(value):
    if isinstance(value, str):
        return value.strip().lower()
    if isinstance(value, dict):
        for key in ('en-US', 'en'):
            if isinstance(value.get(key), str):
                return value.get(key).strip().lower()
        for v in value.values():
            if isinstance(v, str):
                return v.strip().lower()
        return ''
    if value is None:
        return ''
    return str(value).strip().lower()


def _firefox_icon_from_payload(payload):
    if not isinstance(payload, dict):
        return ''
    icon_url = payload.get('icon_url') or payload.get('icon') or ''
    if icon_url:
        return icon_url
    icons = payload.get('icons')
    if isinstance(icons, dict):
        for size in ('64', '32', '128'):
            if icons.get(size):
                return icons.get(size)
        for size in sorted(icons.keys(), key=lambda s: int(s) if str(s).isdigit() else 0, reverse=True):
            candidate = icons.get(size)
            if candidate:
                return candidate
    return ''


@lru_cache(maxsize=512)
def _fetch_firefox_addon_payload(identifier):
    safe = (identifier or '').strip()
    if not safe:
        return {}
    try:
        url = f'https://addons.mozilla.org/api/v5/addons/addon/{_urlquote(safe)}/'
        resp = requests.get(url, timeout=cfg.FIREFOX_API_TIMEOUT_SEC)
        if resp.status_code == 200:
            data = resp.json()
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


@lru_cache(maxsize=512)
def _search_firefox_addons(query):
    q = (query or '').strip()
    if not q:
        return []
    try:
        resp = requests.get(
            'https://addons.mozilla.org/api/v5/addons/search/',
            params={'q': q, 'limit': cfg.FIREFOX_SEARCH_LIMIT},
            timeout=cfg.FIREFOX_API_TIMEOUT_SEC,
        )
        if resp.status_code == 200:
            data = resp.json()
            results = data.get('results', []) if isinstance(data, dict) else []
            return results if isinstance(results, list) else []
    except Exception:
        pass
    return []


def _pick_firefox_search_result(addon_id, addon_name, results):
    if not isinstance(results, list) or not results:
        return {}
    norm_id = _normalize_text(addon_id)
    norm_name = _normalize_text(addon_name)

    for item in results:
        if _normalize_text(item.get('guid')) == norm_id:
            return item

    for item in results:
        if _normalize_text(item.get('slug')) == norm_id:
            return item

    for item in results:
        if _normalize_text(item.get('name')) == norm_name:
            return item

    for item in results:
        item_name = _normalize_text(item.get('name'))
        if norm_name and (norm_name in item_name or item_name in norm_name):
            return item

    return results[0] if results else {}


def _resolve_firefox_addon_details(addon_id, addon_name):
    safe_id = (addon_id or '').strip()

    payload = _fetch_firefox_addon_payload(safe_id)
    if payload:
        slug = payload.get('slug') or payload.get('guid') or safe_id
        return {
            'slug': slug,
            'icon_url': _firefox_icon_from_payload(payload),
            'official_url': f'https://addons.mozilla.org/firefox/addon/{slug}/' if slug else '',
        }

    query = (addon_name or '').strip() or safe_id
    results = _search_firefox_addons(query)
    match = _pick_firefox_search_result(safe_id, addon_name, results)
    if isinstance(match, dict) and match:
        slug = match.get('slug') or match.get('guid') or safe_id
        details_payload = _fetch_firefox_addon_payload(slug)
        payload = details_payload if details_payload else match
        return {
            'slug': slug,
            'icon_url': _firefox_icon_from_payload(payload),
            'official_url': f'https://addons.mozilla.org/firefox/addon/{slug}/' if slug else '',
        }

    return {
        'slug': safe_id,
        'icon_url': '',
        'official_url': f'https://addons.mozilla.org/firefox/addon/{safe_id}/' if safe_id else '',
    }


def _resolve_firefox_addon_slug(addon_id, addon_name, timeout=1):
    return _resolve_firefox_addon_details(addon_id, addon_name).get('slug') or (addon_id or '')


def _fetch_firefox_icon_from_mozilla(addon_slug, timeout=2):
    return _resolve_firefox_addon_details(addon_slug, '').get('icon_url', '')


def scan_firefox_extensions():
    results = []
    home = Path.home()
    profiles_root = home / 'Library' / 'Application Support' / 'Firefox' / 'Profiles'
    if not profiles_root.exists():
        return results

    addon_list = []
    for profile in profiles_root.iterdir():
        if not profile.is_dir():
            continue
        ext_json = profile / 'extensions.json'
        if not ext_json.exists():
            continue
        try:
            with ext_json.open() as fh:
                j = json.load(fh)
                addons = j.get('addons', [])
                for a in addons:
                    if a.get('type') == 'theme':
                        continue
                    addon_id = a.get('id')
                    name = a.get('defaultLocale', {}).get('name') or a.get('name') or ''
                    addon_list.append({
                        'addon_id': addon_id,
                        'name': name,
                        'profile': str(profile)
                    })
        except Exception:
            continue

    def _resolve_addon(item):
        addon_id = item['addon_id']
        name = item['name']
        profile = item['profile']
        details = _resolve_firefox_addon_details(addon_id, name)
        return {
            'browser': 'firefox',
            'id': addon_id,
            'slug': details.get('slug') or addon_id,
            'name': name,
            'path': profile,
            'official_url': details.get('official_url', ''),
            'icon_url': details.get('icon_url', ''),
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=cfg.FIREFOX_SCAN_WORKERS) as executor:
        try:
            results = list(executor.map(_resolve_addon, addon_list, timeout=cfg.FIREFOX_SCAN_TIMEOUT_SEC))
        except Exception:
            results = [_resolve_addon(item) for item in addon_list]

    return results


def scan_local_extensions():
    out = []
    out.extend(scan_chrome_family_extensions())
    out.extend(scan_firefox_extensions())
    return out
