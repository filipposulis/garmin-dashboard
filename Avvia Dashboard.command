#!/bin/bash
# Doppio clic per avviare la Garmin Dashboard (Mac).
# - La prima volta scarica Python e le librerie (un paio di minuti), poi parte in pochi secondi.
# - A ogni avvio controlla se su GitHub c'è una versione nuova e la installa da sola.
#   I dati e l'accesso a Garmin non vengono toccati.

# Tutto dentro main(): bash legge l'intero script prima di eseguirlo,
# così l'aggiornamento può sostituire anche questo file senza problemi.
main() {
    cd "$(dirname "$0")" || exit 1
    export PATH="$HOME/.local/bin:$PATH"
    echo "=== Garmin Dashboard ==="

    update

    if ! command -v uv >/dev/null 2>&1; then
        echo "Prima installazione: scarico uv (gestore di Python)…"
        curl -LsSf https://astral.sh/uv/install.sh | sh || fail "Download non riuscito: controlla la connessione."
        export PATH="$HOME/.local/bin:$PATH"
    fi

    if [ ! -x ".venv/bin/streamlit" ] || [ requirements.txt -nt .venv/.installed ]; then
        echo "Preparo l'ambiente (solo la prima volta o dopo un aggiornamento)…"
        uv venv --python 3.12 --quiet --clear .venv &&
            uv pip install --python .venv --quiet -r requirements.txt &&
            touch .venv/.installed || fail "Installazione non riuscita."
    fi

    echo "Avvio… si aprirà il browser. Per chiudere la dashboard chiudi questa finestra."
    .venv/bin/streamlit run dashboard.py
}

update() {
    [ -f .update_repo ] || return 0
    local repo remote local_v tmp src
    repo=$(tr -d '[:space:]' < .update_repo)
    remote=$(curl -fsSL --max-time 5 "https://raw.githubusercontent.com/$repo/main/VERSION" 2>/dev/null | tr -d '[:space:]')
    local_v=$(tr -d '[:space:]' < VERSION 2>/dev/null)
    # offline o GitHub irraggiungibile: si parte con la versione che c'è
    [ -n "$remote" ] && [ "$remote" != "$local_v" ] || return 0

    echo "Trovata una nuova versione ($remote): aggiorno…"
    tmp=$(mktemp -d)
    if curl -fsSL --max-time 120 "https://github.com/$repo/archive/refs/heads/main.zip" -o "$tmp/u.zip" &&
        unzip -q "$tmp/u.zip" -d "$tmp"; then
        src=$(find "$tmp" -mindepth 1 -maxdepth 1 -type d | head -1)
        if [ -f "$src/dashboard.py" ]; then
            rsync -a --exclude data --exclude .venv "$src"/ ./
            chmod +x "Avvia Dashboard.command"
            echo "Aggiornato alla versione $remote."
        fi
    else
        echo "Aggiornamento non riuscito, uso la versione attuale."
    fi
    rm -rf "$tmp"
}

fail() {
    echo "$1"
    read -r -p "Premi Invio per chiudere"
    exit 1
}

main "$@"
exit
