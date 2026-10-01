"""
Einmaliges Skript (nicht Teil des GUI): ersetzt bei allen Assets einer
href-Liste (TXT, ein href pro Zeile, wie im GUI) ein falsches Attribut in der
"description", z.B.
    "CameraSystem: Spiegelreflexkamera (Handkamera)"
 -> "CameraSystem: Helikopter mit RIEGL-Kamera"

Alle übrigen Attribute der Description bleiben Zeichen für Zeichen gleich.
Gesendet wird per PATCH nur {"description"}; alle übrigen Felder
(title, type, href, gsd, checksum, proj:epsg, ...) bleiben unverändert.

Ablauf:
    1. DRY_RUN = True  -> zeigt pro Asset Vorher/Nachher, schreibt nichts
    2. DRY_RUN = False -> schreibt nach einer Bestätigung mit "ja" (einmal für alle)
    Zuerst auf INT testen, erst danach ENVIRONMENT/Liste auf PROD umstellen.
    Erneutes Ausführen ist unschädlich: bereits korrigierte Assets werden erkannt.

Start (aus dem Projektverzeichnis):
    python processingScripts/fix_asset_camerasystem.py
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

import requests

from configuration import DESCRIPTION_SEPARATOR, REQUEST_TIMEOUT
from stac_asset_editor import PROJECT_DIR, SECRETS_DIR, get_asset_api_url, parse_asset_href, read_hrefs
from utilities import proxy_handler
from utilities.credentials import load_stac_credentials

# ---------------------------------------------------------------------------
# Eingaben
# ---------------------------------------------------------------------------
ENVIRONMENT = "INT"  # "INT" oder "PROD" - muss zum Host der hrefs passen
HREF_LIST_FILE = r"\\server\freigabe\pfad\zur\href_liste.txt"  # Netzwerkpfad (UNC) oder lokaler Pfad
OLD_ATTRIBUTE = "CameraSystem: Spiegelreflexkamera (Handkamera)"
NEW_ATTRIBUTE = "CameraSystem: Helikopter mit RIEGL-Kamera"
DRY_RUN = True  # True = nur prüfen, False = schreiben
# ---------------------------------------------------------------------------

logger = logging.getLogger("fix_asset_camerasystem")


def replace_attribute(description: str, old: str, new: str) -> str:
    """
    Ersetzt das ganze Attribut old durch new, der Rest bleibt unverändert.

    old muss genau einmal und als vollständiges Attribut vorkommen
    (davor Anfang oder ", ", danach Ende oder ", "). So wird z.B.
    "...(Handkamera) XY" nicht still zu "...RIEGL-Kamera XY".

    Raises:
        ValueError: Wenn old nicht genau einmal als ganzes Attribut vorkommt
    """
    count = description.count(old)
    if count != 1:
        raise ValueError(f"'{old}' kommt {count}x in der Description vor (erwartet: 1x).")
    start = description.index(old)
    end = start + len(old)
    before_ok = start == 0 or description[:start].endswith(DESCRIPTION_SEPARATOR)
    after_ok = end == len(description) or description[end:].startswith(DESCRIPTION_SEPARATOR)
    if not (before_ok and after_ok):
        raise ValueError(f"'{old}' steht nicht als ganzes Attribut in der Description.")
    return description[:start] + new + description[end:]


def check_asset(session, href: str):
    """
    Liest ein Asset (GET ist öffentlich) und berechnet die neue Description.

    Gibt (status, url, neue_description) zurück, status ist "change", "ok",
    "skip" oder "error". Für Assets ohne Änderung wird das Endergebnis hier geloggt.
    """
    try:
        collection, item, asset = parse_asset_href(href, ENVIRONMENT)
        url = get_asset_api_url(ENVIRONMENT, collection, item, asset)
        response = session.get(url, timeout=REQUEST_TIMEOUT)
        if response.status_code == 404:
            logger.error(f"ERROR: {href} | Asset nicht gefunden (HTTP 404). href prüfen.")
            return "error", None, None
        if response.status_code != 200:
            logger.error(f"ERROR: {href} | Asset konnte nicht gelesen werden (HTTP {response.status_code}).")
            return "error", None, None
        old_description = response.json().get("description") or ""

        if OLD_ATTRIBUTE not in old_description:
            if NEW_ATTRIBUTE in old_description:
                logger.info(f"SUCCESS: {href} | bereits korrekt, nichts zu ändern.")
                return "ok", None, None
            logger.warning(
                f"WARNING: {href} | '{OLD_ATTRIBUTE}' nicht in der Description, übersprungen. "
                f"Description: '{old_description}'"
            )
            return "skip", None, None

        new_description = replace_attribute(old_description, OLD_ATTRIBUTE, NEW_ATTRIBUTE)
    except ValueError as e:
        logger.error(f"ERROR: {href} | {e} Von Hand prüfen, es wird nichts geschrieben.")
        return "error", None, None
    except requests.RequestException as e:
        logger.error(f"ERROR: {href} | Netzwerkfehler beim Lesen, Verbindung/Proxy prüfen: {e}")
        return "error", None, None

    logger.info(f"  {href}")
    logger.info(f"    vorher:  {old_description}")
    logger.info(f"    nachher: {new_description}")
    if DRY_RUN:
        logger.info(f"SUCCESS: {href} | Prüfung OK, würde geändert.")
    return "change", url, new_description


def write_asset(session, href: str, url: str, new_description: str, auth: tuple) -> bool:
    """Schreibt die neue Description per PATCH. Gibt True bei Erfolg zurück."""
    # PATCH ändert nur die gesendeten Felder. Kein PUT: PUT löscht alle
    # optionalen Felder, die nicht im Payload stehen.
    try:
        response = session.patch(url, json={"description": new_description}, auth=auth, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        logger.error(f"ERROR: {href} | Netzwerkfehler beim Schreiben, Verbindung/Proxy prüfen: {e}")
        return False
    if response.status_code in (401, 403):
        logger.error(
            f"ERROR: {href} | Anmeldung abgelehnt (HTTP {response.status_code}). "
            f"Credentials für {ENVIRONMENT} in secrets/stac_credentials.json prüfen."
        )
        return False
    if response.status_code != 200:
        logger.error(f"ERROR: {href} | Schreiben fehlgeschlagen (HTTP {response.status_code}): {response.text[:300]}")
        return False
    if response.json().get("description") != new_description:
        logger.error(f"ERROR: {href} | Server hat die Description nicht wie gesendet übernommen. Asset prüfen.")
        return False
    logger.info(f"SUCCESS: {href} | Description geschrieben.")
    return True


def main() -> int:
    """Gibt 0 zurück, wenn kein Asset mit ERROR endet, sonst 1."""
    list_path = Path(HREF_LIST_FILE)
    try:
        with open(str(list_path), "r", encoding="utf-8-sig") as f:
            hrefs = read_hrefs(f.read())
    except OSError as e:
        logger.error(
            f"ERROR: href-Liste konnte nicht gelesen werden: {list_path} ({e}). "
            f"Pfad und Zugriff auf das Netzlaufwerk prüfen."
        )
        return 1
    if not hrefs:
        logger.error(f"ERROR: href-Liste ist leer: {list_path}")
        return 1

    mode = "PRÜFUNG (es wird nichts geschrieben)" if DRY_RUN else "SCHREIBEN"
    logger.info("=" * 70)
    logger.info(f"{mode} | Umgebung {ENVIRONMENT} | {len(hrefs)} Asset(s) aus {list_path}")
    logger.info(f"ersetzen: '{OLD_ATTRIBUTE}'")
    logger.info(f"durch:    '{NEW_ATTRIBUTE}'")
    logger.info("=" * 70)

    proxy_handler.initialize_proxy()
    session = proxy_handler.get_session()

    # Phase 1: alle Assets lesen und prüfen, noch nichts schreiben
    to_write = []
    counts = {"change": 0, "ok": 0, "skip": 0, "error": 0}
    for href in hrefs:
        status, url, new_description = check_asset(session, href)
        counts[status] += 1
        if status == "change":
            to_write.append((href, url, new_description))

    logger.info("=" * 70)
    logger.info(
        f"Prüfung: {counts['change']} zu ändern, {counts['ok']} bereits korrekt, "
        f"{counts['skip']} übersprungen (WARNING), {counts['error']} mit ERROR."
    )
    if DRY_RUN:
        logger.info("Prüfung beendet, nichts geschrieben. Zum Schreiben DRY_RUN = False setzen.")
        return 1 if counts["error"] else 0
    if not to_write:
        return 1 if counts["error"] else 0

    # Phase 2: einmal für alle bestätigen, dann schreiben
    answer = input(f"{len(to_write)} Asset(s) in {ENVIRONMENT} wirklich ändern? 'ja' eingeben: ")
    if answer.strip().lower() != "ja":
        logger.warning("WARNING: Abgebrochen durch Benutzer, nichts geschrieben.")
        return 1

    username, password, _ = load_stac_credentials(SECRETS_DIR / "stac_credentials.json", ENVIRONMENT)
    n_errors = 0
    for href, url, new_description in to_write:
        if not write_asset(session, href, url, new_description, (username, password)):
            n_errors += 1

    logger.info("=" * 70)
    logger.info(f"Fertig: {len(to_write) - n_errors} geschrieben, {n_errors} mit ERROR beim Schreiben.")
    return 1 if (n_errors or counts["error"]) else 0


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
        # z.B. Credentials-Datei fehlt oder enthält die Umgebung nicht
        logger.error(f"ERROR: {e}")
        sys.exit(1)
