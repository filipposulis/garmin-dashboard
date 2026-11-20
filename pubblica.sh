#!/bin/bash
# Pubblica le modifiche su GitHub: chi usa la dashboard le riceve al prossimo avvio.
# Uso: ./pubblica.sh "cosa ho cambiato"
set -e
cd "$(dirname "$0")"
date +%Y%m%d%H%M%S > VERSION
git add -A
git commit -q -m "${1:-Aggiornamento dashboard}"
git push -q origin main
echo "Pubblicata la versione $(cat VERSION)."
