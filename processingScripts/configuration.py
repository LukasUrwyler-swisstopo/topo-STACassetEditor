"""
Konfigurationsmodul für den STAC Asset Editor.

Enthält die STAC-Endpunkte (INT/PROD) und die Attribute der Asset-Description.
"""

# STAC Konfiguration
STAC_HOSTNAMES = {
    "INT": "sys-data.int.bgdi.ch",
    "PROD": "data.geo.admin.ch",
}
DEFAULT_ENVIRONMENT = "INT"  # INT bleibt Default, PROD muss bewusst gewählt werden
STAC_SCHEME = "https"
STAC_API_PATH = "/api/stac/v0.9/"

REQUEST_TIMEOUT = 30  # Sekunden

# Attribute der Asset-Description in der Reihenfolge, in der sie im Text stehen.
# Pro Attribut: (Name, Vorschläge für die Auswahlliste im GUI - darf leer sein).
# Im GUI leer gelassene Attribute erscheinen nicht in der Description.
# Liste statt dict: die Reihenfolge ist so auch unter Python 3.6 garantiert.
DESCRIPTION_FIELDS = [
    ("Area", []),
    # TerrainModel und CameraSystem wie TERRAIN_MODELS / CAMERA_SYSTEMS in ../topo-GDWHimport
    # (Ausnahme: "Spiegelreflexkamera (Handkamera)" und "Helikopter mit RIEGL-Kamera" gibt es nur hier)
    ("TerrainModel", [
        "Digital Surface Model (DSM photogrammetric autocorrelation)",
        "swissALTI3D",
        "swissALTI3D/DHM25",
        "swissSURFACE3D",
    ]),
    ("SourceReferenceSystem", []),
    ("CameraSystem", [
        "Leica ADS100",
        "Leica ADS80",
        "Leica DMC-4",
        "Spiegelreflexkamera (Handkamera)",
        "Helikopter mit RIEGL-Kamera",
    ]),
    ("Acquisition time", []),
    ("LineID", []),
    ("Commentary", [
        'Einzelbild Oblique - rapidData "ebo"',
        'Einzelbild Nadir - rapidData "ebn"',
        "Quick Digital OrthoPhoto - RGB 8BIT - rapidData",
        "Quick Digital OrthoPhoto - NRG 8BIT - rapidData",
        "Digital OrthoPhoto - Mosaic RGB 8BIT",
        "Digital OrthoPhoto - Mosaic RGBN 8BIT",
        "Digital Surface Model - Raster Mosaic (DSM photogrammetric autocorrelation)",
        "Digital Surface Model - PointCloud LAZ (DSM photogrammetric autocorrelation)",
        "Digital Terrain Model - swissALTI",
        "Digital Terrain Model - swissSURFACE",
    ]),
]
DESCRIPTION_SEPARATOR = ", "

# Kopplung im GUI in beide Richtungen: wird im Dropdown CameraSystem die Kamera
# gewählt, setzt das GUI das Commentary, und umgekehrt. Texte müssen exakt den
# Vorschlägen in DESCRIPTION_FIELDS entsprechen.
CAMERA_COMMENTARY_PAIRS = [
    ("Spiegelreflexkamera (Handkamera)", 'Einzelbild Oblique - rapidData "ebo"'),
    ("Helikopter mit RIEGL-Kamera", 'Einzelbild Nadir - rapidData "ebn"'),
]

# Vorbelegung im GUI (Feld bleibt editierbar)
FIELD_DEFAULTS = {
    "SourceReferenceSystem": "(EPSG:2056) CH1903+ / LV95_LN02",
}

# Wird nicht im GUI eingegeben, sondern pro Asset aus der Item-ID gelesen
ACQUISITION_TIME_FIELD = "Acquisition time"
