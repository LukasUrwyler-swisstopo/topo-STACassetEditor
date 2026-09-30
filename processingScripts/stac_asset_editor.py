"""
STAC Asset Editor - Kernlogik.

Ergänzt die "description" bestehender STAC-Assets über die Transaktions-API.
Es wird ausschliesslich das Feld "description" per PATCH gesendet; die
Asset-Datei und alle übrigen Metadaten (title, type, gsd, checksum, ...)
bleiben unverändert.

Das GUI dazu: GUI_stac_assetDescription_editor.py (im Hauptverzeichnis)
"""

import logging
from pathlib import Path
from urllib.parse import urlparse

import requests

from configuration import (
    DEFAULT_ENVIRONMENT,
    DESCRIPTION_FIELDS,
    DESCRIPTION_SEPARATOR,
    REQUEST_TIMEOUT,
    STAC_API_PATH,
    STAC_HOSTNAMES,
    STAC_SCHEME,
)
from utilities import proxy_handler
from utilities.credentials import load_stac_credentials

logger = logging.getLogger(__name__)

# Pfade am Skript verankern, damit das Tool aus jedem Arbeitsverzeichnis läuft.
# Dieses Skript liegt in processingScripts/, secrets/ und logs/ im Hauptverzeichnis.
PROJECT_DIR = Path(__file__).resolve().parent.parent
SECRETS_DIR = PROJECT_DIR / "secrets"
proxy_handler.PROXY_CONFIG_PATH = SECRETS_DIR / "proxy_config.json"


def build_description(values: dict) -> str:
    """
    Setzt die Asset-Description aus den ausgefüllten Attributen zusammen.

    Args:
        values (dict): Attributname -> Text (Namen wie in DESCRIPTION_FIELDS)

    Returns:
        str: z.B. "Area: Bern, CameraSystem: Leica ADS100" (leer wenn nichts ausgefüllt)
    """
    parts = []
    for name, _ in DESCRIPTION_FIELDS:
        value = (values.get(name) or "").strip()
        if value:
            parts.append(f"{name}: {value}")
    return DESCRIPTION_SEPARATOR.join(parts)


def read_hrefs(text: str) -> list:
    """
    Liest Asset-hrefs aus einem Text (eine URL pro Zeile).

    Leere Zeilen, Kommentarzeilen (#) und doppelte hrefs fallen weg.
    """
    hrefs = []
    for line in text.splitlines():
        href = line.strip()
        if href and not href.startswith("#") and href not in hrefs:
            hrefs.append(href)
    return hrefs


def parse_asset_href(href: str, environment: str) -> tuple:
    """
    Zerlegt einen Asset-href in (collection, item, asset).

    Erwartet: https://<host>/<collection>/<item>/<asset>
    Der Host muss zur gewählten Umgebung passen, damit nie versehentlich
    in die falsche Umgebung geschrieben wird.

    Raises:
        ValueError: Wenn der href nicht dem Muster oder der Umgebung entspricht
    """
    parsed = urlparse(href)
    parts = [p for p in parsed.path.split("/") if p]
    expected_host = STAC_HOSTNAMES[environment]

    if parsed.scheme != STAC_SCHEME or not parsed.hostname:
        raise ValueError(
            f"Kein gültiger Asset-href. Erwartet: "
            f"{STAC_SCHEME}://{expected_host}/<collection>/<item>/<asset>"
        )
    if parsed.hostname != expected_host:
        raise ValueError(
            f"href zeigt auf '{parsed.hostname}', gewählt ist aber {environment} "
            f"({expected_host}). Umgebung umstellen oder href prüfen."
        )
    if len(parts) != 3:
        raise ValueError(
            f"Kein gültiger Asset-href. Erwartet: "
            f"{STAC_SCHEME}://{expected_host}/<collection>/<item>/<asset>"
        )
    return tuple(parts)


def get_asset_api_url(environment: str, collection: str, item: str, asset: str) -> str:
    """Baut die URL des Assets in der STAC-Transaktions-API."""
    return (
        f"{STAC_SCHEME}://{STAC_HOSTNAMES[environment]}{STAC_API_PATH}"
        f"collections/{collection}/items/{item}/assets/{asset}"
    )


