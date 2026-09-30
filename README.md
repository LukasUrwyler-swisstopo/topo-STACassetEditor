# STAC Asset Editor

Ergänzt bei bestehenden STAC-Assets die fehlende `description`. Die Asset-Datei und alle
übrigen Metadaten bleiben unverändert.

## Start

```
cmd

>python GUI_stac_assetDescription_editor.py
```

<img width="943" height="1024" alt="image" src="https://github.com/user-attachments/assets/a0c23a55-5431-448d-abc4-f976d5a80713" />


Beim ersten Start installiert das GUI die fehlenden Python-Pakete (`requests`, `urllib3`) selbst;
dafür braucht es einmalig eine Internetverbindung. Klappt das nicht (z.B. wegen eines Proxys),
zeigt das GUI den Befehl für die Installation von Hand an:
`python -m pip install -r requirements/requirements.txt`.

Läuft ab Python 3.6 (`pip` wählt dort automatisch passende Versionen von `requests`/`urllib3`).
Oben rechts lässt sich zwischen Dark- und Hell-Modus umschalten.

Voraussetzung: `secrets/stac_credentials.json` (Format wie in topo-rapidmapping, mit `INT` und
`PROD`) und optional `secrets/proxy_config.json`.

## Bedienung

1. **Umgebung** wählen (INT ist Standard). Die hrefs müssen zur gewählten Umgebung gehören.
2. **Asset-hrefs** eingeben, eine URL pro Zeile, oder über «Aus TXT-Datei laden...» einlesen.
   Alle aufgeführten Assets erhalten dieselben Attribute, nur die **Acquisition time** wird pro
   Asset aus der Item-ID gelesen (UTC): `ram-2022-07-16t10080000` → `2022-07-16T10:08:00.00`.
   Passt eine Item-ID nicht zu diesem Muster, endet das Asset mit ERROR.
3. **Attribute** ausfüllen. Leere Felder erscheinen nicht in der Description.
   SourceReferenceSystem ist mit `(EPSG:2056) CH1903+ / LV95_LN02` vorbelegt. Mehrere LineIDs
   mit `, ` trennen. Ein **RapidMapping Event** wird dem Commentary vorangestellt, z.B.
   `Commentary: RapidMapping Trockenheit Wallis 2026, Quick Digital OrthoPhoto - RGB 8BIT - rapidData`.
   Die Vorschau zeigt den Text genau so, wie ihn das erste Asset erhält.
4. **Prüfen (nichts schreiben)**: zeigt pro Asset, was geschehen würde. Braucht kein Login.
5. **Description schreiben**: schreibt nach Rückfrage.

Format der TXT-Datei: eine URL pro Zeile; leere Zeilen und Zeilen mit `#` werden ignoriert.

```
# Befliegung Misox 2024
https://data.geo.admin.ch/ch.swisstopo.spezialbefliegungen/ram-2024-06-28t07300000/ram-2024-06-28t07300000-qdop-rgb-mosaic.tif
```

## Ergebnis pro Asset

| Status  | Bedeutung |
|---------|-----------|
| SUCCESS | Description ergänzt (oder bereits identisch vorhanden) |
| WARNING | Übersprungen: Asset hat bereits eine andere Description. Nur mit «Bestehende Description überschreiben» wird sie ersetzt. |
| ERROR   | href ungültig, falsche Umgebung, Asset nicht gefunden oder Schreiben fehlgeschlagen |

Jeder Lauf wird in `logs/stac_asset_editor_<Datum>.log` protokolliert.

## Anpassen

Attribute, deren Reihenfolge und die Vorschläge in den Auswahllisten stehen in
`processingScripts/configuration.py` (`DESCRIPTION_FIELDS`).

## Aufbau

```
GUI_stac_assetDescription_editor.py   GUI, Einstiegspunkt
processingScripts/                    Kernlogik, Konfiguration, utilities
requirements/requirements.txt         Python-Abhängigkeiten
secrets/                              Zugangsdaten und Proxy (nicht in git)
logs/                                 eine Logdatei pro Tag
.claude/CLAUDE.md                     Regeln für Claude Code
```

## Technik

Pro Asset ein `GET` (Stand lesen) und ein `PATCH` mit ausschliesslich `{"description": "..."}`
auf die STAC-Transaktions-API v0.9
([Spezifikation](https://data.geo.admin.ch/api/stac/static/spec/v0.9/apitransactional.html)).
`PATCH` ändert nur das gesendete Feld; `PUT` würde alle nicht mitgesendeten optionalen Felder löschen.
