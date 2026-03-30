// I18N helper + simple client logger
const I18N = { lang: 'en', dict: {} };
async function setLanguage(lang) {
  I18N.lang = lang || I18N.lang || 'en';
  try {
    const res = await fetch(`/static/i18n/${I18N.lang}.json`);
    if (res.ok) I18N.dict = await res.json(); else I18N.dict = {};
  } catch (e) { console.warn('i18n load failed', e); I18N.dict = {}; }
}
function t(key, params) {
  let s = (I18N.dict && I18N.dict[key]) ? I18N.dict[key] : key;
  if (params && typeof params === 'object') {
    Object.keys(params).forEach(k => { s = s.replace(new RegExp('\{' + k + '\}', 'g'), params[k]); });
  }
  return s;
}

class Logger {
  constructor(level = 'INFO') { this.level = level; }
  send(level, message, meta) {
    const l = (level || 'INFO').toUpperCase();
    if (l === 'ERROR') console.error(`[${l}] ${message}`, meta || '');
    else if (l === 'WARN') console.warn(`[${l}] ${message}`, meta || '');
    else console.log(`[${l}] ${message}`, meta || '');
    try {
      fetch('/api/log', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ level: l, message: message, meta: meta }) }).catch(()=>{});
    } catch (e) { /* swallow */ }
  }
  info(m,meta){ this.send('INFO', m, meta); }
  warn(m,meta){ this.send('WARN', m, meta); }
  error(m,meta){ this.send('ERROR', m, meta); }
}
window.logger = new Logger();
let extensionsInstallInProgress = false;

// Utility: HTML escape for safe display
function escapeHtml(text) {
  if (typeof text !== 'string') return '';
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  return text.replace(/[&<>"']/g, m => map[m]);
}

// TABS
function switchTab(id) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    const tab = document.querySelector(`.tab[onclick="switchTab('${id}')"]`);
    if (tab) tab.classList.add('active');
    const content = document.getElementById(id);
    if (content) content.classList.add('active');
}

// Simple modal preview editor used to edit lines before saving
function showPreviewModal(lines, onSave, opts) {
  opts = opts || {};
  // if modal exists, remove
  const existing = document.getElementById('preview-modal-overlay');
  if (existing) existing.remove();

  // Build modal using template root if available
  const root = document.getElementById('global-modal-root') || document.body;
  const overlay = document.createElement('div');
  overlay.id = 'preview-modal-overlay';
  overlay.className = 'modal-overlay';

  const modal = document.createElement('div');
  modal.className = 'modal-card';

  const title = document.createElement('div');
  title.className = 'modal-title';
  title.innerText = opts.title || (typeof t === 'function' ? t('preview') : 'Preview');

  const textarea = document.createElement('textarea');
  textarea.className = 'modal-textarea';
  textarea.value = lines.join('\n');

  const footer = document.createElement('div');
  footer.className = 'modal-footer';

  const btnCancel = document.createElement('button');
  btnCancel.innerText = opts.cancelText || 'Cancel';
  btnCancel.className = 'secondary';
  btnCancel.onclick = () => overlay.remove();

  const btnSave = document.createElement('button');
  btnSave.innerText = opts.saveText || 'Save';
  btnSave.onclick = async () => {
    const final = textarea.value.split('\n').map(s => s.trim()).filter(Boolean);
    overlay.remove();
    try { if (typeof onSave === 'function') await onSave(final); } catch (e) { showToast('Save failed: ' + e, 'error'); }
  };

  footer.appendChild(btnCancel);
  footer.appendChild(btnSave);

  modal.appendChild(title);
  modal.appendChild(textarea);
  modal.appendChild(footer);
  overlay.appendChild(modal);
  root.style.display = '';
  root.appendChild(overlay);
  textarea.focus();
}

// Toast notifications (non-blocking)
function showToast(message, type='info', duration=4000) {
  try {
    const container = document.getElementById('toast-container') || (function(){ const d=document.createElement('div'); d.id='toast-container'; document.body.appendChild(d); return d; })();
    const node = document.createElement('div');
    node.className = 'toast ' + (type||'info');
    node.innerText = message;
    container.appendChild(node);
    setTimeout(() => { node.style.opacity = '0'; node.style.transition = 'opacity 300ms'; setTimeout(()=>node.remove(), 350); }, duration);
  } catch (e) { console.log('toast error', e); }
}

// Modal prompt (returns Promise<string|null>) and confirm (Promise<boolean>)
function showPrompt(message, defaultValue = '', opts = {}) {
  return new Promise((resolve) => {
    const existing = document.getElementById('prompt-modal-overlay');
    if (existing) existing.remove();
    const root = document.getElementById('global-modal-root') || document.body;
    root.style.display = '';  // ensure container is visible
    const overlay = document.createElement('div'); overlay.id = 'prompt-modal-overlay'; overlay.className = 'modal-overlay';
    const modal = document.createElement('div'); modal.className = 'modal-card';
    const title = document.createElement('div'); title.className = 'modal-title'; title.innerText = opts.title || message || '';
    const input = document.createElement('input'); input.className = 'modal-input'; input.type = opts.mask ? 'password' : 'text'; input.value = defaultValue || '';
    const footer = document.createElement('div'); footer.className = 'modal-footer';
    const btnCancel = document.createElement('button'); btnCancel.className = 'secondary'; btnCancel.innerText = opts.cancelText || 'Cancel'; btnCancel.onclick = () => { overlay.remove(); resolve(null); };
    const btnOk = document.createElement('button'); btnOk.innerText = opts.okText || 'OK'; btnOk.onclick = () => { const v = input.value; overlay.remove(); resolve(v); };
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') btnOk.click(); else if (e.key === 'Escape') btnCancel.click(); });
    footer.appendChild(btnCancel); footer.appendChild(btnOk);
    modal.appendChild(title); modal.appendChild(input); modal.appendChild(footer); overlay.appendChild(modal); root.appendChild(overlay); input.focus(); input.select();
  });
}

function showConfirm(message, opts = {}) {
  return new Promise((resolve) => {
    const existing = document.getElementById('confirm-modal-overlay'); if (existing) existing.remove();
    const root = document.getElementById('global-modal-root') || document.body;
    root.style.display = '';  // ensure container is visible
    const overlay = document.createElement('div'); overlay.id = 'confirm-modal-overlay'; overlay.className = 'modal-overlay';
    const modal = document.createElement('div'); modal.className = 'modal-card';
    const title = document.createElement('div'); title.className = 'modal-title'; title.innerText = opts.title || message || '';
    const footer = document.createElement('div'); footer.className = 'modal-footer';
    const btnNo = document.createElement('button'); btnNo.className = 'secondary'; btnNo.innerText = opts.noText || 'No'; btnNo.onclick = () => { overlay.remove(); resolve(false); };
    const btnYes = document.createElement('button'); btnYes.innerText = opts.yesText || 'Yes'; btnYes.onclick = () => { overlay.remove(); resolve(true); };
    modal.appendChild(title); modal.appendChild(footer); overlay.appendChild(modal); root.appendChild(overlay);
    footer.appendChild(btnNo); footer.appendChild(btnYes);
  });
}

// Validate extension lines before saving
function validateExtensionLines(lines) {
  const errors = [];
  lines.forEach((ln, idx) => {
    const parts = ln.split('|');
    if (parts.length < 2) { errors.push({line: idx+1, reason: 'Too few segments'}); return; }
    const mode = parts[0].trim();
    if (!mode) { errors.push({line: idx+1, reason: 'Empty mode'}); return; }
    if (mode === 'all') {
      if (parts.length < 4) errors.push({line: idx+1, reason: 'mode "all" requires 4 parts: all|chrome|firefox|desc'});
    } else if (['chrome','firefox','arc'].includes(mode)) {
      if (parts.length < 3) errors.push({line: idx+1, reason: `${mode} requires 3 parts: ${mode}|id|desc`});
      if (!parts[1] || parts[1].trim()==='') errors.push({line: idx+1, reason: 'Empty id'});
    } else {
      // allow freeform descriptions but warn
      if (parts.length === 1) errors.push({line: idx+1, reason: 'Unknown format'});
    }
  });
  return errors;
}

// LOAD DATA
// Single, cleaned JS file for UI interactions
// (Removed duplicated/malformed sections)

// --- Tabs
function switchTab(id) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  const tab = document.querySelector(`.tab[onclick="switchTab('${id}')"]`);
  if (tab) tab.classList.add('active');
  const content = document.getElementById(id);
  if (content) content.classList.add('active');
}

function applyTheme(mode) {
  const root = document.documentElement;
  if (!root) return;
  if (!mode || mode === 'auto') {
    const isDark = !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
    root.setAttribute('data-theme', isDark ? 'dark' : 'light');
    return;
  }
  root.setAttribute('data-theme', mode === 'dark' ? 'dark' : 'light');
}

function setThemeMode(mode) {
  const value = mode || 'auto';
  try {
    localStorage.setItem('okc-theme-mode', value);
  } catch (e) {}
  applyTheme(value);
}

function initThemeMode() {
  let saved = 'auto';
  try {
    saved = localStorage.getItem('okc-theme-mode') || 'auto';
  } catch (e) {}
  applyTheme(saved);
  const picker = document.getElementById('theme-mode');
  if (picker) picker.value = saved;

  // Keep Auto synced with system preference changes
  if (window.matchMedia) {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => {
      let mode = 'auto';
      try { mode = localStorage.getItem('okc-theme-mode') || 'auto'; } catch (e) {}
      if (mode === 'auto') applyTheme('auto');
    };
    if (typeof media.addEventListener === 'function') media.addEventListener('change', onChange);
    else if (typeof media.addListener === 'function') media.addListener(onChange);
  }
}

// --- Init
window.addEventListener('DOMContentLoaded', async () => {
  const lang = navigator.language && navigator.language.startsWith('fr') ? 'fr' : 'en';
  if (typeof setLanguage === 'function') await setLanguage(lang);
  initThemeMode();
  loadEnv();
  loadDotfilesStatus();
  loadSharedConfigStatus();
  loadPackages();
  loadSystemSettings();
  loadExtensions();
  loadAutoUpdateStatus();
});

