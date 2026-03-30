from pathlib import Path
import re

from dotenv import load_dotenv, set_key


class PreferencesService:
    def __init__(self, env_local, env_example, env_local_repo, legacy_hidden_env_keys, logger, sync_env_to_repo):
        self.env_local = Path(env_local)
        self.env_example = Path(env_example)
        self.env_local_repo = Path(env_local_repo)
        self.legacy_hidden_env_keys = set(legacy_hidden_env_keys)
        self.logger = logger
        self.sync_env_to_repo = sync_env_to_repo

    def load_env_dict(self):
        schema = []
        if self.env_example.exists():
            with self.env_example.open() as f:
                last_comment = ""
                last_type = None
                types_map = {}
                last_examples = []
                for line in f:
                    raw = line.rstrip('\n')
                    s = raw.strip()
                    if not s:
                        last_comment = ""
                        last_type = None
                        last_examples = []
                        continue
                    if s.startswith('#'):
                        m_key = re.match(r"#\s*([A-Z0-9_]+)\s*:\s*TYPE\s*:\s*(.+)$", raw, re.IGNORECASE)
                        if m_key:
                            types_map[m_key.group(1).strip()] = m_key.group(2).strip()
                            continue
                        m = re.search(r"TYPE:\s*(.+)$", raw, re.IGNORECASE)
                        if m:
                            last_type = m.group(1).strip()
                            continue
                        m_example = re.match(r'^#\s*([A-Z0-9_]+)\s*=\s*(.+)$', s)
                        if m_example:
                            example_val = m_example.group(2).strip().strip('"')
                            last_examples.append(example_val)
                            continue
                        if s.strip('#').strip().lower() in ('examples:', 'example:'):
                            continue
                        last_comment += raw.lstrip('#').strip() + ' '
                        continue
                    if '=' in s:
                        k, v = s.split('=', 1)
                        keyname = k.strip()
                        if keyname in self.legacy_hidden_env_keys:
                            last_comment = ""
                            last_type = None
                            last_examples = []
                            continue
                        declared = types_map.get(keyname) or last_type
                        schema.append({
                            'key': keyname,
                            'default': v.strip().strip('"'),
                            'desc': last_comment.strip(),
                            'type': declared,
                            'examples': list(last_examples),
                        })
                        last_comment = ""
                        last_type = None
                        last_examples = []

        env_local_exists = self.env_local.exists()
        if not env_local_exists and self.env_example.exists():
            try:
                self.env_local.write_text(self.env_example.read_text())
                self.sync_env_to_repo()
                self.logger.info('.env.local auto-created from .env.example')
                env_local_exists = True
            except Exception as exc:
                self.logger.warning('Failed to auto-create .env.local: %s', exc)

        current = {}
        if env_local_exists and self.env_local.exists():
            load_dotenv(dotenv_path=self.env_local, override=False)
            with self.env_local.open() as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    k, v = line.split('=', 1)
                    current[k.strip()] = v.strip().strip('"').strip("'")

        final_list = []
        seen = set()
        for item in schema:
            key = item['key']
            val = current.get(key, item['default'])
            entry = {'key': key, 'value': val, 'desc': item['desc']}
            if item.get('type'):
                entry['type'] = item['type']
            if item.get('examples'):
                entry['examples'] = item['examples']
            final_list.append(entry)
            seen.add(key)

        for k, v in current.items():
            if k not in seen and k not in self.legacy_hidden_env_keys:
                final_list.append({'key': k, 'value': v, 'desc': 'Custom setting'})
        return final_list

    def parse_env_example_schema(self):
        schema = []
        if not self.env_example.exists():
            return schema
        try:
            with self.env_example.open() as f:
                for raw in f:
                    s = raw.strip()
                    if not s or s.startswith('#') or '=' not in s:
                        continue
                    k, v = s.split('=', 1)
                    schema.append((k.strip(), v.strip().strip('"').strip("'")))
        except Exception:
            return []
        return schema

    def read_env_keys(self, path):
        path = Path(path)
        keys = set()
        if not path.exists():
            return keys
        try:
            with path.open() as f:
                for raw in f:
                    s = raw.strip()
                    if not s or s.startswith('#') or '=' not in s:
                        continue
                    k, _ = s.split('=', 1)
                    keys.add(k.strip())
        except Exception:
            return keys
        return keys

    def ensure_env_local_complete(self):
        if not self.env_local.exists():
            if self.env_example.exists():
                self.env_local.write_text(self.env_example.read_text())
            else:
                self.env_local.write_text('')
            return

        schema = self.parse_env_example_schema()
        if not schema:
            return

        existing = self.read_env_keys(self.env_local)
        for key, default in schema:
            if key not in existing:
                set_key(str(self.env_local), key, str(default))

    def parse_system_settings_conf(self, system_settings_conf, find_conf_file_fn, base_dir, runtime_src_dir_fn=None):
        conf = Path(system_settings_conf) if Path(system_settings_conf).exists() else find_conf_file_fn('system_settings.conf')
        if not conf or not Path(conf).exists():
            fallback = Path(base_dir) / 'src' / 'system_settings.conf'
            conf = fallback if fallback.exists() else Path(base_dir) / 'src' / 'system_settings.conf.example'

        items = []
        if not Path(conf).exists():
            return items

        def _normalize(v):
            if v is None:
                return ''
            v = str(v).strip()
            if v == '-':
                return ''
            return v

        def _normalize_bool(v):
            if v.lower() in ('true', '1', 'yes', 'on'):
                return 'true'
            if v.lower() in ('false', '0', 'no', 'off'):
                return 'false'
            return None

        with Path(conf).open() as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith('#'):
                    continue
                parts = [p.strip() for p in line.split('|')]
                if len(parts) < 5:
                    continue
                key = parts[0]
                mac = _normalize(parts[1])
                win = _normalize(parts[2])
                linux = _normalize(parts[3])
                desc = parts[4]
                candidate_vals = [x for x in (mac, win, linux) if x != '']
                if not candidate_vals:
                    shared_value = ''
                elif all(x.lower() == candidate_vals[0].lower() for x in candidate_vals):
                    shared_value = candidate_vals[0]
                else:
                    shared_value = candidate_vals[0]

                bool_val = _normalize_bool(shared_value)
                if bool_val is not None:
                    setting_type = 'boolean'
                    shared_value = bool_val
                    options = None
                else:
                    use_choices = ['left', 'bottom', 'right', 'top']
                    lower_vals = [v.lower() for v in candidate_vals]
                    if any(v in use_choices for v in lower_vals):
                        setting_type = 'choice'
                        options = use_choices
                        if shared_value.lower() not in use_choices:
                            shared_value = use_choices[0]
                    else:
                        setting_type = 'string'
                        options = None

                items.append({
                    'key': key,
                    'mac': mac or '-',
                    'win': win or '-',
                    'linux': linux or '-',
                    'desc': desc,
                    'raw': line,
                    'value': shared_value,
                    'type': setting_type,
                    'options': options,
                })
        return items
