# Test manuel : Boutons "Parcourir" / "Browse"

## Objectif
Valider que les boutons de sélection de fichiers/dossiers fonctionnent correctement et sont internationalisés.

## Prérequis
- Application buildée : `dist/ok_computer_ui.app`
- Lancer l'application

## Tests à effectuer

### 1. Vérification i18n
- [ ] **Français** : Ouvrir Settings → Les boutons affichent "Parcourir"
- [ ] **Anglais** : Changer la langue du système → Les boutons affichent "Browse"

### 2. Sélection de dossier (macOS native picker)

#### Test SYNC_DIR
1. Aller dans Settings
2. Cliquer sur "Parcourir" à côté de SYNC_DIR
3. **Attendu** : Un sélecteur de dossiers s'ouvre (Finder)
4. Sélectionner un dossier (ex: Documents)
5. **Attendu** : Le chemin complet apparaît dans le champ (ex: `/Users/nom/Documents`)

#### Test OBSIDIAN_VAULT
1. Cliquer sur "Parcourir" à côté de OBSIDIAN_VAULT
2. **Attendu** : Sélecteur de dossiers (car VAULT → mode='dir')
3. Sélectionner un dossier
4. **Attendu** : Chemin complet rempli

#### Test PACKAGES_CONF_DIR
1. Cliquer sur "Parcourir" à côté de PACKAGES_CONF_DIR
2. **Attendu** : Sélecteur de dossiers (car _DIR → mode='dir')
3. Sélectionner un dossier
4. **Attendu** : Chemin complet rempli

### 3. Sélection de fichier (macOS native picker)

#### Test WIFI_KDBX_DB
1. Aller dans Settings
2. Cliquer sur "Parcourir" à côté de WIFI_KDBX_DB
3. **Attendu** : Un sélecteur de **fichiers** s'ouvre (Finder)
4. Sélectionner un fichier .kdbx
5. **Attendu** : Le chemin complet du fichier apparaît

#### Test WIFI_KDBX_KEY_FILE
1. Cliquer sur "Parcourir" à côté de WIFI_KDBX_KEY_FILE
2. **Attendu** : Sélecteur de fichiers (car _KEY_FILE → mode='file')
3. Sélectionner un fichier
4. **Attendu** : Chemin complet rempli

### 4. Sélection avec exemples (placeholders)
1. Observer les champs avec placeholder (exemples commentés dans .env.example)
2. **Attendu pour SYNC_DIR** : placeholder affiche un exemple comme `$HOME/OneDrive/dotfiles`

### 5. Sauvegarde
1. Après avoir sélectionné des chemins, cliquer sur "Save Changes"
2. **Attendu** : Toast de succès avec le chemin du fichier `.env.local`
3. Fermer et rouvrir l'app
4. **Attendu** : Les valeurs sont persistées

## Bugs connus avant correction
- ❌ Les boutons disaient "Parcourir" en dur (pas i18n)
- ❌ OBSIDIAN_VAULT et VSCODE_CONFIG ouvraient un sélecteur de fichiers au lieu de dossiers
- ❌ WIFI_KDBX_DB (base .kdbx) devrait être sélectionné comme fichier

## Après correction
- ✅ Boutons internationalisés (fr: "Parcourir", en: "Browse")
- ✅ Détection correcte : _DIR, VAULT, CONFIG → sélecteur de dossiers
- ✅ Détection correcte : _FILE, _KEY_FILE, DB → sélecteur de fichiers
- ✅ Mode stocké dans `data-path-mode` pour cohérence
- ✅ Fallback browser avec `webkitdirectory` pour dossiers

## Implémentation technique

### Détection du mode
```javascript
function inferType(key, value) {
  // ...
  if (/DB$/i.test(k)) return { type: 'path', mode: 'file' };
  if (/VAULT|CONFIG|SYNC_DIR/i.test(k)) return { type: 'path', mode: 'dir' };
  // ...
}
```

### Native picker (pywebview)
```javascript
if (isDir && window.pywebview.api.open_dir) {
  const path = await window.pywebview.api.open_dir(`Select folder for ${key}`);
}
if (isFile && window.pywebview.api.open_file) {
  const path = await window.pywebview.api.open_file(`Select file for ${key}`);
}
```

### Fallback browser (webkitdirectory)
```javascript
dirInput.webkitdirectory = true;
dirInput.directory = true;
```
