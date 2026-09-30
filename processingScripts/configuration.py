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
    ("TerrainModel", [
        "Digital Surface Model (DSM photogrammetric autocorrelation)",
    ]),
    ("SourceReferenceSystem", [
        "(EPSG:2056) CH1903+ / LV95_LN02",
    ]),
    ("CameraSystem", [
        "Leica ADS100",
    ]),
    ("Acquisition time", []),
    ("LineId", []),
    ("Commentary", [
        "Digital OrthoPhoto - Mosaic RGB 8BIT",
        "Digital Surface Model - Raster Mosaic (DSM photogrammetric autocorrelation)",
        "Digital Surface Model - PointCloud LAZ (DSM photogrammetric autocorrelation)",
    ]),
]
DESCRIPTION_SEPARATOR = ", "
