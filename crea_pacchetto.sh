#!/bin/bash
# Crea "Garmin Dashboard.zip" da mandare a un amico: solo codice, nessun dato personale.
set -e
cd "$(dirname "$0")"
OUT="$PWD/Garmin Dashboard.zip"
TMP="$(mktemp -d)/Garmin Dashboard"
mkdir -p "$TMP/.streamlit"
cp dashboard.py pages_analysis.py analysis.py common.py garmin_data.py theme.py login.py \
   requirements.txt LEGGIMI.txt "$TMP/"
cp .streamlit/config.toml "$TMP/.streamlit/"
cp VERSION .update_repo "$TMP/"    # servono per gli aggiornamenti automatici
cp "Avvia Dashboard.command" "$TMP/Avvia Dashboard.command"
chmod +x "$TMP/Avvia Dashboard.command"
rm -f "$OUT"
(cd "$(dirname "$TMP")" && zip -rq -X "$OUT" "Garmin Dashboard")
rm -rf "$(dirname "$TMP")"
echo "Creato: $OUT"
unzip -l "$OUT"