// --- System Settings
async function loadSystemSettings() {
  const container = document.getElementById('system-settings-list');
  if (!container) return;
  container.innerHTML = 'Loading...';

  try {
    const res = await fetch('/api/system-settings');
    const data = await res.json();
    if (!Array.isArray(data) || data.length === 0) {
      container.innerHTML = 'No system settings found.';
      return;
    }

    let html = '<table><thead><tr><th>Key</th><th>Value (shared)</th><th>Description</th></tr></thead><tbody>';
    data.forEach((row) => {
      const key = escapeHtml(row.key || '');
      const desc = escapeHtml(row.desc || '');
      const value = row.value || '';
      const type = row.type || 'string';
      const options = row.options || [];

      let valueControl = '';
      if (type === 'boolean') {
        const checked = (value.toString().toLowerCase() === 'true') ? 'checked' : '';
        valueControl = `<input type="checkbox" data-field="value" ${checked}>`;
      } else if (type === 'choice' && Array.isArray(options) && options.length > 0) {
        valueControl = `<select data-field="value">${options.map(opt => `<option value="${opt}" ${opt === (value || options[0]) ? 'selected' : ''}>${opt}</option>`).join('')}</select>`;
      } else {
        valueControl = `<input type="text" data-field="value" value="${escapeHtml(value)}">`;
      }

      html += '<tr>' +
        `<td><input data-field="key" value="${key}"></td>` +
        `<td data-field="type" data-value-type="${type}">${valueControl}</td>` +
        `<td><input data-field="desc" value="${desc}"></td>` +
        '</tr>';
    });
    html += '</tbody></table>';
    container.innerHTML = html;
  } catch (e) {
    container.innerHTML = 'Failed to load: ' + e;
  }
}

function collectSystemSettingsLines() {
  const container = document.getElementById('system-settings-list');
  if (!container) return [];
  const rows = container.querySelectorAll('tbody tr');
  const lines = [];
  rows.forEach((r) => {
    const key = (r.querySelector('input[data-field="key"]') || {}).value || '';
    const desc = (r.querySelector('input[data-field="desc"]') || {}).value || '';
    const cellType = r.querySelector('[data-field="type"]');
    const valueField = r.querySelector('[data-field="value"]');
    if (!valueField) return;

    let sharedValue = '';
    if (valueField.type === 'checkbox') {
      sharedValue = valueField.checked ? 'true' : 'false';
    } else if (valueField.tagName === 'SELECT') {
      sharedValue = valueField.value;
    } else {
      sharedValue = valueField.value;
    }

    const keyTrimmed = key.trim();
    if (!keyTrimmed) return;

    // Save as shared value for all OS. Keep backwards compat by writing explicit per-OS values.
    lines.push([keyTrimmed, sharedValue || '-', sharedValue || '-', sharedValue || '-', desc.trim()].join('|'));
  });
  return lines;
}

async function saveSystemSettings() {
  const lines = collectSystemSettingsLines();
  try {
    const res = await fetch('/api/system-settings/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lines })
    });
    const data = await res.json();
    if (!res.ok || data.error) {
      showToast('Save failed: ' + (data.error || 'unknown error'), 'error');
      return;
    }
    showToast('System settings saved.', 'success');
  } catch (e) {
    showToast('Save failed: ' + e, 'error');
  }
}

async function applySystemSettings() {
  const out = document.getElementById('system-settings-output');
  if (out) {
    out.style.display = 'block';
    out.innerText = 'Applying system settings...';
  }

  try {
    const res = await fetch('/api/system-settings/apply', { method: 'POST' });
    const data = await res.json();
    if (out) out.innerText = JSON.stringify(data, null, 2);

    if (res.status === 401) {
      showToast('Administrator authentication canceled.', 'warn');
    } else if (!res.ok || data.error || data.code !== 0) {
      showToast('Apply failed.', 'error');
    } else {
      showToast('System settings applied.', 'success');
    }
  } catch (e) {
    if (out) out.innerText = 'Apply failed: ' + e;
    showToast('Apply failed: ' + e, 'error');
  }
}

// --- Extensions
async function loadExtensions() {
  const container = document.getElementById('extensions-list');
  if (!container) return;
  container.innerHTML = 'Loading...';
  try {
    const [cfgRes, installedRes] = await Promise.all([
      fetch('/api/extensions'),
      fetch('/api/extensions/scan')
    ]);
    const data = await cfgRes.json();
    const installed = await installedRes.json();
    if (!Array.isArray(data)) { container.innerHTML = 'No extensions configured.'; return; }

    const installedList = Array.isArray(installed) ? installed : [];
    const installedChrome = new Map();
    const installedFirefox = new Map();
    for (const item of installedList) {
      if (!item || !item.id) continue;
      if (item.browser === 'firefox') {
        // Use slug for Firefox (resolves GUID to store slug for comparison)
        const key = item.slug || item.id;
        installedFirefox.set(key, item);
      }
      else installedChrome.set(item.id, item);
    }

    const renderIcon = (iconUrl, altText) => {
      if (!iconUrl) return '<span style="color:#999">-</span>';
      return `<img src="${escapeHtml(iconUrl)}" alt="${escapeHtml(altText || 'ext')}" title="${escapeHtml(altText || 'extension')}" style="width:20px;height:20px;border-radius:6px;vertical-align:middle;">`;
    };

    const renderOfficialLinks = (links) => {
      if (!Array.isArray(links) || !links.length) return '<span style="color:#999">-</span>';
      return links
        .filter(Boolean)
        .map((u, idx) => `<a href="${escapeHtml(u)}" target="_blank" rel="noopener noreferrer">Official ${idx + 1}</a>`)
        .join(' | ');
    };

    let html = `<div style="margin-bottom:8px;"><button onclick="scanLocalExtensions()">Scan local browsers</button></div>`;
    html += `<table><thead><tr><th>Icon</th><th>Mode</th><th>Chrome ID</th><th>Firefox slug</th><th>Description</th><th>Official page(s)</th><th>Installed</th><th>Actions</th></tr></thead><tbody>`;

    const renderedInstalledKeys = new Set();
    for (const e of data) {
      const chrome = e.chrome || (e.id && e.mode === 'chrome' ? e.id : '');
      const firefox = e.firefox || (e.id && e.mode === 'firefox' ? e.id : '');
      const desc = e.desc || '';
      const chromeInstalled = !!(chrome && installedChrome.has(chrome));
      const firefoxInstalled = !!(firefox && installedFirefox.has(firefox));
      const chromeInstalledItem = chrome ? installedChrome.get(chrome) : null;
      const firefoxInstalledItem = firefox ? installedFirefox.get(firefox) : null;
      const statusBits = [];
      if (chrome) statusBits.push(`Chrome: ${chromeInstalled ? 'Installed' : 'Missing'}`);
      if (firefox) statusBits.push(`Firefox: ${firefoxInstalled ? 'Installed' : 'Missing'}`);
      if (!statusBits.length) statusBits.push('No ID');

      if (chromeInstalled) renderedInstalledKeys.add(`chrome:${chrome}`);
      if (firefoxInstalled) renderedInstalledKeys.add(`firefox:${firefox}`);

      const actionButtons = [];
      // Show Search button only if at least one platform is missing
      const allPlatformsConfigured = (chrome || firefox);
      const hasAnyMissing = (chrome && !chromeInstalled) || (firefox && !firefoxInstalled);
      if (allPlatformsConfigured && hasAnyMissing) {
        actionButtons.push(`<button type="button" onclick="searchForRow(this)">Search</button>`);
      }
      if (chromeInstalled) {
        actionButtons.push(`<button type="button" class="secondary" onclick="uninstallConfiguredExtension(this, 'chrome')">Uninstall Chrome</button>`);
      }
      if (firefoxInstalled) {
        actionButtons.push(`<button type="button" class="secondary" onclick="uninstallConfiguredExtension(this, 'firefox')">Uninstall Firefox</button>`);
      }

      const iconCandidates = [];
      if (chromeInstalledItem && chromeInstalledItem.icon_url) iconCandidates.push(renderIcon(chromeInstalledItem.icon_url, `Chrome ${chrome || ''}`));
      if (firefoxInstalledItem && firefoxInstalledItem.icon_url) iconCandidates.push(renderIcon(firefoxInstalledItem.icon_url, `Firefox ${firefox || ''}`));
      if (!iconCandidates.length && e.icon_url) iconCandidates.push(renderIcon(e.icon_url, `${e.mode || ''} ${e.id || ''}`));
      const icons = iconCandidates;

      const officialLinks = e.official_urls || [e.chrome_url, e.firefox_url, e.official_url].filter(Boolean);

      html += `<tr>` +
        `<td>${icons.length ? icons.join(' ') : '<span style="color:#999">-</span>'}</td>` +
        `<td>${escapeHtml(e.mode || '')}</td>` +
        `<td><input data-field="chrome" value="${escapeHtml(chrome)}"></td>` +
        `<td><input data-field="firefox" value="${escapeHtml(firefox)}"></td>` +
        `<td><input data-field="desc" value="${escapeHtml(desc)}"></td>` +
        `<td>${renderOfficialLinks(officialLinks)}</td>` +
        `<td>${escapeHtml(statusBits.join(' | '))}</td>` +
        `<td style="white-space:nowrap;">` +
          actionButtons.join(' ') +
        `</td>` +
      `</tr>`;
    }

    for (const ext of installedList) {
      const browser = ext.browser === 'firefox' ? 'firefox' : 'chrome';
      const key = `${browser}:${ext.id}`;
      if (renderedInstalledKeys.has(key)) continue;
      const chrome = browser === 'chrome' ? (ext.id || '') : '';
      const firefox = browser === 'firefox' ? (ext.id || '') : '';
      const desc = ext.name || '(installed only)';
      const extLinks = ext.official_url ? [ext.official_url] : [];
      html += `<tr data-configured="0">` +
        `<td>${renderIcon(ext.icon_url, ext.name || ext.id || 'extension')}</td>` +
        `<td>installed</td>` +
        `<td><input data-field="chrome" value="${escapeHtml(chrome)}" disabled></td>` +
        `<td><input data-field="firefox" value="${escapeHtml(firefox)}" disabled></td>` +
        `<td><input data-field="desc" value="${escapeHtml(desc)}" disabled></td>` +
        `<td>${renderOfficialLinks(extLinks)}</td>` +
        `<td>${browser === 'chrome' ? 'Chrome: Installed' : 'Firefox: Installed'}</td>` +
        `<td style="white-space:nowrap;">` +
          `<button type="button" class="secondary" onclick="uninstallStandaloneExtension('${escapeHtml(browser)}', '${escapeHtml(ext.id || '')}')">Uninstall</button>` +
        `</td>` +
      `</tr>`;
    }

    html += '</tbody></table>';
    container.innerHTML = html;
  } catch (err) { container.innerHTML = 'Failed to load: ' + (err && err.message ? err.message : err); }
}