def update_one_asset(session, href, description, environment, overwrite, dry_run, auth) -> tuple:
    """
    Prüft ein Asset und schreibt die Description (ausser bei dry_run).

    Returns:
        tuple: (status, meldung) mit status = "SUCCESS" | "WARNING" | "ERROR"

    Raises:
        ValueError: Ungültiger href
        PermissionError: Anmeldung vom Server abgelehnt (betrifft alle Assets)
        requests.RequestException: Netzwerkfehler
    """
    collection, item, asset = parse_asset_href(href, environment)
    url = get_asset_api_url(environment, collection, item, asset)

    # Aktuellen Stand lesen: existiert das Asset, hat es schon eine Description?
    response = session.get(url, timeout=REQUEST_TIMEOUT)
    if response.status_code == 404:
        return "ERROR", "Asset im STAC nicht gefunden (HTTP 404). href prüfen."
    if response.status_code != 200:
        return "ERROR", f"Asset konnte nicht gelesen werden (HTTP {response.status_code})."
    try:
        existing = response.json().get("description")
    except ValueError:
        return "ERROR", "Unerwartete Antwort vom Server (kein JSON). Verbindung/Proxy prüfen."

    if existing == description:
        return "SUCCESS", "Description ist bereits identisch vorhanden, nichts zu ändern."
    if existing and not overwrite:
        return "WARNING", f"Übersprungen, Asset hat bereits eine Description: {existing}"

    action = "überschrieben" if existing else "ergänzt"
    if dry_run:
        return "SUCCESS", f"Prüfung OK, Description würde {action}."

    # PATCH ändert nur das gesendete Feld. Kein PUT verwenden: PUT löscht alle
    # optionalen Felder, die nicht im Payload stehen.
    response = session.patch(
        url, json={"description": description}, auth=auth, timeout=REQUEST_TIMEOUT
    )
    if response.status_code in (401, 403):
        raise PermissionError(
            f"Anmeldung vom Server abgelehnt (HTTP {response.status_code}). "
            f"Benutzername/Passwort für {environment} in secrets/stac_credentials.json prüfen."
        )
    if response.status_code != 200:
        return "ERROR", (
            f"Schreiben fehlgeschlagen (HTTP {response.status_code}): {response.text[:300]}"
        )
    try:
        written = response.json().get("description")
    except ValueError:
        written = None
    if written != description:
        return "ERROR", "Server hat die Description nicht wie gesendet übernommen. Asset im STAC prüfen."

    return "SUCCESS", f"Description {action}."


def update_asset_descriptions(
    hrefs: list,
    description: str,
    environment: str = DEFAULT_ENVIRONMENT,
    overwrite: bool = False,
    dry_run: bool = True
) -> dict:
    """
    Schreibt dieselbe Description in alle angegebenen Assets.

    Args:
        hrefs (list): Asset-hrefs (https://<host>/<collection>/<item>/<asset>)
        description (str): Text der Description
        environment (str): "INT" oder "PROD" (default: "INT")
        overwrite (bool): Bestehende Descriptions überschreiben (default: False)
        dry_run (bool): Nur prüfen, nichts schreiben (default: True)

    Returns:
        dict: Anzahl pro Status, z.B. {"SUCCESS": 3, "WARNING": 1, "ERROR": 0}

    Raises:
        ValueError: Bei ungültigen Eingaben oder fehlenden Credentials
        ConnectionError: Wenn keine Netzwerkverbindung möglich ist
    """
    if environment not in STAC_HOSTNAMES:
        raise ValueError(f"Unbekannte Umgebung '{environment}'. Erlaubt: {list(STAC_HOSTNAMES)}")
    if not hrefs:
        raise ValueError("Keine Asset-hrefs angegeben.")
    if not description:
        raise ValueError("Die Description ist leer. Mindestens ein Attribut ausfüllen.")

    proxy_handler.initialize_proxy()
    session = proxy_handler.get_session()

    # Credentials nur laden, wenn wirklich geschrieben wird (Lesen ist öffentlich)
    auth = None
    if not dry_run:
        username, password, _ = load_stac_credentials(
            SECRETS_DIR / "stac_credentials.json", environment
        )
        auth = (username, password)

    total = len(hrefs)
    mode = "PRÜFUNG (es wird nichts geschrieben)" if dry_run else "SCHREIBEN"
    logger.info("=" * 70)
    logger.info(f"{mode} | Umgebung {environment} ({STAC_HOSTNAMES[environment]}) | {total} Asset(s)")
    logger.info(f"Description: {description}")
    logger.info("=" * 70)

    counts = {"SUCCESS": 0, "WARNING": 0, "ERROR": 0}
    processed = 0
    for idx, href in enumerate(hrefs, 1):
        aborted = False
        try:
            status, message = update_one_asset(
                session, href, description, environment, overwrite, dry_run, auth
            )
        except ValueError as e:
            status, message = "ERROR", str(e)
        except PermissionError as e:
            # Betrifft alle Assets: abbrechen statt weitere Fehlversuche senden
            status, message, aborted = "ERROR", str(e), True
        except requests.RequestException as e:
            status, message = "ERROR", f"Netzwerkfehler, Verbindung/Proxy prüfen: {e}"

        counts[status] += 1
        processed = idx
        line = f"[{idx}/{total}] {status}: {href}\n      {message}"
        if status == "ERROR":
            logger.error(line)
        elif status == "WARNING":
            logger.warning(line)
        else:
            logger.info(line)
        if aborted:
            break

    logger.info("=" * 70)
    logger.info(
        f"Fertig: {counts['SUCCESS']} SUCCESS, {counts['WARNING']} WARNING, {counts['ERROR']} ERROR"
    )
    if processed < total:
        logger.error(f"Abgebrochen: {total - processed} Asset(s) wurden nicht bearbeitet.")
    logger.info("=" * 70)
    return counts
