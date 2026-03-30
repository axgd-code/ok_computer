import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


def set_exec_if_possible(path_obj):
    try:
        mode = path_obj.stat().st_mode
        path_obj.chmod(mode | 0o111)
    except Exception:
        pass


def copy_if_newer(src, dst):
    try:
        if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            if dst.suffix == '.sh' and os.name != 'nt':
                set_exec_if_possible(dst)
            return True
    except Exception:
        return False
    return False


def find_src_candidates(base_dir):
    candidates = [
        Path(base_dir) / 'src',
        Path.cwd() / 'src',
        Path(sys.executable).parent / 'src',
    ]
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        candidates.append(Path(meipass) / 'src')
    return [path for path in candidates if path.exists() and path.is_dir()]


def ensure_user_scripts_available(base_dir, user_app_dir, user_src_dir):
    copied = []
    user_src_dir = Path(user_src_dir)
    user_src_dir.mkdir(parents=True, exist_ok=True)
    for src_dir in find_src_candidates(base_dir):
        for item in src_dir.iterdir():
            if not item.is_file():
                continue
            if item.suffix in ('.sh', '.conf', '.example', '.log') or item.name in (
                'packages.conf',
                'packages.conf.example',
                'extensions.conf',
                'extensions.conf.example',
            ):
                dst = user_src_dir / item.name
                if copy_if_newer(item, dst):
                    copied.append(str(dst))
        break

    for env_example in (Path(base_dir) / '.env.example', Path.cwd() / '.env.example'):
        if env_example.exists():
            copy_if_newer(env_example, Path(user_app_dir) / '.env.example')
            break

    return copied


def find_script(name, user_src_dir, base_dir):
    candidates = [
        Path(user_src_dir) / name,
        Path(base_dir) / 'src' / name,
        Path.cwd() / 'src' / name,
        Path(sys.executable).parent / 'src' / name,
    ]
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        candidates.append(Path(meipass) / 'src' / name)
    candidates.append(Path.home() / '.ok_computer' / 'src' / name)

    checked = []
    for candidate in candidates:
        checked.append(str(candidate))
        if candidate.exists():
            return candidate, checked
    return None, checked


def find_conf_file(name, user_src_dir, base_dir):
    candidates = [
        Path(user_src_dir) / name,
        Path(base_dir) / 'src' / name,
        Path.cwd() / 'src' / name,
        Path(sys.executable).parent / 'src' / name,
        Path.home() / '.ok_computer' / name,
    ]
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        candidates.append(Path(meipass) / 'src' / name)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def run_script_with_optional_admin(script_path, args=None, timeout=None, require_admin=False, extra_env=None):
    args = args or []
    cmd = ['bash', str(script_path)] + list(args)
    run_env = os.environ.copy()
    if extra_env:
        run_env.update(extra_env)
    extra_path = '/opt/homebrew/bin:/usr/local/bin'
    run_env['PATH'] = extra_path + ':' + run_env.get('PATH', '/usr/bin:/bin')

    if require_admin and platform.system().lower() == 'darwin':
        script_cmd = ' '.join(shlex.quote(x) for x in cmd)
        privileged_cmd = f'export PATH={extra_path}:$PATH; {script_cmd}'
        osa_cmd = [
            'osascript',
            '-e',
            f'do shell script {json.dumps(privileged_cmd)} with administrator privileges',
        ]
        res = subprocess.run(osa_cmd, capture_output=True, text=True, timeout=timeout)
        if res.returncode != 0:
            stderr_l = (res.stderr or '').lower()
            if 'user canceled' in stderr_l or 'user cancelled' in stderr_l:
                return {
                    'error': 'administrator authentication canceled by user',
                    'code': 1,
                    'stdout': res.stdout,
                    'stderr': res.stderr,
                }
            return {
                'error': 'administrator authentication failed',
                'code': res.returncode,
                'stdout': res.stdout,
                'stderr': res.stderr,
            }
        return {'code': 0, 'stdout': res.stdout, 'stderr': res.stderr}

    res = subprocess.run(cmd, capture_output=True, text=True, env=run_env, timeout=timeout)
    return {'code': res.returncode, 'stdout': res.stdout, 'stderr': res.stderr}
