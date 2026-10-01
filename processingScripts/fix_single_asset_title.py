"""
Einmaliges Skript (nicht Teil des GUI): ändert bei EINEM Asset den "title" und
den Wert von "Commentary" in der "description".

Gesendet wird per PATCH nur {"title", "description"}; alle übrigen Felder
(type, href, gsd, checksum, proj:epsg, ...) bleiben unverändert.

Ablauf:
    1. DRY_RUN = True  -> zeigt Vorher/Nachher, schreibt nichts
    2. DRY_RUN = False -> schreibt nach Bestätigung mit "ja"
    Zuerst auf INT testen, erst danach ENVIRONMENT/HREF auf PROD umstellen.

Start (aus dem Projektverzeichnis):
    python processingScripts/fix_single_asset_title.py
"""

import logging
import sys
from datetime import datetime

import requests

from configuration import REQUEST_TIMEOUT
from stac_asset_editor import PROJECT_DIR, SECRETS_DIR, get_asset_api_url, parse_asset_href
from utilities import proxy_handler
from utilities.credentials import load_stac_credentials

# ---------------------------------------------------------------------------
# Eingaben
# ---------------------------------------------------------------------------
ENVIRONMENT = "INT"  # "INT" oder "PROD" - muss zum Host im HREF passen
HREF = (
    "https://sys-data.int.bgdi.ch/ch.swisstopo.spezialbefliegungen/"
    "ram-2026-08-19t12595900/ram-2026-08-19t12595900-qdop-rgb-mosaic.tif"
)
NEW_TITLE = "QDOP-NRG-MOSAIC"
NEW_COMMENTARY = "Trockenheit 2026 - Testflug, Quick Digital OrthoPhoto - NRG 8BIT - rapidData"
DRY_RUN = False  # True = nur prüfen, False = schreiben
# ---------------------------------------------------------------------------

# Commentary ist laut Format immer das letzte Attribut der Description.
# Der Wert darf selbst ", " enthalten, darum wird alles ab dem Marker bis zum
# Ende ersetzt (kein Aufteilen an ", ").
COMMENTARY_MARKER = "Commentary: "

logger = logging.getLogger("fix_single_asset_title")


def replace_commentary(description: str, new_value: str) -> str:
    """
    Ersetzt den Wert von Commentary (alles nach "Commentary: " bis zum Ende).

    Raises:
        ValueError: Wenn "Commentary: " nicht genau einmal vorkommt
    """
    count = description.count(COMMENTARY_MARKER)
    if count != 1:
        raise ValueError(
            f"'{COMMENTARY_MARKER.strip()}' kommt {count}x in der Description vor (erwartet: 1x). "
            f"Description von Hand prüfen, es wird nichts geschrieben."
        )
    start = description.index(COMMENTARY_MARKER) + len(COMMENTARY_MARKER)
    return description[:start] + new_value.strip()


def main() -> int:
    """Gibt 0 bei Erfolg zurück, 1 bei Fehler."""
    collection, item, asset = parse_asset_href(HREF, ENVIRONMENT)
    url = get_asset_api_url(ENVIRONMENT, collection, item, asset)

    proxy_handler.initialize_proxy()
    session = proxy_handler.get_session()

    # Aktuellen Stand lesen (GET ist öffentlich)
    response = session.get(url, timeout=REQUEST_TIMEOUT)
    if response.status_code != 200:
        logger.error(f"Asset konnte nicht gelesen werden (HTTP {response.status_code}). HREF prüfen.")
        return 1
    current = response.json()
    old_title = current.get("title")
    old_description = current.get("description") or ""

    new_title = NEW_TITLE.strip()
    new_description = replace_commentary(old_description, NEW_COMMENTARY)

    mode = "PRÜFUNG (es wird nichts geschrieben)" if DRY_RUN else "SCHREIBEN"
    logger.info("=" * 70)
    logger.info(f"{mode} | Umgebung {ENVIRONMENT} | {HREF}")
    logger.info(f"title vorher:       {old_title}")
    logger.info(f"title nachher:      {new_title}")
    logger.info(f"description vorher:  {old_description}")
    logger.info(f"description nachher: {new_description}")
    logger.info("=" * 70)

    if old_title == new_title and old_description == new_description:
        logger.info("SUCCESS: title und description sind bereits so vorhanden, nichts zu ändern.")
        return 0
    if DRY_RUN:
        logger.info("SUCCESS: Prüfung OK. Zum Schreiben DRY_RUN = False setzen.")
        return 0

    answer = input(f"Asset in {ENVIRONMENT} wirklich ändern? 'ja' eingeben: ")
    if answer.strip().lower() != "ja":
        logger.warning("WARNING: Abgebrochen durch Benutzer, nichts geschrieben.")
        return 1

    username, password, _ = load_stac_credentials(SECRETS_DIR / "stac_credentials.json", ENVIRONMENT)

    # PATCH ändert nur die gesendeten Felder. Kein PUT: PUT löscht alle
    # optionalen Felder, die nicht im Payload stehen.
    response = session.patch(
        url,
        json={"title": new_title, "description": new_description},
        auth=(username, password),
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code in (401, 403):
        logger.error(
            f"ERROR: Anmeldung abgelehnt (HTTP {response.status_code}). "
            f"Credentials für {ENVIRONMENT} in secrets/stac_credentials.json prüfen."
        )
        return 1
    if response.status_code != 200:
        logger.error(f"ERROR: Schreiben fehlgeschlagen (HTTP {response.status_code}): {response.text[:300]}")
        return 1

    written = response.json()
    if written.get("title") != new_title or written.get("description") != new_description:
        logger.error("ERROR: Server hat die Werte nicht wie gesendet übernommen. Asset im STAC prüfen.")
        return 1
    logger.info("SUCCESS: title und description geschrieben.")
    return 0


if __name__ == "__main__":
    # Ausgabe in Konsole und in die Tages-Logdatei des Projekts
    log_dir = PROJECT_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "stac_asset_editor_{}.log".format(datetime.now().strftime("%Y-%m-%d"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(str(log_file), encoding="utf-8")],
    )
    try:
        sys.exit(main())
    except ValueError as e:
        logger.error(f"ERROR: {e}")
        sys.exit(1)
    except requests.RequestException as e:
        logger.error(f"ERROR: Netzwerkfehler, Verbindung/Proxy prüfen: {e}")
        sys.exit(1)
