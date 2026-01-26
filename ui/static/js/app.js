// TABS
function switchTab(id) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.querySelector(`.tab[onclick="switchTab('${id}')"]`).classList.add('active');
    document.getElementById(id).classList.add('active');
}

// LOAD DATA
window.addEventListener('DOMContentLoaded', () => {
    // Detect lang (simple)
    const lang = navigator.language.startsWith('fr') ? 'fr' : 'en';
    setLanguage(lang);
    
    loadEnv();
    loadPackages();
});

async function loadEnv() {
    const res = await fetch('/api/env');
    const data = await res.json();
    const container = document.getElementById('env-form');
    container.innerHTML = '';
    
    // If API failed or returned empty, show form built from expected keys
    if (!data || (Array.isArray(data) && data.length === 0)) {
        data = [
            {key: 'SYNC_DIR', value: '', desc: ''},
            {key: 'PACKAGES_CONF_DIR', value: '', desc: ''},
            {key: 'OBSIDIAN_VAULT', value: '', desc: ''},
            {key: 'VSCODE_CONFIG', value: '', desc: ''},
            {key: 'SYNC_TYPE', value: '', desc: ''},
            {key: 'ENABLE_DOTFILES_SYNC', value: 'false', desc: ''},
            {key: 'WIFI_KDBX_DB', value: '', desc: ''},
            {key: 'WIFI_KDBX_GROUP', value: 'Wifi', desc: ''},
            {key: 'WIFI_KDBX_KEY_FILE', value: '', desc: ''},
            {key: 'WIFI_KDBX_DRY_RUN', value: '0', desc: ''},
            {key: 'WIFI_KDBX_ASK_PASS', value: '1', desc: ''},
            {key: 'AUTO_UPDATE_HOUR', value: '21', desc: ''},
            {key: 'AUTO_UPDATE_MINUTE', value: '0', desc: ''}
        ];
    }

    // data is now an array of {key, value, desc}
    data.forEach(item => {
        const div = document.createElement('div');
        div.className = 'env-item';

        const key = item.key;
        const val = item.value == null ? '' : item.value;
        const desc = item.desc || '';

        // Infer type from key name and value
        function inferType(key, value) {
            const k = key.toUpperCase();
            const v = (value || '').toString().toLowerCase();
            if (/(_DIR|_PATH|_FILE|VAULT|CONFIG|DB|KEY_FILE)/i.test(k)) {
                if (/_FILE$/i.test(k) || /_KEY_FILE$/i.test(k)) return {type: 'path', mode: 'file'};
                if (/_DIR$/i.test(k) || /_DIR\b/i.test(k)) return {type: 'path', mode: 'dir'};
                return {type: 'path', mode: 'any'};
            }
            if (v === 'true' || v === 'false' || v === '0' || v === '1') return {type: 'boolean'};
            if (k.match(/(HOUR|MINUTE|PORT|COUNT|NUM|SIZE|SECONDS|DAYS)/)) return {type: 'number'};
            if (/^\d+$/.test(v)) return {type: 'number'};
            return {type: 'string'};
        }

        const info = inferType(key, val);

        // Build inner HTML per type
        let inputHtml = '';
        if (info.type === 'boolean') {
            const checked = (val === 'true' || val === '1') ? 'checked' : '';
            inputHtml = `<input type="checkbox" data-key="${key}" ${checked}>`;
        } else if (info.type === 'number') {
            let attrs = '';
            if (key.toUpperCase().includes('HOUR')) attrs = 'min="0" max="23"';
            if (key.toUpperCase().includes('MINUTE')) attrs = 'min="0" max="59"';
            inputHtml = `<input type="number" data-key="${key}" value="${val}" ${attrs}>`;
        } else if (info.type === 'path') {
            // show text input + browse button (browse uses prompt as fallback)
            inputHtml = `<div style="display:flex;gap:8px;align-items:center;"><input type="text" data-key="${key}" value="${val}" style="flex:1"><button type="button" class="secondary" data-browse-for="${key}">Parcourir</button></div>`;
        } else {
            inputHtml = `<input type="text" data-key="${key}" value="${val}">`;
        }

        div.innerHTML = `
            <label class="env-label">${key}</label>
            <div class="env-desc">${desc}</div>
            ${inputHtml}
        `;
        container.appendChild(div);
    });

    // Attach browse handlers. Prefer native pywebview dialogs when available,
    // otherwise fall back to a simple `prompt`.
    container.querySelectorAll('button[data-browse-for]').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const key = btn.dataset.browseFor;
            const input = container.querySelector(`input[data-key="${key}"]`);
            if (!input) return;

            const isFile = /_FILE$|KEY_FILE/i.test(key);
            const isDir = /_DIR$|VAULT|CONFIG|SYNC_DIR/i.test(key);

            // If running inside pywebview, use the exposed API
            if (window.pywebview && window.pywebview.api) {
                try {
                    let path = '';
                    if (isDir) {
                        path = await window.pywebview.api.open_dir(`Select folder for ${key}`);
                    } else {
                        path = await window.pywebview.api.open_file(`Select file for ${key}`);
                    }
                    if (path) input.value = path;
                    return;
                } catch (err) {
                    // fall through to prompt fallback
                }
            }

            // Browser or fallback
            const current = input.value || '';
            const chosen = prompt('Entrez le chemin pour ' + key, current);
            if (chosen !== null) input.value = chosen;
        });
    });

    // no init button — we always present the editable form
}