async function scanLocalExtensions() {
  try {
    const res = await fetch('/api/extensions/scan');
    const data = await res.json();
    if (!Array.isArray(data) || data.length === 0) return showToast('No local browser extensions found.', 'info');
    // Prepare preview lines to append
    const curRes = await fetch('/api/extensions');
    const cur = await curRes.json();
    const existingIds = new Set();
    const baseLines = [];
    cur.forEach(item => {
      if (item.raw) { baseLines.push(item.raw); const parts = item.raw.split('|'); if (parts[1]) existingIds.add(parts[1]); }
      else if (item.mode === 'all') { baseLines.push(['all', item.chrome||'', item.firefox||'', item.desc||''].join('|')); if (item.chrome) existingIds.add(item.chrome); if (item.firefox) existingIds.add(item.firefox); }
      else if (item.mode === 'chrome' || item.mode === 'firefox' || item.mode === 'arc') { baseLines.push([item.mode, item.id||'', item.desc||''].join('|')); if (item.id) existingIds.add(item.id); }
      else { baseLines.push(item.raw || ''); }
    });

    const newLines = [];
    data.forEach(d => {
      if (d.browser === 'firefox') {
        // Use slug for Firefox (store slug, not local GUID)
        const id = d.slug || d.id || '';
        if (!id || existingIds.has(id)) return;
        newLines.push(['firefox', id, d.name || ''].join('|'));
      } else {
        const id = d.id || '';
        if (!id || existingIds.has(id)) return;
        newLines.push(['chrome', id, d.name || ''].join('|'));
      }
    });

    if (newLines.length === 0) return showToast('No new extensions to add.', 'info');

    // Show modal preview allowing user to edit lines before save
    showPreviewModal(newLines, async (finalLines) => {
      const lines = baseLines.concat(finalLines || []);
      const upd = await fetch('/api/extensions/update', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ lines }) });
      const r = await upd.json();
      if (r.status) { showToast('Extensions list updated.', 'success'); loadExtensions(); }
      else showToast('Error updating: ' + (r.error || JSON.stringify(r)), 'error');
    }, { title: 'Preview extensions to append', saveText: 'Append', cancelText: 'Cancel' });
  } catch (e) { showToast('Scan failed: ' + e, 'error'); }
}

async function importInstalledExtensions() {
  return scanLocalExtensions();
}

function refreshExtensions() {
  loadExtensions();
}

async function searchGlobal() {
  const qEl = document.getElementById('ext-global-search');
  const q = qEl ? qEl.value : '';
  if (!q) return showToast('Enter a search term', 'warn');
  const res = await fetch('/api/extensions/search?q=' + encodeURIComponent(q));
  const data = await res.json();
  let msg = '';
  if (data.firefox && data.firefox.length) msg += 'Firefox results:\n' + data.firefox.map(f => `${f.name} — ${f.slug}`).join('\n') + '\n\n';
  if (data.chrome && data.chrome.length) msg += 'Chrome IDs:\n' + data.chrome.map(c => c.id).join('\n') + '\n';
  if (msg) showToast('Search results: ' + (msg.split('\n')[0]||''), 'info'); else showToast('No results', 'info');
}

async function searchForRow(btn) {
  const row = btn.closest('tr');
  const desc = row.querySelector('input[data-field="desc"]').value || '';
  let q = desc;
  if (!q) q = await showPrompt((typeof t === 'function') ? t('search_query_prompt') : 'Search query (name or description)', '');
  if (!q) return;
  const res = await fetch('/api/extensions/search?q=' + encodeURIComponent(q));
  const data = await res.json();
  if (data.chrome && data.chrome.length) row.querySelector('input[data-field="chrome"]').value = data.chrome[0].id;
  if (data.firefox && data.firefox.length) row.querySelector('input[data-field="firefox"]').value = data.firefox[0].slug;
  showToast('Populated results (edit as needed, then Save List)', 'success');
}

function collectExtensionLines() {
  const container = document.getElementById('extensions-list');
  if (!container) return [];
  const rows = container.querySelectorAll('tbody tr');
  const lines = [];
  rows.forEach(r => {
    if (r.dataset.configured === '0') return;
    const mode = r.children[0].innerText.trim();
    const chrome = r.querySelector('input[data-field="chrome"]').value.trim();
    const firefox = r.querySelector('input[data-field="firefox"]').value.trim();
    const desc = r.querySelector('input[data-field="desc"]').value.trim();
    if (mode === 'all') lines.push(['all', chrome, firefox, desc].join('|'));
    else if (mode === 'chrome' || mode === 'firefox' || mode === 'arc') lines.push([mode, (mode === 'chrome' ? chrome : firefox), desc].join('|'));
    else lines.push(desc || '');
  });
  return lines;
}

async function saveExtensions() {
  const lines = collectExtensionLines();
  const res = await fetch('/api/extensions/update', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ lines }) });
  const data = await res.json();
  if (data.status) showToast('Saved', 'success'); else showToast('Error: ' + (data.error || 'unknown'), 'error');
}

async function installExtensions(btn) {
  if (extensionsInstallInProgress) {
    showToast('Install already running...', 'warn');
    return;
  }

  extensionsInstallInProgress = true;
  const out = document.getElementById('extensions-output');
  const button = btn || document.querySelector('button[onclick="installExtensions(this)"]');
  const originalLabel = button ? button.innerText : '';

  if (button) {
    button.disabled = true;
    button.innerText = 'Installing...';
  }
  if (out) {
    out.style.display = 'block';
    out.innerText = 'Installing extensions. This can take a few minutes...';
  }

  try {
    const sudoRes = await fetch('/api/sudo/status');
    const sudo = await sudoRes.json();
    if (sudo.interactivePrompt) {
      if (out) {
        out.innerText = [
          'A system password dialog may appear during installation.',
          'No terminal is required.'
        ].join('\n');
      }
    } else if (!sudo.available) {
      const msg = (sudo.message || 'sudo is not available. Running in user mode.');
      if (out) {
        out.innerText = [
          'sudo is not available in non-interactive mode.',
          'Continuing in user mode (no terminal required).',
          'Some system-wide policies may be skipped.',
          '',
          'Details:',
          msg
        ].join('\n');
      }
      showToast('Installing in user mode (without sudo).', 'warn');
    }

    const res = await fetch('/api/extensions/install', { method: 'POST' });
    const data = await res.json();
    if (out) out.innerText = JSON.stringify(data, null, 2);

    if (res.status === 409) {
      showToast('An extensions install is already running.', 'warn');
    } else if (res.status === 401) {
      showToast('Administrator authentication canceled.', 'warn');
    } else if (res.status === 504) {
      showToast('Install timed out. Check output and retry.', 'error');
    } else if (!res.ok || data.error || data.code !== 0) {
      showToast('Extensions install failed.', 'error');
    } else {
      showToast('Extensions install completed.', 'success');
      loadExtensions();
    }
  } catch (e) {
    if (out) out.innerText = 'Install failed: ' + e;
    showToast('Extensions install failed: ' + e, 'error');
  } finally {
    extensionsInstallInProgress = false;
    if (button) {
      button.disabled = false;
      button.innerText = originalLabel || 'Install Extensions';
    }
  }
}

async function runExtensionUninstall(requests, successMessage) {
  const failures = [];
  for (const req of requests) {
    const res = await fetch('/api/extensions/uninstall', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req)
    });
    const data = await res.json();
    if (data.status !== 'ok') {
      failures.push(data.message || data.error || `${req.browser}:${req.id}`);
    }
  }

  if (failures.length) {
    showToast('Uninstall failed: ' + failures.join(' | '), 'error');
    return false;
  }

  showToast(successMessage || 'Extension uninstalled', 'success');
  return true;
}

async function uninstallConfiguredExtension(btn, browser) {
  const row = btn.closest('tr');
  if (!row) return;
  const mode = row.children[0] ? row.children[0].innerText.trim() : '';
  const chromeInput = row.querySelector('input[data-field="chrome"]');
  const firefoxInput = row.querySelector('input[data-field="firefox"]');
  const descInput = row.querySelector('input[data-field="desc"]');
  const extId = browser === 'firefox' ? (firefoxInput?.value.trim() || '') : (chromeInput?.value.trim() || '');
  const desc = descInput?.value.trim() || extId;

  if (!extId) {
    showToast('No extension ID found on this row.', 'warn');
    return;
  }

  const ok = await showConfirm(
    `Uninstall ${desc} from ${browser}?`,
    { title: 'Uninstall Extension', yesText: 'Uninstall', noText: 'Cancel' }
  );
  if (!ok) return;

  try {
    const succeeded = await runExtensionUninstall([{ browser, id: extId }], 'Extension uninstalled');
    if (!succeeded) return;

    if (mode === 'all') {
      if (browser === 'firefox' && firefoxInput) firefoxInput.value = '';
      if (browser !== 'firefox' && chromeInput) chromeInput.value = '';
      const hasChrome = chromeInput && chromeInput.value.trim();
      const hasFirefox = firefoxInput && firefoxInput.value.trim();
      if (!hasChrome && !hasFirefox) row.remove();
    } else {
      row.remove();
    }

    await saveExtensions();
    loadExtensions();
  } catch (e) {
    showToast('Uninstall error: ' + e, 'error');
  }
}

async function uninstallStandaloneExtension(browser, extId) {
  const ok = await showConfirm(
    `Uninstall this extension from ${browser}?\n\n${extId}`,
    { title: 'Uninstall Extension', yesText: 'Uninstall', noText: 'Cancel' }
  );
  if (!ok) {
    return;
  }

  try {
    const succeeded = await runExtensionUninstall([{ browser, id: extId }], 'Extension uninstalled');
    if (!succeeded) return;
    loadExtensions();
  } catch (e) {
    showToast('Uninstall error: ' + e, 'error');
  }
}

async function loadAutoUpdateStatus() {
  const toggle = document.getElementById('auto-update-toggle');
  const label = document.getElementById('auto-update-status');
  if (!toggle) return;
  try {
    const res = await fetch('/api/auto-update/status');
    const data = await res.json();
    if (data && !data.error) {
      toggle.checked = !!data.enabled;
      if (label) label.innerText = (data.enabled ? 'Enabled' : 'Disabled') + (data.mode ? ` (${data.mode})` : '');
    }
  } catch (e) {
    if (label) label.innerText = 'Status unavailable';
  }
}

async function toggleAutoUpdate() {
  const toggle = document.getElementById('auto-update-toggle');
  if (!toggle) return;
  const enabled = !!toggle.checked;
  try {
    const res = await fetch('/api/auto-update/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled })
    });
    const data = await res.json();
    if (data.error) {
      showToast(data.error, 'error');
      toggle.checked = !enabled;
      return;
    }
    showToast(enabled ? 'Auto-update enabled' : 'Auto-update disabled', 'success');
    loadAutoUpdateStatus();
  } catch (e) {
    showToast('Toggle failed: ' + e, 'error');
    toggle.checked = !enabled;
  }
}

async function startInitFromZip() {
  // Use native folder picker if available, otherwise prompt for path
  let zipPath = null;
  try {
    const browseRes = await fetch('/api/browse', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: 'file', title: 'Select configuration zip file' })
    });
    const bd = await browseRes.json();
    if (bd.cancelled) return;
    zipPath = bd.path || null;
  } catch (_) {}
  if (!zipPath) {
    zipPath = await showPrompt((typeof t === 'function') ? t('init_from_zip_prompt') : 'Path to configuration zip', '');
  }
  if (!zipPath) return;
  const bar = document.getElementById('init-progress-bar');
  const text = document.getElementById('init-progress-text');
  if (bar) bar.style.width = '2%';
  if (text) text.innerText = 'Starting...';

  try {
    const res = await fetch('/api/action/init-from-zip', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ zipPath })
    });
    const data = await res.json();
    if (data.error || !data.jobId) {
      showToast(data.error || 'Unable to start initialization', 'error');
      return;
    }
    trackInitJob(data.jobId, 'Initialization completed', 'Initialization finished with errors');
  } catch (e) {
    showToast('Init from zip failed: ' + e, 'error');
  }
}

