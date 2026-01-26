from flask import Flask, jsonify, request, render_template, send_from_directory
from dotenv import load_dotenv, set_key
import os
import requests
from pathlib import Path
import multiprocessing
import socket
import webview
import subprocess
import threading
import sys
import re

BASE_DIR = Path(__file__).resolve().parents[1]
ENV_LOCAL = BASE_DIR / '.env.local'
ENV_EXAMPLE = BASE_DIR / '.env.example'
PACKAGES_CONF = BASE_DIR / 'src' / 'packages.conf'

app = Flask(__name__, static_folder='static', template_folder='templates')

# Load environment
def load_env_dict():
    # 1. Parse example to get keys and comments
    schema = []
    if ENV_EXAMPLE.exists():
        with ENV_EXAMPLE.open() as f:
            last_comment = ""
            for line in f:
                line = line.strip()
                if not line:
                     last_comment = ""
                     continue
                if line.startswith('#'):
                     last_comment += line.lstrip('#').strip() + " "
                     continue
                if '=' in line:
                     k, v = line.split('=', 1)
                     schema.append({'key': k.strip(), 'default': v.strip().strip('"'), 'desc': last_comment.strip()})
                     last_comment = ""
    
    # 2. Load actual values from .env.local
    current = {}
    if ENV_LOCAL.exists():
        load_dotenv(dotenv_path=ENV_LOCAL, override=False)
        with ENV_LOCAL.open() as f:
            for line in f:
                line=line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k,v=line.split('=',1)
                current[k.strip()]=v.strip().strip('"')

    # Merge
    final_list = []
    seen = set()
    # Add items from schema
    for item in schema:
        key = item['key']
        val = current.get(key, item['default'])
        final_list.append({'key': key, 'value': val, 'desc': item['desc']})
        seen.add(key)
    
    # Add extra items from current that were not in schema
    for k, v in current.items():
        if k not in seen:
            final_list.append({'key': k, 'value': v, 'desc': 'Custom setting'})
            
    return final_list

# Packages parsing
def read_packages():
    packages = []
    if PACKAGES_CONF.exists():
        with PACKAGES_CONF.open() as f:
            for line in f:
                line=line.strip()
                if not line or line.startswith('#'):
                    continue
                parts=line.split('|')
                # expected format: type|mac|win|desc
                if len(parts) < 4:
                    continue
                pkg = {
                    'type': parts[0],
                    'mac': parts[1],
                    'win': parts[2],
                    'desc': parts[3]
                }
                packages.append(pkg)
    return packages

# Simple availability checks
def check_homebrew(app):
    url_formula = f"https://formulae.brew.sh/api/formula/{app}.json"
    url_cask = f"https://formulae.brew.sh/api/cask/{app}.json"
    try:
        r = requests.get(url_formula, timeout=5)
        if r.status_code == 200 and 'name' in r.text:
            return True
    except Exception:
        pass
    try:
        r = requests.get(url_cask, timeout=5)
        if r.status_code == 200 and 'token' in r.text:
            return True
    except Exception:
        pass
    return False

def check_chocolatey(app):
    # Query Chocolatey OData endpoint
    q = f"https://community.chocolatey.org/api/v2/Packages()?%24filter=tolower(Id)%20eq%20tolower(%27{app}%27)&%24select=Id"
    try:
        r = requests.get(q, timeout=6)
        if r.status_code == 200 and app.lower() in r.text.lower():
            return True
    except Exception:
        pass
    return False

def check_debian(app):
    try:
        url = f"https://packages.debian.org/search?keywords={app}&searchon=names&suite=stable&section=all"
        r = requests.get(url, timeout=6)
        if r.status_code == 200 and 'Exact hits' in r.text:
            return True
    except Exception:
        pass
    return False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/env', methods=['GET','POST'])
def api_env():
    if request.method == 'GET':
        return jsonify(load_env_dict())
    data = request.json or {}
    # write keys back to .env.local
    if not ENV_LOCAL.exists():
        ENV_LOCAL.write_text('')
    for k,v in data.items():
        set_key(str(ENV_LOCAL), k, str(v))
    return jsonify({'status':'ok'})