async function saveEnv() {
    const inputs = document.querySelectorAll('#env-form input');
    const data = {};
    inputs.forEach(i => {
        const key = i.dataset.key;
        if (!key) return;
        if (i.type === 'checkbox') {
            data[key] = i.checked ? 'true' : 'false';
        } else if (i.type === 'number') {
            data[key] = i.value.toString();
        } else {
            data[key] = i.value;
        }
    });
    
    await fetch('/api/env', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    });
    alert(t('settings_saved'));
}

async function loadPackages() {
    const res = await fetch('/api/packages');
    const data = await res.json();
    let html = `<table><thead><tr><th style="width:50px">Icon</th><th>Name (Mac)</th><th>Name (Win)</th><th>Type</th><th>Desc</th><th>Actions</th></tr></thead><tbody>`;
    document.getElementById('pkg-list').innerHTML = html + `<tr><td colspan="6">${t('loading')}</td></tr></tbody></table>`;
    
    let rows = '';
    for (const p of data) {
        // Determine best name for icon lookup
        let iconName = p.mac;
        if(!iconName || iconName=='-') iconName = p.win;
        
        // Unique ID for icon img
        const imgId = 'icon-' + (p.mac || p.win).replace(/[^a-zA-Z0-9]/g, '');
        
        rows += `<tr>
            <td><img id="${imgId}" src="" alt="" style="width:32px;height:32px;border-radius:6px;background:#eee;"></td>
            <td>${p.mac}</td>
            <td>${p.win}</td>
            <td>${p.type}</td>
            <td>${p.desc}</td>
            <td>
                <button class="secondary" style="font-size:10px; padding:4px 8px;" onclick="checkAvail('${p.mac || p.win}')">${t('check')}</button>
            </td>
        </tr>`;
        
        // Lazy load icon
        fetchIcon(imgId, iconName);
    }
    document.getElementById('pkg-list').innerHTML = html + rows + '</tbody></table>';
}

async function fetchIcon(imgId, name) {
     if(!name || name=='-') return;
     try {
         const res = await fetch('/api/icon?name=' + name);
         const d = await res.json();
         if(d.url) {
             document.getElementById(imgId).src = d.url;
         }
     } catch(e) {}
}

async function checkAvail(app) {
    if(!app || app=='-') return;
    alert('Checking availability for ' + app + '...'); // Could utilize t() here but simple alert ok
    const res = await fetch('/api/check?app=' + app);
    const data = await res.json();
    alert(JSON.stringify(data, null, 2));
}