function trackInitJob(jobId, successMessage, errorMessage) {
  const bar = document.getElementById('init-progress-bar');
  const text = document.getElementById('init-progress-text');
  const poll = async () => {
    const r = await fetch('/api/action/init-status/' + encodeURIComponent(jobId));
    const s = await r.json();
    const pct = Math.max(0, Math.min(100, s.progress || 0));
    if (bar) bar.style.width = pct + '%';
    if (text) text.innerText = (s.message || '') + ` (${pct}%)`;
    if (s.done) {
      if (s.ok) showToast(successMessage, 'success');
      else showToast(errorMessage, 'error');
      loadSharedConfigStatus();
      loadDotfilesStatus();
      return;
    }
    setTimeout(poll, 1500);
  };
  setTimeout(poll, 700);
}

async function startInitFromShared() {
  const ok = await showConfirm((typeof t === 'function') ? t('shared_confirm_init') : 'Initialize this machine from the shared drive now?');
  if (!ok) return;
  const bar = document.getElementById('init-progress-bar');
  const text = document.getElementById('init-progress-text');
  if (bar) bar.style.width = '2%';
  if (text) text.innerText = 'Starting...';

  try {
    const res = await fetch('/api/action/init-from-shared', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    const data = await res.json();
    if (data.error || !data.jobId) {
      showToast(data.error || 'Unable to start initialization', 'error');
      return;
    }
    trackInitJob(
      data.jobId,
      (typeof t === 'function') ? t('shared_init_done') : 'Shared-drive initialization completed',
      (typeof t === 'function') ? t('shared_init_failed') : 'Shared-drive initialization finished with errors'
    );
  } catch (e) {
    showToast('Init from shared drive failed: ' + e, 'error');
  }
}

// --- ENV STATUS & INIT
async function openEnvPath(path) {
  try {
    await fetch('/api/open-path', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path }) });
  } catch (e) { console.warn('openEnvPath failed', e); }
}

async function checkEnvStatus() {
  const banner = document.getElementById('env-status-banner');
  if (!banner) return;
  try {
    const [res, locRes] = await Promise.all([
      fetch('/api/env/exists'),
      fetch('/api/env/location')
    ]);
    const data = await res.json();
    const loc = await locRes.json();
    const envPath = (loc && loc.path) ? loc.path : '';
    const folderPath = (loc && loc.dir) ? loc.dir : '';
    const safeEnvPath = envPath.replace(/'/g, "\\'");
    const safeFolderPath = folderPath.replace(/'/g, "\\'");
    const revealBtn = envPath ? ` <button class="secondary" onclick="openEnvPath('${safeEnvPath}')" style="margin-left:8px;font-size:12px;padding:3px 8px;">&#128065; ${folderPath}</button>` : '';
    if (data.exists) {
      banner.style.display = 'block';
      banner.style.background = '#e6f4ea';
      banner.style.color = '#1a7f37';
      banner.innerHTML = '&#10003; ' + t('env_file_exists') + revealBtn;
    } else {
      banner.style.display = 'block';
      banner.style.background = '#fff8e1';
      banner.style.color = '#8a6d00';
      banner.innerHTML = '&#9888; ' + t('env_file_missing') + revealBtn + ' <button onclick="initEnv()" style="margin-left:12px;">' + t('init_config') + '</button>';
    }
  } catch (e) { console.warn('checkEnvStatus failed', e); }
}

async function initEnv() {
  try {
    const res = await fetch('/api/env/init', { method: 'POST' });
    const data = await res.json();
    if (data.error) {
      showToast(t('init_failed') + ': ' + data.error, 'error');
    } else {
      showToast(t('init_success'), 'success');
      checkEnvStatus();
      loadEnv();
    }
  } catch (e) {
    showToast(t('init_failed') + ': ' + e, 'error');
  }
}

async function resetEnv() {
  if (!await showConfirm(t('reset_confirm'))) return;
  try {
    const res = await fetch('/api/env/init', { method: 'POST' });
    const data = await res.json();
    if (data.error) {
      showToast(t('reset_failed') + ': ' + data.error, 'error');
    } else {
      showToast(t('reset_success'), 'success');
      loadEnv();
    }
  } catch (e) {
    showToast(t('reset_failed') + ': ' + e, 'error');
  }
}

// --- ENV FORM
async function loadEnv() {
  checkEnvStatus();
  const res = await fetch('/api/env');
  const data = await res.json();
  const container = document.getElementById('env-form');
  if (!container) return;
  container.innerHTML = '';
  let list = data && Array.isArray(data) && data.length ? data : [
    { key: 'SYNC_DIR', value: '', desc: '' },
    { key: 'PACKAGES_CONF_DIR', value: '', desc: '' },
    { key: 'OBSIDIAN_VAULT', value: '', desc: '' },
    { key: 'VSCODE_CONFIG', value: '', desc: '' },
    { key: 'ENABLE_DOTFILES_SYNC', value: 'false', desc: '' },
    { key: 'DOTFILES_SYNC_MODE', value: 'drive', desc: '' },
    { key: 'WIFI_KDBX_DB', value: '', desc: '' },
    { key: 'WIFI_KDBX_GROUP', value: 'Wifi', desc: '' },
    { key: 'WIFI_KDBX_KEY_FILE', value: '', desc: '' },
    { key: 'WIFI_KDBX_ASK_PASS', value: '1', desc: '' },
    { key: 'AUTO_UPDATE_HOUR', value: '21', desc: '' },
    { key: 'AUTO_UPDATE_MINUTE', value: '0', desc: '' }
  ];

  function parseDeclaredType(declared) {
    if (!declared) return null;
    const d = declared.toLowerCase();
    // Check for explicit mode in type declaration
    if (d.indexOf('file') !== -1) return { type: 'path', mode: 'file' };
    if (d.indexOf('dir') !== -1 || d.indexOf('folder') !== -1) return { type: 'path', mode: 'dir' };
    if (d.indexOf('path') !== -1) return { type: 'path', mode: 'dir' }; // default path to dir
    
    const enumMatch = declared.match(/enum\s*\(([^)]+)\)/i);
    if (enumMatch) return { type: 'enum', options: enumMatch[1].split(',').map(s => s.trim()).filter(Boolean) };
    const egMatch = declared.match(/e\.g\.\s*[:\-]?\s*(.+)/i);
    if (egMatch) {
      const quoted = Array.from(egMatch[1].matchAll(/"([^\"]+)"/g)).map(m => m[1]);
      if (quoted && quoted.length) return { type: 'enum', options: quoted };
      const parts = egMatch[1].split(',').map(s => s.replace(/["'\u201C\u201D]/g, '').trim()).filter(Boolean);
      if (parts.length) return { type: 'enum', options: parts };
    }
    if (d.indexOf('bool') !== -1 || d.indexOf('boolean') !== -1) return { type: 'boolean' };
    if (d.indexOf('number') !== -1 || d.indexOf('int') !== -1 || d.indexOf('hour') !== -1 || d.indexOf('minute') !== -1) return { type: 'number' };
    if (d.indexOf('enum') !== -1) return { type: 'enum' };
    return { type: 'string' };
  }

  function inferType(key, value) {
    const k = key.toUpperCase();
    const v = (value || '').toString().toLowerCase();
    if (/(_DIR|_PATH|_FILE|VAULT|CONFIG|DB|KEY_FILE)/i.test(k)) {
      // Explicit file indicators
      if (/_FILE$/i.test(k) || /_KEY_FILE$/i.test(k) || /KDBX_DB$/i.test(k)) return { type: 'path', mode: 'file' };
      // Explicit directory indicators
      if (/_DIR$/i.test(k) || /_DIR\b/i.test(k) || /VAULT|CONFIG/i.test(k)) return { type: 'path', mode: 'dir' };
      // PATH without specific suffix defaults to directory (most common case)
      return { type: 'path', mode: 'dir' };
    }
    if (v === 'true' || v === 'false') return { type: 'boolean' };
    if ((v === '0' || v === '1') && (/^ENABLE_|_ENABLED$|_ASK_PASS$|^USE_/.test(k))) return { type: 'boolean' };
    if (k.match(/(HOUR|MINUTE|PORT|COUNT|NUM|SIZE|SECONDS|DAYS)/)) return { type: 'number' };
    if (/^\d+$/.test(v)) return { type: 'number' };
    return { type: 'string' };
  }

  const processed = new Set();
  for (let i = 0; i < list.length; i++) {
    if (processed.has(i)) continue;
    const item = list[i];
    const key = item.key;
    const val = item.value == null ? '' : item.value;
    const desc = item.desc || '';

    // special-case combined hour/minute
    if (key === 'AUTO_UPDATE_HOUR') {
      let minuteIndex = -1;
      for (let j = 0; j < list.length; j++) if (list[j].key === 'AUTO_UPDATE_MINUTE') { minuteIndex = j; break; }
      const hourVal = val || '21';
      const minuteVal = (minuteIndex !== -1 && list[minuteIndex].value != null) ? list[minuteIndex].value : '0';
      const div = document.createElement('div'); div.className = 'env-item';
      let hourOpts = '';
      for (let h = 0; h < 24; h++) { const s = h.toString(); hourOpts += `<option value="${s}" ${s === hourVal ? 'selected' : ''}>${s.padStart(2, '0')}</option>`; }
      let minOpts = '';
      for (let m = 0; m < 60; m++) { const s = m.toString(); minOpts += `<option value="${s}" ${s === minuteVal ? 'selected' : ''}>${s.padStart(2, '0')}</option>`; }
      div.innerHTML = `\n<label class="env-label">AUTO_UPDATE_HOUR / AUTO_UPDATE_MINUTE</label>\n<div class="env-desc">${desc}</div>\n<div style="display:flex;gap:8px;align-items:center;">\n<select data-key="AUTO_UPDATE_HOUR">${hourOpts}</select>\n<select data-key="AUTO_UPDATE_MINUTE">${minOpts}</select>\n</div>`;
      container.appendChild(div);
      processed.add(i); if (minuteIndex !== -1) processed.add(minuteIndex); continue;
    }

    let info = item.type ? parseDeclaredType(item.type) : null;
    if (!info) info = inferType(key, val);

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
      const ph = (item.examples && item.examples.length) ? item.examples[0] : '';
      const browseText = (typeof t === 'function') ? t('browse') : 'Browse';
      const safeVal = val.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      inputHtml = `<div style="display:flex;gap:8px;align-items:center;"><input type="text" data-key="${key}" value="${safeVal}" placeholder="${ph}" style="flex:1"><button type="button" class="secondary" data-browse-for="${key}" data-path-mode="${info.mode || 'any'}">${browseText}</button></div>`;
    } else if (info.type === 'enum') {
      const opts = info.options || [];
      if (opts.length) inputHtml = `<select data-key="${key}">${opts.map(o => `<option value="${o}" ${o === val ? 'selected' : ''}>${o}</option>`).join('')}</select>`;
      else inputHtml = `<input type="text" data-key="${key}" value="${val}">`;
    } else {
      const ph = (item.examples && item.examples.length) ? item.examples[0] : '';
      inputHtml = `<input type="text" data-key="${key}" value="${val}" placeholder="${ph}">`;
    }

    const div = document.createElement('div'); div.className = 'env-item';
    div.innerHTML = `\n<label class="env-label">${key}</label>\n<div class="env-desc">${desc}</div>\n${inputHtml}`;
    container.appendChild(div);
    processed.add(i);
  }

  // browse handlers
  container.querySelectorAll('button[data-browse-for]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const key = btn.dataset.browseFor;
      const input = container.querySelector(`input[data-key="${key}"]`);
      if (!input) return;
      
      // Prefer declared mode from button (set during rendering)
      const declaredMode = btn.dataset.pathMode;
      // Explicit file detection
      const isFile = declaredMode === 'file';
      // Default to directory if mode is 'dir' or 'any' (most settings are directories)
      const isDir = declaredMode === 'dir' || declaredMode === 'any' || !isFile;

      // Log for debugging
      if (window.logger) {
        window.logger.info(`Browse clicked: key=${key}, mode=${declaredMode}, isFile=${isFile}, isDir=${isDir}`);
      }

      // 1) Prefer native dialogs in packaged app (pywebview)
      if (window.pywebview && window.pywebview.api) {
        try {
          if (isFile && typeof window.pywebview.api.open_file === 'function') {
            const path = await window.pywebview.api.open_file(t('select_file_for', {key}) || `Select file for ${key}`);
            if (path) { input.value = path; return; }
          } else if (isDir && typeof window.pywebview.api.open_dir === 'function') {
            const path = await window.pywebview.api.open_dir(t('select_folder_for', {key}) || `Select folder for ${key}`);
            if (path) { input.value = path; return; }
          }
        } catch (err) { 
          console.warn('pywebview dialog failed:', err);
        }
      }

      // 2) Use backend native OS picker (osascript on macOS) — returns full path
      try {
        const browseTitle = isFile
          ? ((typeof t === 'function') ? t('select_file_for', { key }) : `Select file for ${key}`)
          : ((typeof t === 'function') ? t('select_folder_for', { key }) : `Select folder for ${key}`);
        const browseRes = await fetch('/api/browse', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mode: isFile ? 'file' : 'dir', title: browseTitle })
        });
        const browseData = await browseRes.json();
        if (browseData.path) { input.value = browseData.path; return; }
        if (browseData.cancelled) return;  // user dismissed dialog
        // If error or not_supported, fall through to manual prompt
      } catch (err) {
        console.warn('Backend browse failed:', err);
      }

      // 3) Fallback: manual prompt
      const chosen = await showPrompt((typeof t === 'function') ? t('enter_path_for', { key: key }) : ('Enter path for ' + key), input.value || '');
      if (chosen !== null) input.value = chosen;
    });
  });
}

