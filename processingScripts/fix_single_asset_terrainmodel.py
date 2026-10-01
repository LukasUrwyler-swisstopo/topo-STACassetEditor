"""
Einmaliges Skript (nicht Teil des GUI): ändert bei EINEM Asset den Wert von
"TerrainModel" in der "description", z.B.
    "TerrainModel: swissALTI3D" -> "TerrainModel: swissSURFACE3D"

Alle übrigen Attribute der Description bleiben Zeichen für Zeichen gleich.
Gesendet wird per PATCH nur {"description"}; alle übrigen Felder
(title, type, href, gsd, checksum, proj:epsg, ...) bleiben unverändert.

Ablauf:
    1. DRY_RUN = True  -> zeigt Vorher/Nachher, schreibt nichts
    2. DRY_RUN = False -> schreibt nach Bestätigung mit "ja"
    Zuerst auf INT testen, erst danach ENVIRONMENT/HREF auf PROD umstellen.

Start (aus dem Projektverzeichnis):
    python processingScripts/fix_single_asset_terrainmodel.py
"""

import logging
import sys
from datetime import datetime

import requests

from configuration import DESCRIPTION_FIELDS, DESCRIPTION_SEPARATOR, REQUEST_TIMEOUT
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
# Übliche Werte: "Digital Surface Model (DSM photogrammetric autocorrelation)",
# "swissALTI3D", "swissALTI3D/DHM25", "swissSURFACE3D"
NEW_TERRAIN_MODEL = "swissSURFACE3D"
DRY_RUN = True  # True = nur prüfen, False = schreiben
# ---------------------------------------------------------------------------

TERRAIN_MARKER = "TerrainModel: "
# Das TerrainModel endet dort, wo das nächste Attribut beginnt (", SourceReferenceSystem: "
# usw.). So wird der Wert auch dann vollständig ersetzt, wenn er selbst ", " enthält.
_FIELD_NAMES = [name for name, _ in DESCRIPTION_FIELDS]
NEXT_MARKERS = [
    DESCRIPTION_SEPARATOR + name + ": "
    for name in _FIELD_NAMES[_FIELD_NAMES.index("TerrainModel") + 1:]
]

logger = logging.getLogger("fix_single_asset_terrainmodel")


def replace_terrain_model(description: str, new_value: str):
    """
    Ersetzt den Wert von TerrainModel, der Rest der Description bleibt unverändert.

    Gibt (alter_wert, neue_description) zurück.

    Raises:
        ValueError: Wenn "TerrainModel: " nicht genau einmal als ganzes Attribut vorkommt
    """
    count = description.count(TERRAIN_MARKER)
    if count != 1:
        raise ValueError(
            f"'{TERRAIN_MARKER.strip()}' kommt {count}x in der Description vor (erwartet: 1x). "
            f"Description von Hand prüfen, es wird nichts geschrieben."
        )
    marker_pos = description.index(TERRAIN_MARKER)
    if marker_pos != 0 and not description[:marker_pos].endswith(DESCRIPTION_SEPARATOR):
        raise ValueError(
            f"'{TERRAIN_MARKER.strip()}' steht nicht als ganzes Attribut in der Description. "
            f"Description von Hand prüfen, es wird nichts geschrieben."
        )
    start = marker_pos + len(TERRAIN_MARKER)
    # Ende des Werts: Beginn des nächsten Attributs, sonst Ende der Description
    ends = [description.find(m, start) for m in NEXT_MARKERS]
    ends = [e for e in ends if e != -1]
    end = min(ends) if ends else len(description)
    return description[start:end], description[:start] + new_value + description[end:]


def main() -> int:
    """Gibt 0 bei Erfolg zurück, 1 bei Fehler."""
    new_value = NEW_TERRAIN_MODEL.strip()
    if not new_value:
        logger.error("ERROR: NEW_TERRAIN_MODEL ist leer. Neuen Wert oben im Skript eintragen.")
        return 1

    collection, item, asset = parse_asset_href(HREF, ENVIRONMENT)
    url = get_asset_api_url(ENVIRONMENT, collection, item, asset)

    proxy_handler.initialize_proxy()
    session = proxy_handler.get_session()

    # Aktuellen Stand lesen (GET ist öffentlich)
    response = session.get(url, timeout=REQUEST_TIMEOUT)
    if response.status_code == 404:
        logger.error("ERROR: Asset nicht gefunden (HTTP 404). HREF und ENVIRONMENT prüfen.")
        return 1
    if response.status_code != 200:
        logger.error(f"ERROR: Asset konnte nicht gelesen werden (HTTP {response.status_code}). HREF prüfen.")
        return 1
    old_description = response.json().get("description") or ""

    old_value, new_description = replace_terrain_model(old_description, new_value)

    mode = "PRÜFUNG (es wird nichts geschrieben)" if DRY_RUN else "SCHREIBEN"
    logger.info("=" * 70)
    logger.info(f"{mode} | Umgebung {ENVIRONMENT} | {HREF}")
    logger.info(f"TerrainModel vorher:  {old_value}")
    logger.info(f"TerrainModel nachher: {new_value}")
    logger.info(f"description vorher:  {old_description}")
    logger.info(f"description nachher: {new_description}")
    logger.info("=" * 70)

    if old_description == new_description:
        logger.info("SUCCESS: TerrainModel ist bereits so vorhanden, nichts zu ändern.")
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
        json={"description": new_description},
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

    if response.json().get("description") != new_description:
        logger.error("ERROR: Server hat die Description nicht wie gesendet übernommen. Asset im STAC prüfen.")
        return 1
    logger.info("SUCCESS: description geschrieben.")
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
    except (ValueError, OSError) as e:
        # z.B. HREF passt nicht zur Umgebung, TerrainModel fehlt, Credentials-Datei fehlt
        logger.error(f"ERROR: {e}")
        sys.exit(1)
    except requests.RequestException as e:
        logger.error(f"ERROR: Netzwerkfehler, Verbindung/Proxy prüfen: {e}")
        sys.exit(1)