// ACTIONS
async function runUpdate() {
    const btn = document.getElementById('btn-update');
    const log = document.getElementById('update-log');
    const out = document.getElementById('update-output');
    
    btn.disabled = true;
    const originalText = btn.innerText;
    btn.innerText = t('running');
    out.style.display = 'block';
    log.innerText = t('starting_update');
    
    try {
        const res = await fetch('/api/action/update', { method: 'POST' });
        const data = await res.json();
        console.log(data);
        if(data.error) {
            log.innerText = 'Error: ' + data.error;
        } else {
            log.innerText = 'Exit Code: ' + data.code + '\n\nSTDOUT:\n' + data.stdout + '\n\nSTDERR:\n' + data.stderr;
        }
    } catch(e) {
        log.innerText = 'Request failed: ' + e;
    } finally {
        btn.disabled = false;
        btn.innerText = originalText; // restore or use t('run_update')
    }
}

async function importInstalled() {
    const btn = document.querySelector('button[onclick="importInstalled()"]');
    const originalText = btn ? btn.innerText : '';
    if(btn) { btn.disabled = true; btn.innerText = t('running'); }

    try {
        const res = await fetch('/api/action/import-installed', { method: 'POST' });
        const data = await res.json();
        console.log(data);
        if(data.error) {
            alert('Error: ' + data.error);
        } else {
            alert('Exit Code: ' + data.code + '\n\nSTDOUT:\n' + (data.stdout || '').slice(0,2000) + '\n\nSTDERR:\n' + (data.stderr || '').slice(0,2000));
        }
    } catch(e) {
        alert('Request failed: ' + e);
    } finally {
        if(btn) { btn.disabled = false; btn.innerText = originalText; }
    }
}

// SEARCH
async function doSearch() {
    const q = document.getElementById('search-input').value;
    const store = document.getElementById('search-store').value;
    const resultsDiv = document.getElementById('search-results');
    
    resultsDiv.innerHTML = t('loading');
    
    const res = await fetch(`/api/search?q=${q}&store=${store}`);
    const data = await res.json();
    
    let html = '';
    if(data.results) {
        data.results.forEach(r => {
            html += `<h3>${r.store}</h3>`;
            if(r.store === 'homebrew') {
                r.data.forEach && r.data.forEach(item => {
                    const name = item.name || item.token;
                    const desc = item.desc || '';
                    // encode name for js call
                    html += `<div class="search-result-item">
                        <strong>${name}</strong> <span style="color:#888">${desc}</span>
                        <button style="float:right; font-size:10px;" onclick="installApp('${name}')">Install</button>
                    </div>`;
                });
            } else {
                html += `<pre>${r.data}</pre>`;
            }
        });
    }
    resultsDiv.innerHTML = html || 'No results.';
}

async function installApp(name) {
    if(!confirm(t('install_confirm', {name: name}))) return;
    
    alert(t('installing', {name: name}));
    const res = await fetch('/api/action/install', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({app: name})
    });
    const data = await res.json();
    alert('Result:\n' + (data.stdout || data.error));
}

async function promptWifiExport() {
    // Check if DB path is set in env
    const envRes = await fetch('/api/env');
    const envData = await envRes.json() || []; // returns array now
    // convert array to obj
    let envMap = {};
    envData.forEach(e => envMap[e.key] = e.value);

    let dbPath = envMap['WIFI_KDBX_DB'] || '';
    
    dbPath = prompt(t('enter_db_path'), dbPath);
    if(!dbPath) return;
    
    const password = prompt(t('enter_db_pass'));
    if(!password) return;
    
    const btn = document.querySelector('button[onclick="promptWifiExport()"]');
    const originalText = btn.innerText;
    btn.innerText = t('exporting');
    btn.disabled = true;
    
    try {
        const res = await fetch('/api/action/wifi-export', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({db: dbPath, password: password})
        });
        const data = await res.json();
        if(data.error) {
            alert('Error: ' + data.error);
        } else {
            if(data.code !== 0) {
                 alert('Failed (Exit Code ' + data.code + '):\n' + data.stderr + '\n' + data.stdout);
            } else {
                 alert('Success:\n' + data.stdout.slice(-500)); 
            }
        }
    } catch(e) {
        alert('Request failed: ' + e);
    } finally {
        btn.innerText = originalText;
        btn.disabled = false;
    }
}