async function saveEnv() {
  const inputs = document.querySelectorAll('#env-form input, #env-form select');
  const data = {};
  inputs.forEach(i => {
    const key = i.dataset.key; if (!key) return;
    if (i.type === 'checkbox') data[key] = i.checked ? 'true' : 'false';
    else if (i.type === 'number') data[key] = i.value.toString();
    else data[key] = i.value;
  });
  try {
    const res = await fetch('/api/env', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
    const result = await res.json();
    if (result.error) {
      showToast('Save failed: ' + result.error, 'error');
      return;
    }
    window.logger && window.logger.info && window.logger.info('Env saved to ' + (result.path || '.env.local'), data);
    showToast(t('settings_saved') + (result.path ? ' → ' + result.path : ''), 'success');
    await loadEnv();  // Refresh form to confirm saved values
  } catch (e) {
    showToast('Save failed: ' + e, 'error');
  }
}

// --- Packages
async function loadPackages() {
  const listEl = document.getElementById('pkg-list'); if (!listEl) return;
  const loadingHtml = `<p>${(typeof t === 'function') ? t('loading') : 'Loading...'}</p>`;
  listEl.innerHTML = loadingHtml;
  try {
    const res = await fetch('/api/packages?withAvailability=1');
    if (!res.ok) { listEl.innerHTML = '<p>Error loading packages (HTTP ' + res.status + ')</p>'; return; }
    const data = await res.json();
    if (!Array.isArray(data) || data.length === 0) {
      listEl.innerHTML = '<p>' + ((typeof t === 'function') ? t('no_packages') : 'No configured packages found. Run "Import Installed Packages" from the Dashboard.') + '</p>';
      return;
    }
    let html = `<table><thead><tr><th style="width:50px">Icon</th><th>Name (Mac)</th><th>Name (Win)</th><th>Name (Linux)</th><th>Type</th><th>Desc</th><th>Actions</th></tr></thead><tbody>`;
    let rows = '';
    for (const p of data) {
      let iconName = p.mac; if (!iconName || iconName == '-') iconName = p.win;
      const imgId = 'icon-' + (p.mac || p.win || '').replace(/[^a-zA-Z0-9]/g, '');
      const linux = (p.linux && p.linux !== '') ? p.linux : '-';
      const appName = (p.mac && p.mac !== '-') ? p.mac : ((p.win && p.win !== '-') ? p.win : linux);
      const appArg = JSON.stringify(appName || '');
      rows += `<tr><td><img id="${imgId}" src="" alt="" style="width:32px;height:32px;border-radius:6px;background:#eee;"></td><td>${p.mac}</td><td>${p.win}</td><td>${linux}</td><td>${p.type}</td><td>${p.desc}</td><td><button style="font-size:10px; padding:4px 8px;" onclick="updatePackage(${appArg})">Update</button> <button class="secondary" style="font-size:10px; padding:4px 8px;" onclick="removePackage(${appArg})">Remove</button></td></tr>`;
      fetchIcon(imgId, iconName);
    }
    listEl.innerHTML = html + rows + '</tbody></table>';
  } catch (err) {
    listEl.innerHTML = '<p>Failed to load packages: ' + (err && err.message ? err.message : err) + '</p>';
    console.error('loadPackages error', err);
  }
}

async function fetchIcon(imgId, name) { if (!name || name == '-') return; try { const res = await fetch('/api/icon?name=' + encodeURIComponent(name)); const d = await res.json(); if (d.url) document.getElementById(imgId).src = d.url; } catch (e) {} }

async function updatePackage(app) {
  if (!app || app === '-') return;
  showToast('Updating ' + app + '...', 'info');
  try {
    const res = await fetch('/api/packages/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ app })
    });
    const data = await res.json();
    if (data.error || data.code !== 0) showToast('Update failed for ' + app, 'error');
    else showToast('Updated ' + app, 'success');
  } catch (e) {
    showToast('Update failed: ' + e, 'error');
  }
}

async function removePackage(app) {
  if (!app || app === '-') { showToast('No package identifier available for removal.', 'warn'); return; }
  if (!await showConfirm('Remove ' + app + ' ?')) return;
  showToast('Removing ' + app + '...', 'info');
  try {
    const res = await fetch('/api/packages/remove', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ app, runUninstall: true })
    });
    const data = await res.json();
    if (data.error) {
      showToast('Remove failed for ' + app + ': ' + data.error, 'error');
      return;
    }

    const removed = Number(data.removed || 0);
    if (removed > 0) {
      showToast('Removed ' + app + ' from package list.', 'success');
      await loadPackages();
    } else {
      showToast(app + ' was not present in package list.', 'warn');
    }

    if (typeof data.code === 'number' && data.code !== 0) {
      showToast('Uninstall command returned code ' + data.code + ' (config entry removed).', 'warn');
    }
    if (data.warning) {
      showToast(data.warning, 'warn');
    }
  } catch (e) {
    showToast('Remove failed: ' + e, 'error');
  }
}

// --- Actions
async function runUpdate() {
  const btn = document.getElementById('btn-update');
  const log = document.getElementById('update-log');
  const out = document.getElementById('update-output');
  if (btn) { btn.disabled = true; var originalText = btn.innerText; btn.innerText = (typeof t === 'function') ? t('running') : 'Running…'; }
  if (out) out.style.display = 'block';
  if (log) log.innerText = (typeof t === 'function') ? t('starting_update') : 'Starting update…';
  try {
    const res = await fetch('/api/action/update', { method: 'POST' });
    if (!res.ok) { if (log) log.innerText = 'Server error: HTTP ' + res.status; return; }
    const data = await res.json();
    if (data.error) {
      if (log) log.innerText = 'Error: ' + data.error;
      showToast('Update failed: ' + data.error, 'error');
    } else {
      if (log) log.innerText = 'Exit code: ' + data.code + '\n\n' + (data.stdout || '') + (data.stderr ? '\nSTDERR:\n' + data.stderr : '');
      if (data.code === 0) showToast('Update completed successfully', 'success');
      else showToast('Update finished with errors (exit ' + data.code + ')', 'warn');
    }
  } catch (e) {
    if (log) log.innerText = 'Request failed: ' + e;
    showToast('Update request failed', 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.innerText = originalText; }
  }
}

async function importInstalled() {
  const btn = document.querySelector('button[onclick="importInstalled()"]');
  const originalText = btn ? btn.innerText : '';
  if (btn) { btn.disabled = true; btn.innerText = (typeof t === 'function') ? t('running') : 'Running…'; }
  showToast((typeof t === 'function') ? t('import_started') : 'Scanning installed packages…', 'info');
  try {
    const res = await fetch('/api/action/import-installed', { method: 'POST' });
    if (!res.ok) { showToast('Server error: HTTP ' + res.status, 'error'); return; }
    const data = await res.json();
    if (data.error) {
      showToast('Import error: ' + data.error, 'error');
    } else if (data.code === 0 || data.code == null) {
      showToast((typeof t === 'function') ? t('import_done') : 'Import complete — check logs for details', 'success');
      await loadPackages();
    } else {
      showToast('Import finished with errors (exit ' + data.code + ')', 'warn');
    }
  } catch (e) {
    showToast('Import request failed: ' + e, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.innerText = originalText; }
  }
}

