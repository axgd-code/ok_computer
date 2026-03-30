import json
import os
import shutil
from pathlib import Path

import requests


def check_homebrew(app):
    url_formula = f'https://formulae.brew.sh/api/formula/{app}.json'
    url_cask = f'https://formulae.brew.sh/api/cask/{app}.json'
    try:
        response = requests.get(url_formula, timeout=5)
        if response.status_code == 200 and 'name' in response.text:
            return True
    except Exception:
        pass
    try:
        response = requests.get(url_cask, timeout=5)
        if response.status_code == 200 and 'token' in response.text:
            return True
    except Exception:
        pass
    return False


def check_chocolatey(app):
    query = f"https://community.chocolatey.org/api/v2/Packages()?%24filter=tolower(Id)%20eq%20tolower(%27{app}%27)&%24select=Id"
    try:
        response = requests.get(query, timeout=6)
        if response.status_code == 200 and app.lower() in response.text.lower():
            return True
    except Exception:
        pass
    return False


def uninstall_chrome_extension(ext_id):
    home = Path.home()
    from platform import system

    sysname = system().lower()
    candidates = []
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

    for base in candidates:
        ext_dir = base / 'Default' / 'Extensions' / ext_id
        if ext_dir.exists():
            shutil.rmtree(ext_dir, ignore_errors=True)
            if not ext_dir.exists():
                return {'status': 'ok', 'message': f'Extension {ext_id} uninstalled', 'removed_from': str(base)}

        if base.exists():
            for profile in base.iterdir():
                if profile.is_dir() and profile.name != 'Default':
                    ext_dir = profile / 'Extensions' / ext_id
                    if ext_dir.exists():
                        shutil.rmtree(ext_dir, ignore_errors=True)
                        if not ext_dir.exists():
                            return {
                                'status': 'ok',
                                'message': f'Extension {ext_id} uninstalled',
                                'removed_from': str(base / profile.name),
                            }

    return {'status': 'error', 'message': f'Extension {ext_id} not found or could not be removed'}


def uninstall_firefox_extension(addon_id):
    home = Path.home()
    profiles_root = home / 'Library' / 'Application Support' / 'Firefox' / 'Profiles'
    if not profiles_root.exists():
        return {'status': 'error', 'message': 'Firefox profiles not found'}

    for profile in profiles_root.iterdir():
        if not profile.is_dir():
            continue
        ext_json = profile / 'extensions.json'
        if not ext_json.exists():
            continue

        try:
            with ext_json.open() as fh:
                payload = json.load(fh)
            addons = payload.get('addons', [])
            original_count = len(addons)
            addons = [item for item in addons if item.get('id') != addon_id]
            if len(addons) < original_count:
                payload['addons'] = addons
                with ext_json.open('w') as fh:
                    json.dump(payload, fh, indent=2)
                ext_dir = profile / 'extensions' / addon_id
                if ext_dir.exists():
                    shutil.rmtree(ext_dir, ignore_errors=True)
                return {'status': 'ok', 'message': f'Extension {addon_id} uninstalled', 'removed_from': str(profile)}
        except Exception as exc:
            return {'status': 'error', 'message': f'Failed to uninstall from profile {profile.name}: {exc}'}

    return {'status': 'error', 'message': f'Extension {addon_id} not found in any Firefox profile'}


def uninstall_extension(browser, ext_id):
    if browser in ('chrome', 'chromium', 'brave', 'chrome-like'):
        return uninstall_chrome_extension(ext_id)
    if browser == 'firefox':
        return uninstall_firefox_extension(ext_id)
    return {'status': 'error', 'message': f'Unknown browser type: {browser}'}
