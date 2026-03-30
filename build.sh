#!/bin/bash

set -euo pipefail

# Compile all shell scripts in src/ using shc into dist/
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="${ROOT_DIR}/src"
DIST_DIR="${ROOT_DIR}/dist"
VERSION_FILE="${ROOT_DIR}/VERSION"
VERSION="$(cat "${VERSION_FILE}" 2>/dev/null || echo 'dev')"

if ! command -v shc >/dev/null 2>&1; then
  echo "shc est requis pour compiler les scripts (sudo apt-get install -y shc)" >&2
  exit 1
fi

rm -rf "${DIST_DIR}"
mkdir -p "${DIST_DIR}"

echo "Build v${VERSION}"

compile_script() {
  local script_path="$1"
  local base
  base="$(basename "${script_path}")"
  local out="${DIST_DIR}/${base}"
  
  # shc crée le binaire et des fichiers temporaires
  # On ignore les warnings et on nettoie après
  shc -f "${script_path}" -i /bin/bash -o "${out}" 2>/dev/null || true
  
  # Nettoyer les fichiers générés non-utiles (ils restent à côté du script source)
  rm -f "${script_path}.x.c" 2>/dev/null || true
  
  # Vérifier que le binaire existe
  if [ -f "${out}" ]; then
    chmod +x "${out}"
    return 0
  else
    echo "Erreur: ${script_path} n'a pas pu être compilé" >&2
    return 1
  fi
}

for script in "${SRC_DIR}"/*.sh; do
  [ -e "${script}" ] || continue
  compile_script "${script}"
  echo "Compilé: ${script} → ${DIST_DIR}/$(basename "${script}")"
done

# Include configuration file for distribution
if [ -f "${SRC_DIR}/packages.conf" ]; then
  cp "${SRC_DIR}/packages.conf" "${DIST_DIR}/packages.conf"
fi

# Générer un manifest avec la version
cat > "${DIST_DIR}/MANIFEST.txt" << EOF
init_mac compiled release v${VERSION}
Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Built with: shc

Files:
EOF

ls -lh "${DIST_DIR}" | awk 'NR>1 {print $9 " (" $5 ")"}' >> "${DIST_DIR}/MANIFEST.txt" || true

echo "Build v${VERSION} terminé. Artefacts dans ${DIST_DIR}"