async function exportConfig() {
  const btn = document.querySelector('button[onclick="exportConfig()"]');
  const originalText = btn ? btn.innerText : '';
  if (btn) { btn.disabled = true; btn.innerText = (typeof t === 'function') ? t('running') : 'Running'; }
  try {
    // 1. Fetch default filename suggestion/path
    const defaultRes = await fetch('/api/export/default-path');
    const defaultData = await defaultRes.json();
    const suggestedPath = (defaultData && defaultData.default_path) ? defaultData.default_path : '';
    const defaultFilename = (defaultData && defaultData.default_path)
      ? defaultData.default_path.split('/').pop()
      : 'ok_computer_export.zip';

    // 2. Try native folder picker
    const browseRes = await fetch('/api/browse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mode: 'dir',
        title: (typeof t === 'function') ? t('export_config_choose_folder') : 'Choose export folder'
      })
    });
    const browseData = await browseRes.json();

    let outputPath = '';
    if (!browseData.cancelled && !browseData.error && browseData.path) {
      outputPath = browseData.path + '/' + defaultFilename;
    } else {
      // 3. Fallback: manual path input (works everywhere)
      outputPath = await showPrompt(
        (typeof t === 'function') ? t('export_config_path_prompt') : 'Export zip path',
        suggestedPath
      );
      if (!outputPath) {
        return;
      }
    }

    // 4. Trigger export
    const res = await fetch('/api/action/export-config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ outputPath })
    });
    const data = await res.json();
    if (data.error) {
      showToast(data.error, 'error');
      return;
    }
    const msg = ((typeof t === 'function') ? t('export_config_done') : 'Configuration exported')
      + ' → ' + (data.path || outputPath);
    showToast(msg, 'success');
    if (window.logger) window.logger.info('Configuration export done', data);
  } catch (e) {
    showToast('Export failed: ' + e, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.innerText = originalText; }
  }
}

function dotfilesPresenceLabel(item) {
  if (item.linked) return (typeof t === 'function') ? t('dotfiles_state_linked') : 'Linked';
  if (item.present) return (typeof t === 'function') ? t('dotfiles_state_present') : 'Present';
  return (typeof t === 'function') ? t('dotfiles_state_missing') : 'Missing';
}

function sharedConfigPresenceLabel(item, kind) {
  const present = kind === 'shared' ? item.shared_present : item.local_present;
  return present
    ? ((typeof t === 'function') ? t('shared_config_present') : 'Present')
    : ((typeof t === 'function') ? t('shared_config_missing') : 'Missing');
}

async function loadSharedConfigStatus() {
  const container = document.getElementById('shared-config-panel');
  if (!container) return;
  container.innerHTML = (typeof t === 'function') ? t('loading') : 'Loading...';
  try {
    const res = await fetch('/api/shared-config/status');
    const data = await res.json();
    if (data.error) {
      container.innerHTML = `<div style="color:#b42318;">${escapeHtml(data.error)}</div>`;
      return;
    }

    const syncState = !data.sync_dir_configured
      ? ((typeof t === 'function') ? t('shared_sync_missing') : 'SYNC_DIR is not configured.')
      : data.sync_dir_exists
        ? `${(typeof t === 'function') ? t('shared_sync_configured') : 'Shared drive configured'}: ${escapeHtml(data.shared_root_dir || data.sync_dir || '')}`
        : `${(typeof t === 'function') ? t('shared_sync_invalid') : 'SYNC_DIR does not exist'}: ${escapeHtml(data.sync_dir || '')}`;

    const trackedRows = (data.tracked || []).map((item) => `<tr>
      <td>${escapeHtml(item.name || '')}</td>
      <td>${escapeHtml(sharedConfigPresenceLabel(item, 'local'))}</td>
      <td>${escapeHtml(sharedConfigPresenceLabel(item, 'shared'))}</td>
    </tr>`).join('');

    container.innerHTML = `
      <div style="padding:10px 12px; border-radius:10px; background:#fff; color:#333; font-size:13px; margin-bottom:10px;">${syncState}</div>
      <div style="font-size:13px; color:#555; line-height:1.5; margin-bottom:12px;">${(typeof t === 'function') ? t('shared_config_intro') : 'Use the shared drive as the source of truth for packages.conf, extensions.conf and optional system_settings.conf. Sync publishes local changes; Restore pulls them back into the local runtime; Init from shared drive restores and then runs installation.'}</div>
      <div style="display:flex; flex-wrap:wrap; gap:8px; margin-bottom:12px;">
        <button class="secondary" onclick="runSharedConfigAction('sync')">${(typeof t === 'function') ? t('shared_action_sync') : 'Sync local configs to shared drive'}</button>
        <button class="secondary" onclick="runSharedConfigAction('restore')">${(typeof t === 'function') ? t('shared_action_restore') : 'Restore shared configs locally'}</button>
        <button onclick="startInitFromShared()">${(typeof t === 'function') ? t('shared_action_init') : 'Initialize from shared drive'}</button>
        <button class="secondary" onclick="loadSharedConfigStatus()">${(typeof t === 'function') ? t('refresh') : 'Refresh'}</button>
      </div>
      <div style="display:flex; gap:18px; flex-wrap:wrap; font-size:13px; color:#555; margin-bottom:12px;">
        <div>${(typeof t === 'function') ? t('shared_tracked_count') : 'Tracked'}: <strong>${data.tracked_count || 0}</strong></div>
        <div>${(typeof t === 'function') ? t('shared_local_count') : 'Local'}: <strong>${data.local_count || 0}</strong></div>
        <div>${(typeof t === 'function') ? t('shared_remote_count') : 'Shared'}: <strong>${data.shared_count || 0}</strong></div>
      </div>
      <details>
        <summary style="cursor:pointer; font-size:13px; color:#444;">${(typeof t === 'function') ? t('shared_tracked_list') : 'Tracked shared configuration files'}</summary>
        <div style="margin-top:10px; overflow:auto;">
          <table>
            <thead>
              <tr>
                <th>${(typeof t === 'function') ? t('shared_column_name') : 'File'}</th>
                <th>${(typeof t === 'function') ? t('shared_column_local') : 'Local state'}</th>
                <th>${(typeof t === 'function') ? t('shared_column_remote') : 'Shared state'}</th>
              </tr>
            </thead>
            <tbody>${trackedRows}</tbody>
          </table>
        </div>
      </details>
    `;
  } catch (e) {
    container.innerHTML = `<div style="color:#b42318;">Shared config error: ${escapeHtml(String(e))}</div>`;
  }
}

async function loadDotfilesStatus() {
  const container = document.getElementById('dotfiles-panel');
  if (!container) return;
  container.innerHTML = (typeof t === 'function') ? t('loading') : 'Loading...';
  try {
    const res = await fetch('/api/dotfiles/status');
    const data = await res.json();
    if (data.error) {
      container.innerHTML = `<div style="color:#b42318;">${escapeHtml(data.error)}</div>`;
      return;
    }

    const syncState = !data.sync_dir_configured
      ? ((typeof t === 'function') ? t('dotfiles_sync_missing') : 'SYNC_DIR is not configured.')
      : data.sync_dir_exists
        ? `${(typeof t === 'function') ? t('dotfiles_sync_configured') : 'Shared folder configured'}: ${escapeHtml(data.sync_dir || '')}`
        : `${(typeof t === 'function') ? t('dotfiles_sync_invalid') : 'SYNC_DIR does not exist'}: ${escapeHtml(data.sync_dir || '')}`;
    const preferredWorkflow = data.preferred_workflow || 'drive';
    const driveSelected = preferredWorkflow === 'drive';
    const zipSelected = preferredWorkflow === 'zip';
    const setupRecommended = driveSelected && (data.linked_count || 0) === 0;

    const trackedRows = (data.tracked || []).map((item) => {
      const syncLabel = item.sync_present
        ? ((typeof t === 'function') ? t('dotfiles_sync_copy_present') : 'Shared copy available')
        : ((typeof t === 'function') ? t('dotfiles_sync_copy_missing') : 'No shared copy');
      const target = item.link_target ? `<div style="font-size:11px; color:#666; margin-top:4px;">${escapeHtml(item.link_target)}</div>` : '';
      return `<tr>
        <td>${escapeHtml(item.path || '')}${target}</td>
        <td>${escapeHtml(dotfilesPresenceLabel(item))}</td>
        <td>${escapeHtml(syncLabel)}</td>
      </tr>`;
    }).join('');

    container.innerHTML = `
      <div style="display:flex; flex-wrap:wrap; gap:8px; margin-bottom:12px;">
        <span style="background:#eef6ff; color:#0b4f8a; padding:6px 10px; border-radius:999px; font-size:12px;">${(typeof t === 'function') ? t('dotfiles_manual_mode') : 'Manual mode'}</span>
        <span style="background:#f5f5f7; color:#444; padding:6px 10px; border-radius:999px; font-size:12px;">${(typeof t === 'function') ? t('dotfiles_no_cron') : 'No cron'}</span>
        <span style="background:#f5f5f7; color:#444; padding:6px 10px; border-radius:999px; font-size:12px;">ZIP ${(typeof t === 'function') ? t('dotfiles_zip_supported') : 'export and import supported'}</span>
      </div>
      <div style="margin-bottom:12px;">
        <div style="font-size:13px; color:#555; margin-bottom:8px;">${(typeof t === 'function') ? t('dotfiles_workflow_label') : 'Preferred workflow'}</div>
        <div style="display:flex; flex-wrap:wrap; gap:8px;">
          <button ${driveSelected ? '' : 'class="secondary"'} onclick="setPreferredDotfilesWorkflow('drive')">${(typeof t === 'function') ? t('dotfiles_workflow_drive') : 'Drive sync via shared folder'}</button>
          <button ${zipSelected ? '' : 'class="secondary"'} onclick="setPreferredDotfilesWorkflow('zip')">${(typeof t === 'function') ? t('dotfiles_workflow_zip') : 'ZIP export/import snapshots'}</button>
        </div>
      </div>
      <div style="font-size:13px; color:#555; line-height:1.5; margin-bottom:12px;">
        <div>${driveSelected
          ? ((typeof t === 'function') ? t('dotfiles_explainer_drive_selected') : 'Drive workflow selected: use SYNC_DIR as your shared folder. After Setup creates symlinks, your cloud client keeps those files in sync automatically.')
          : ((typeof t === 'function') ? t('dotfiles_explainer_manual') : 'Use SYNC_DIR as your shared folder, then run Init, Setup, Sync or Restore manually.')}</div>
        <div style="margin-top:6px;">${zipSelected
          ? ((typeof t === 'function') ? t('dotfiles_explainer_zip_selected') : 'ZIP workflow selected: use Export Configuration to create a snapshot, then Initialize from zip on the target machine.')
          : ((typeof t === 'function') ? t('dotfiles_explainer_zip') : 'Export Configuration also snapshots tracked dotfiles in the ZIP. Initialize from zip restores them on the target machine.')}</div>
      </div>
      <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(260px, 1fr)); gap:12px; margin-bottom:12px;">
        <div style="padding:12px; border-radius:12px; background:${driveSelected ? '#eef6ff' : '#f5f5f7'}; border:1px solid ${driveSelected ? '#c9def5' : '#e5e7eb'};">
          <div style="font-weight:600; margin-bottom:8px;">${(typeof t === 'function') ? t('dotfiles_workflow_drive') : 'Drive sync via shared folder'}</div>
          <div style="font-size:13px; color:#555; line-height:1.5; margin-bottom:10px;">${(typeof t === 'function') ? t('dotfiles_drive_help') : 'Best when you use OneDrive, Dropbox or Synology Drive and want a living shared source of truth. Once Setup creates symlinks, the cloud client handles the automatic sync.'}</div>
          <div style="padding:10px 12px; border-radius:10px; background:#fff; color:#333; font-size:13px; margin-bottom:10px;">${syncState}</div>
          ${setupRecommended ? `<div style="padding:10px 12px; border-radius:10px; background:#fff8e6; color:#7a4b00; font-size:13px; margin-bottom:10px; border:1px solid #f2d28b;">${(typeof t === 'function') ? t('dotfiles_setup_recommended') : 'Recommended next step: run Setup symlinks. After that, changes made in your home dotfiles are written directly into the shared drive folder.'}</div>` : ''}
          <div style="display:flex; flex-wrap:wrap; gap:8px;">
            <button class="secondary" onclick="runDotfilesAction('init')">${(typeof t === 'function') ? t('dotfiles_action_init') : 'Init shared folder'}</button>
            <button onclick="runDotfilesAction('setup')">${(typeof t === 'function') ? t('dotfiles_action_setup') : 'Setup symlinks'}</button>
            <button class="secondary" onclick="runDotfilesAction('sync')">${(typeof t === 'function') ? t('dotfiles_action_sync') : 'Sync to shared folder'}</button>
            <button class="secondary" onclick="runDotfilesAction('restore')">${(typeof t === 'function') ? t('dotfiles_action_restore') : 'Restore from shared folder'}</button>
          </div>
        </div>
        <div style="padding:12px; border-radius:12px; background:${zipSelected ? '#eef6ff' : '#f5f5f7'}; border:1px solid ${zipSelected ? '#c9def5' : '#e5e7eb'};">
          <div style="font-weight:600; margin-bottom:8px;">${(typeof t === 'function') ? t('dotfiles_workflow_zip') : 'ZIP export/import snapshots'}</div>
          <div style="font-size:13px; color:#555; line-height:1.5; margin-bottom:10px;">${(typeof t === 'function') ? t('dotfiles_zip_help') : 'Best for backup, migration to another machine, or occasional restore without a shared drive.'}</div>
          <div style="display:flex; flex-wrap:wrap; gap:8px;">
            <button class="secondary" onclick="exportConfig()">${(typeof t === 'function') ? t('export_config') : 'Export Configuration'}</button>
            <button class="secondary" onclick="startInitFromZip()">${(typeof t === 'function') ? t('init_from_zip') : 'Initialize from zip file'}</button>
          </div>
        </div>
      </div>
      <div style="display:flex; flex-wrap:wrap; gap:8px; margin-bottom:12px;">
        <button class="secondary" onclick="loadDotfilesStatus()">${(typeof t === 'function') ? t('refresh') : 'Refresh'}</button>
      </div>
      <div style="display:flex; gap:18px; flex-wrap:wrap; font-size:13px; color:#555; margin-bottom:12px;">
        <div>${(typeof t === 'function') ? t('dotfiles_tracked_count') : 'Tracked'}: <strong>${data.tracked_count || 0}</strong></div>
        <div>${(typeof t === 'function') ? t('dotfiles_present_count') : 'Present locally'}: <strong>${data.present_count || 0}</strong></div>
        <div>${(typeof t === 'function') ? t('dotfiles_linked_count') : 'Linked'}: <strong>${data.linked_count || 0}</strong></div>
        <div>${(typeof t === 'function') ? t('dotfiles_synced_count') : 'Copied to shared folder'}: <strong>${data.synced_count || 0}</strong></div>
      </div>
      <details>
        <summary style="cursor:pointer; font-size:13px; color:#444;">${(typeof t === 'function') ? t('dotfiles_tracked_list') : 'Tracked dotfiles list'}</summary>
        <div style="margin-top:10px; overflow:auto;">
          <table>
            <thead>
              <tr>
                <th>${(typeof t === 'function') ? t('dotfiles_column_path') : 'Path'}</th>
                <th>${(typeof t === 'function') ? t('dotfiles_column_local') : 'Local state'}</th>
                <th>${(typeof t === 'function') ? t('dotfiles_column_shared') : 'Shared state'}</th>
              </tr>
            </thead>
            <tbody>${trackedRows}</tbody>
          </table>
        </div>
      </details>
    `;
  } catch (e) {
    container.innerHTML = `<div style="color:#b42318;">Dotfiles error: ${escapeHtml(String(e))}</div>`;
  }
}