@app.route('/api/env/exists')
def api_env_exists():
    try:
        return jsonify({'exists': ENV_LOCAL.exists()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/env/init', methods=['POST'])
def api_env_init():
    try:
        # If an example file exists, copy it as a starting point
        if ENV_EXAMPLE.exists():
            ENV_LOCAL.write_text(ENV_EXAMPLE.read_text())
        else:
            # create an empty .env.local
            ENV_LOCAL.write_text('')
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/packages')
def api_packages():
    pkgs=read_packages()
    return jsonify(pkgs)

@app.route('/api/check')
def api_check():
    appname = request.args.get('app')
    target = request.args.get('target','auto')
    if not appname:
        return jsonify({'error':'missing app parameter'}),400
    result = {'app':appname,'available':False,'sources':{}}
    # check homebrew
    try:
        hb = check_homebrew(appname)
        result['sources']['homebrew']=hb
        if hb:
            result['available']=True
    except Exception:
        result['sources']['homebrew']=False
    # check chocolatey
    try:
        ch = check_chocolatey(appname)
        result['sources']['chocolatey']=ch
        if ch:
            result['available']=True
    except Exception:
        result['sources']['chocolatey']=False
    # check debian
    try:
        de = check_debian(appname)
        result['sources']['debian']=de
        if de:
            result['available']=True
    except Exception:
        result['sources']['debian']=False
    return jsonify(result)

@app.route('/api/icon')
def api_icon():
    name = request.args.get('name')
    if not name or name == '-': 
        return jsonify({'url': ''})

    # Default fallback
    fallback = f"https://ui-avatars.com/api/?name={name}&background=e1e1e1&color=333&size=64&font-size=0.4&length=2"
    
    # 1. Try Homebrew Cask (best for icons)
    try:
        r = requests.get(f"https://formulae.brew.sh/api/cask/{name}.json", timeout=1.5)
        if r.status_code == 200:
            hp = r.json().get('homepage')
            if hp:
                return jsonify({'url': f"https://www.google.com/s2/favicons?domain={hp}&sz=64"})
    except:
        pass
    
    # 2. Try Chocolatey
    try:
        url = f"https://community.chocolatey.org/api/v2/Packages()?$filter=tolower(Id) eq '{name.lower()}'&$select=IconUrl"
        r = requests.get(url, timeout=1.5)
        if r.status_code == 200:
            m = re.search(r'<d:IconUrl>(.+?)</d:IconUrl>', r.text)
            if m:
                # Some choco icons are broken or http, assume https for safety if possible or just return
                return jsonify({'url': m.group(1)})
    except:
        pass

    return jsonify({'url': fallback})

@app.route('/api/search')
def api_search():
    q = request.args.get('q')
    store = request.args.get('store','all')
    if not q:
        return jsonify({'error':'missing q parameter'}),400
    out = {'query':q,'store':store,'results':[]}
    if store in ('all','homebrew'):
        try:
            r = requests.get(f"https://formulae.brew.sh/api/search?q={q}", timeout=6)
            if r.status_code==200:
                out['results'].append({'store':'homebrew','data':r.json()})
        except Exception:
            pass
    if store in ('all','chocolatey'):
        try:
            r = requests.get(f"https://community.chocolatey.org/packages?search={q}", timeout=6)
            out['results'].append({'store':'chocolatey','data':r.text})
        except Exception:
            pass
    if store in ('all','debian'):
        try:
            r = requests.get(f"https://packages.debian.org/search?keywords={q}&searchon=names&suite=stable&section=all", timeout=6)
            out['results'].append({'store':'debian','data':r.text})
        except Exception:
            pass
    return jsonify(out)

# static files
@app.route('/static/<path:p>')
def static_files(p):
    return send_from_directory(os.path.join(os.path.dirname(__file__),'static'), p)

@app.route('/api/action/update', methods=['POST'])
def api_action_update():
    # Run bash src/update.sh
    script = BASE_DIR / 'src' / 'update.sh'
    if not script.exists():
        return jsonify({'error':'update script not found'}), 500
    try:
        # Run in background or wait? Wait for now to show status
        # Note: on Windows this might fail if bash is not in PATH.
        cmd = ['bash', str(script)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        return jsonify({'stdout': res.stdout, 'stderr': res.stderr, 'code': res.returncode})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/action/install', methods=['POST'])
def api_action_install():
    data = request.json or {}
    app_name = data.get('app')
    if not app_name:
        return jsonify({'error':'missing app name'}), 400
    
    script = BASE_DIR / 'src' / 'app.sh'
    try:
        cmd = ['bash', str(script), 'install', app_name]
        res = subprocess.run(cmd, capture_output=True, text=True)
        return jsonify({'stdout': res.stdout, 'stderr': res.stderr, 'code': res.returncode})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/action/import-installed', methods=['POST'])
def api_action_import_installed():
    # Run bash src/import_installed.sh
    def find_script(name):
        candidates = []
        # repo-relative (dev mode)
        candidates.append(BASE_DIR / 'src' / name)
        # current working dir
        candidates.append(Path.cwd() / 'src' / name)
        # next to the executable (one-dir builds)
        candidates.append(Path(sys.executable).parent / 'src' / name)
        # PyInstaller onefile unpack dir
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            candidates.append(Path(meipass) / 'src' / name)

        found = None
        checked = []
        for c in candidates:
            checked.append(str(c))
            if c.exists():
                found = c
                break
        return found, checked

    script_name = 'import_installed.sh'
    script, checked = find_script(script_name)
    if not script:
        return jsonify({'error': f"{script_name} script not found", 'checked': checked}), 500

    try:
        cmd = ['bash', str(script)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        return jsonify({'stdout': res.stdout, 'stderr': res.stderr, 'code': res.returncode, 'used': str(script)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/action/wifi-export', methods=['POST'])
def api_action_wifi_export():
    data = request.json or {}
    db_path = data.get('db')
    password = data.get('password')
    
    if not db_path:
        # try loading from env
        env = load_env_dict()
        db_path = env.get('WIFI_KDBX_DB')
    
    if not db_path:
         return jsonify({'error':'No DB path provided and WIFI_KDBX_DB not set'}), 400
    if not password:
         return jsonify({'error':'Password is required'}), 400

    script = BASE_DIR / 'src' / 'wifi_from_keychain.sh'
    if not script.exists():
         return jsonify({'error':'wifi_from_keychain.sh script not found'}), 500

    env = os.environ.copy()
    env['KEEPASS_DB_PASS'] = password
    
    # We pass the DB path as argument
    cmd = ['bash', str(script), '--db', db_path]
    
    try:
        # Run process
        res = subprocess.run(cmd, env=env, capture_output=True, text=True)
        return jsonify({'stdout': res.stdout, 'stderr': res.stderr, 'code': res.returncode})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def start_server(port):
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)

if __name__=='__main__':
    multiprocessing.freeze_support()
    
    port = int(os.environ.get('PORT', 5000))
    if is_port_in_use(port):
        # In --noconsole mode, avoid print() as it might crash on Windows
        # print(f" * Port {port} is in use. Trying to find another port...")
        if port == 5000:
            port = 5001
        while is_port_in_use(port):
            port += 1
            if port > 5010: # Limit searches
                break
    
    # Start Flask in a thread
    t = threading.Thread(target=start_server, args=(port,), daemon=True)
    t.start()

    # Provide a small JS API to open native file/folder dialogs when running
    # inside the pywebview window. Fall back to prompt in browsers.
    class FileDialogApi:
        def __init__(self):
            # Window will be set after creation
            self.window = None

        def open_file(self, title="Select file"):
            try:
                # Use pywebview native dialog if available
                if self.window:
                    res = webview.create_file_dialog(self.window, webview.OPEN_DIALOG)
                    # pywebview returns a list for multiple selections
                    if isinstance(res, (list, tuple)):
                        return res[0] if res else ""
                    return res or ""
            except Exception:
                pass
            return ""

        def open_dir(self, title="Select folder"):
            try:
                if self.window:
                    res = webview.create_file_dialog(self.window, webview.FOLDER_DIALOG)
                    if isinstance(res, (list, tuple)):
                        return res[0] if res else ""
                    return res or ""
            except Exception:
                pass
            return ""

    api = FileDialogApi()

    # Create webview window and expose the API to JS via `window.pywebview.api`
    try:
        window = webview.create_window('ok_computer', f'http://localhost:{port}', js_api=api)
        api.window = window
    except TypeError:
        # Older pywebview versions or contexts where js_api isn't supported
        window = webview.create_window('ok_computer', f'http://localhost:{port}')

    webview.start()