async function setPreferredDotfilesWorkflow(mode) {
  try {
    const res = await fetch('/api/env', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ DOTFILES_SYNC_MODE: mode })
    });
    const data = await res.json();
    if (data.error) {
      showToast(data.error, 'error');
      return;
    }
    showToast((typeof t === 'function') ? t('dotfiles_workflow_saved') : 'Dotfiles workflow saved', 'success');
    await loadEnv();
    await loadDotfilesStatus();
  } catch (e) {
    showToast('Save failed: ' + e, 'error');
  }
}

async function runDotfilesAction(action) {
  const confirmationKeys = {
    init: 'dotfiles_confirm_init',
    setup: 'dotfiles_confirm_setup',
    restore: 'dotfiles_confirm_restore'
  };
  if (confirmationKeys[action]) {
    const ok = await showConfirm((typeof t === 'function') ? t(confirmationKeys[action]) : `Run dotfiles action: ${action}?`);
    if (!ok) return;
  }
  try {
    const res = await fetch('/api/action/dotfiles', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action })
    });
    const data = await res.json();
    if (data.error) {
      showToast(data.error, 'error');
      return;
    }
    showToast(data.message || ((typeof t === 'function') ? t('saved') : 'Saved'), 'success');
    loadDotfilesStatus();
  } catch (e) {
    showToast('Dotfiles failed: ' + e, 'error');
  }
}

async function runSharedConfigAction(action) {
  const confirmationKeys = {
    restore: 'shared_confirm_restore'
  };
  if (confirmationKeys[action]) {
    const ok = await showConfirm((typeof t === 'function') ? t(confirmationKeys[action]) : `Run shared config action: ${action}?`);
    if (!ok) return;
  }
  try {
    const res = await fetch('/api/action/shared-config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action })
    });
    const data = await res.json();
    if (data.error) {
      showToast(data.error, 'error');
      return;
    }
    showToast(data.message || ((typeof t === 'function') ? t('saved') : 'Saved'), 'success');
    loadSharedConfigStatus();
  } catch (e) {
    showToast('Shared config failed: ' + e, 'error');
  }
}

// --- Search
let _searchResults = [];
let _extensionSearchRows = [];

function _sanitizeExtField(v) {
  return (v || '').toString().replace(/\|/g, ' ').trim();
}

function _isSameExtensionLine(existing, candidate) {
  const a = (existing || '').split('|').map((x) => x.trim());
  const b = (candidate || '').split('|').map((x) => x.trim());
  if (!a.length || !b.length) return false;
  if (a[0] !== b[0]) return false;
  if (a[0] === 'all') {
    return (a[1] || '') === (b[1] || '') && (a[2] || '') === (b[2] || '');
  }
  return (a[1] || '') === (b[1] || '');
}

async function _appendExtensionLine(newLine) {
  const line = (newLine || '').trim();
  if (!line) return { ok: false, reason: 'empty' };
  const curRes = await fetch('/api/extensions');
  const cur = await curRes.json();
  if (!Array.isArray(cur)) return { ok: false, reason: 'invalid-current' };

  const lines = [];
  cur.forEach((item) => {
    if (item.raw) lines.push(item.raw);
    else if (item.mode === 'all') lines.push(['all', item.chrome || '', item.firefox || '', item.desc || ''].join('|'));
    else if (item.mode === 'chrome' || item.mode === 'firefox' || item.mode === 'arc') lines.push([item.mode, item.id || '', item.desc || ''].join('|'));
  });

  if (lines.some((l) => _isSameExtensionLine(l, line))) {
    return { ok: false, reason: 'duplicate' };
  }

  const updated = lines.concat([line]);
  const upd = await fetch('/api/extensions/update', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lines: updated })
  });
  const result = await upd.json();
  if (!result || result.error) {
    return { ok: false, reason: result && result.error ? result.error : 'update-failed' };
  }
  return { ok: true };
}

async function addExtensionFromSearch(idx) {
  const row = _extensionSearchRows[idx];
  if (!row) return;

  const descBase = _sanitizeExtField(`${row.name || ''}${row.publisher ? ` - ${row.publisher}` : ''}`) || 'Imported from search';
  const chromeId = (Array.from(row.chromeIds || [])[0] || '').trim();
  const firefoxSlug = (Array.from(row.firefoxSlugs || [])[0] || '').trim();

  let candidateLine = '';
  if (chromeId && firefoxSlug) {
    candidateLine = `all|${_sanitizeExtField(chromeId)}|${_sanitizeExtField(firefoxSlug)}|${descBase}`;
  } else if (chromeId) {
    candidateLine = `chrome|${_sanitizeExtField(chromeId)}|${descBase}`;
  } else if (firefoxSlug) {
    candidateLine = `firefox|${_sanitizeExtField(firefoxSlug)}|${descBase}`;
  }

  if (!candidateLine) {
    showToast('No valid extension identifier found for this row.', 'warn');
    return;
  }

  try {
    const added = await _appendExtensionLine(candidateLine);
    if (!added.ok && added.reason === 'duplicate') {
      showToast('Extension already present in install list.', 'info');
      return;
    }
    if (!added.ok) {
      showToast('Unable to add extension: ' + added.reason, 'error');
      return;
    }
    showToast('Extension added to install list.', 'success');
    loadExtensions();
  } catch (e) {
    showToast('Unable to add extension: ' + e, 'error');
  }
}

async function doSearch() {
  const q = (document.getElementById('search-input') || {}).value || '';
  const kind = (document.getElementById('search-kind') || {}).value || 'package';
  const btn = document.getElementById('search-btn');
  const resultsDiv = document.getElementById('search-results');
  if (!resultsDiv) return;
  if (!q.trim()) { resultsDiv.innerHTML = ''; return; }
  resultsDiv.innerHTML = `<span>${(typeof t === 'function') ? t('loading') : 'Searching\u2026'}</span>`;
  if (btn) btn.disabled = true;
  try {
    if (kind === 'extension') {
      const res = await fetch('/api/extensions/search?q=' + encodeURIComponent(q));
      const data = await res.json();
      const chrome = data.chrome || [];
      const firefox = data.firefox || [];

      // Load current configured extensions to mark already-added rows.
      const curExtRes = await fetch('/api/extensions');
      const curExt = await curExtRes.json();
      const existingChromeIds = new Set();
      const existingFirefoxSlugs = new Set();
      const existingAllPairs = new Set();
      if (Array.isArray(curExt)) {
        curExt.forEach((item) => {
          if (item && item.mode === 'all') {
            const ch = (item.chrome || '').trim();
            const ff = (item.firefox || '').trim();
            if (ch) existingChromeIds.add(ch);
            if (ff) existingFirefoxSlugs.add(ff);
            if (ch && ff) existingAllPairs.add(`${ch}::${ff}`);
          } else if (item && item.mode === 'chrome') {
            const ch = (item.id || '').trim();
            if (ch) existingChromeIds.add(ch);
          } else if (item && item.mode === 'firefox') {
            const ff = (item.id || '').trim();
            if (ff) existingFirefoxSlugs.add(ff);
          } else if (item && item.raw) {
            const parts = item.raw.split('|').map((x) => x.trim());
            if (parts[0] === 'all' && parts.length >= 3) {
              if (parts[1]) existingChromeIds.add(parts[1]);
              if (parts[2]) existingFirefoxSlugs.add(parts[2]);
              if (parts[1] && parts[2]) existingAllPairs.add(`${parts[1]}::${parts[2]}`);
            } else if (parts[0] === 'chrome' && parts.length >= 2 && parts[1]) {
              existingChromeIds.add(parts[1]);
            } else if (parts[0] === 'firefox' && parts.length >= 2 && parts[1]) {
              existingFirefoxSlugs.add(parts[1]);
            }
          }
        });
      }

      const normalize = (v) => (v || '').toString().trim().toLowerCase();
      const rowsByKey = new Map();

      const upsertRow = (item, source) => {
        const name = (item.name || item.id || item.slug || `${source}-extension`).toString().trim();
        const publisher = (item.publisher || '').toString().trim();
        const key = `${normalize(name)}::${normalize(publisher)}`;
        let row = rowsByKey.get(key);
        if (!row) {
          row = {
            name,
            publisher,
            chrome: false,
            firefox: false,
            chromeIds: new Set(),
            firefoxSlugs: new Set(),
            links: new Set()
          };
          rowsByKey.set(key, row);
        }

        if (source === 'chrome') {
          row.chrome = true;
          if (item.id) row.chromeIds.add(item.id);
        }
        if (source === 'firefox') {
          row.firefox = true;
          if (item.slug) row.firefoxSlugs.add(item.slug);
        }
        if (item.url) row.links.add(item.url);
      };

      chrome.forEach((c) => upsertRow(c, 'chrome'));
      firefox.forEach((f) => upsertRow(f, 'firefox'));

      const rows = Array.from(rowsByKey.values()).sort((a, b) => {
        const n = a.name.localeCompare(b.name);
        if (n !== 0) return n;
        return a.publisher.localeCompare(b.publisher);
      });
      _extensionSearchRows = rows;
      if (!rows.length) {
        resultsDiv.innerHTML = `<span style="color:#888">${(typeof t === 'function') ? t('no_results') : 'No results.'}</span>`;
        return;
      }
      const yes = '\u2705';
      const no = '<span style="color:#ccc">\u2014</span>';
      let html = `<table><thead><tr><th style="text-align:left">${(typeof t==='function')?t('package'):'Result'}</th><th style="text-align:left">Publisher</th><th style="text-align:center">Chrome</th><th style="text-align:center">Firefox</th><th style="text-align:left">Stores</th><th style="text-align:left">Identifiers</th><th></th></tr></thead><tbody>`;
      rows.forEach((r, i) => {
        const chromeIds = Array.from(r.chromeIds).join(', ');
        const ffSlugs = Array.from(r.firefoxSlugs).join(', ');
        let identifiers = '';
        if (chromeIds) identifiers += `Chrome: ${chromeIds}`;
        if (ffSlugs) identifiers += `${identifiers ? ' | ' : ''}Firefox: ${ffSlugs}`;
        const chromeIdFirst = Array.from(r.chromeIds)[0] || '';
        const ffSlugFirst = Array.from(r.firefoxSlugs)[0] || '';
        const chromeUrl = chromeIdFirst ? `https://chrome.google.com/webstore/detail/${chromeIdFirst}` : '';
        const firefoxUrl = ffSlugFirst ? `https://addons.mozilla.org/firefox/addon/${ffSlugFirst}/` : '';
        const alreadyAdded = (
          (chromeIdFirst && ffSlugFirst && existingAllPairs.has(`${chromeIdFirst}::${ffSlugFirst}`)) ||
          (chromeIdFirst && existingChromeIds.has(chromeIdFirst)) ||
          (ffSlugFirst && existingFirefoxSlugs.has(ffSlugFirst))
        );
        const stores = [
          chromeUrl ? `<a href="${chromeUrl}" target="_blank" rel="noopener noreferrer">Chrome Web Store</a>` : '',
          firefoxUrl ? `<a href="${firefoxUrl}" target="_blank" rel="noopener noreferrer">Firefox Add-ons</a>` : ''
        ].filter(Boolean).join(' | ');
        html += `<tr>
          <td><strong>${r.name}</strong></td>
          <td>${r.publisher || '<span style="color:#999">Unknown</span>'}</td>
          <td style="text-align:center">${r.chrome ? yes : no}</td>
          <td style="text-align:center">${r.firefox ? yes : no}</td>
          <td><span style="font-size:11px;color:#666">${stores || '-'}</span></td>
          <td><span style="font-size:11px;color:#666">${identifiers || '-'}</span></td>
          <td style="text-align:right;">
            ${alreadyAdded
              ? `<button style="font-size:11px" class="secondary" disabled>Added</button>`
              : `<button style="font-size:11px" onclick="addExtensionFromSearch(${i})">Add</button>`}
          </td>
        </tr>`;
      });
      html += '</tbody></table>';
      resultsDiv.innerHTML = html;
      return;
    }

    const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
    const data = await res.json();
    if (data.error) { resultsDiv.innerHTML = `<span style="color:red">${data.error}</span>`; return; }
    _searchResults = data.results || [];
    if (_searchResults.length === 0) {
      resultsDiv.innerHTML = `<span style="color:#888">${(typeof t === 'function') ? t('no_results') : 'No results.'}</span>`;
      return;
    }
    const yes = '\u2705';
    const no = '<span style="color:#ccc">\u2014</span>';
    const addLabel = (typeof t === 'function') ? t('add_to_list') : 'Add';
    const pkgLabel = (typeof t === 'function') ? t('package') : 'Package';
    let html = `<table><thead><tr>
      <th style="text-align:left">${pkgLabel}</th>
      <th style="text-align:center">Homebrew</th>
      <th style="text-align:center">Chocolatey</th>
      <th style="text-align:center">apt-get</th>
      <th></th>
    </tr></thead><tbody>`;
    _searchResults.forEach((r, i) => {
      const hb = r.homebrew ? yes : no;
      const ch = r.chocolatey ? yes : no;
      const ap = r.apt ? yes : no;
      const canAdd = r.homebrew || r.chocolatey || r.apt;
      html += `<tr>
        <td><strong>${r.name}</strong>${r.desc ? `<br><span style="font-size:11px;color:#888">${r.desc}</span>` : ''}</td>
        <td style="text-align:center">${hb}</td>
        <td style="text-align:center">${ch}</td>
        <td style="text-align:center">${ap}</td>
        <td style="text-align:right">${canAdd ? `<button style="font-size:11px" onclick="openAddPackageModal(${i})">${addLabel}</button>` : ''}</td>
      </tr>`;
    });
    html += '</tbody></table>';
    resultsDiv.innerHTML = html;
  } catch (e) {
    resultsDiv.innerHTML = `<span style="color:red">Error: ${e}</span>`;
  } finally {
    if (btn) btn.disabled = false;
  }
}

function openAddPackageModal(idx) {
  const pkg = _searchResults[idx];
  if (!pkg) return;
  const typeEl = document.getElementById('add-pkg-type');
  if (typeEl) typeEl.value = pkg.homebrew_type || 'brew';
  const macEl = document.getElementById('add-pkg-mac');
  if (macEl) macEl.value = (pkg.mac && pkg.mac !== '-') ? pkg.mac : '';
  const winEl = document.getElementById('add-pkg-win');
  if (winEl) winEl.value = (pkg.win && pkg.win !== '-') ? pkg.win : '';
  const descEl = document.getElementById('add-pkg-desc');
  if (descEl) descEl.value = pkg.desc || '';
  const modal = document.getElementById('add-pkg-modal');
  if (modal) modal.style.display = 'flex';
}

async function confirmAddPackage() {
  const typeEl = document.getElementById('add-pkg-type');
  const macEl  = document.getElementById('add-pkg-mac');
  const winEl  = document.getElementById('add-pkg-win');
  const descEl = document.getElementById('add-pkg-desc');
  const payload = {
    type: typeEl ? typeEl.value : 'brew',
    mac:  macEl  && macEl.value  ? macEl.value  : '-',
    win:  winEl  && winEl.value  ? winEl.value  : '-',
    desc: descEl ? descEl.value : ''
  };
  try {
    const res = await fetch('/api/packages/add', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    const modal = document.getElementById('add-pkg-modal');
    if (modal) modal.style.display = 'none';
    if (data.error) {
      showToast(data.error, 'error');
    } else {
      showToast((typeof t === 'function') ? t('pkg_added') : 'Package added to list \u2713', 'success');
    }
  } catch (e) {
    showToast('Error: ' + e, 'error');
  }
}

async function installApp(name) {
  if (!await showConfirm((typeof t === 'function')?t('install_confirm',{name:name}):`Install ${name}?`)) return;
  showToast((typeof t === 'function')?t('installing',{name:name}):`Installing ${name}`, 'info');
  try {
    const res = await fetch('/api/action/install', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ app: name }) });
    const data = await res.json();
    if (data.error) showToast('Install failed: ' + data.error, 'error'); else showToast('Install finished (see console for output)', 'success');
    console.log('install result', data);
  } catch (e) {
    showToast('Install request failed: ' + e, 'error');
    console.error(e);
  }
}

// --- Wifi export helper
async function promptWifiExport() {
  const envRes = await fetch('/api/env');
  const envData = await envRes.json() || [];
  let envMap = {};
  envData.forEach(e => envMap[e.key] = e.value);

  let dbPath = envMap['WIFI_KDBX_DB'] || '';
  dbPath = await showPrompt((typeof t === 'function')?t('enter_db_path'):'DB path', dbPath);
  if (!dbPath) return;
  const password = await showPrompt((typeof t === 'function')?t('enter_db_pass'):'DB password', '', { mask: true });
  if (!password) return;
  const btn = document.querySelector('button[onclick="promptWifiExport()"]');
  const originalText = btn ? btn.innerText : '';
  if (btn) { btn.innerText = (typeof t === 'function')?t('exporting'):'Exporting'; btn.disabled = true; }
  try {
    const res = await fetch('/api/action/wifi-export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ db: dbPath, password: password }) });
    const data = await res.json();
    if (data.error) {
      showToast('Error: ' + data.error, 'error');
    } else {
      if (data.code !== 0) showToast('Failed (Exit Code ' + data.code + ')', 'error');
      else showToast('Success: export finished', 'success');
      console.log('wifi-export output', data);
    }
  } catch (e) {
    showToast('Request failed: ' + e, 'error');
  } finally {
    if (btn) { btn.innerText = originalText; btn.disabled = false; }
  }
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

// duplicate/old action/search/install/prompt block removed (kept cleaned definitions above)
