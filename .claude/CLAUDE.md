# CLAUDE.md

## Project Context

Rules for Claude Code in this repository: swisstopo STAC Asset Editor.

The tool adds a missing `description` to existing STAC assets (collection
`ch.swisstopo.spezialbefliegungen` and similar). The user enters asset hrefs (single, or a TXT
file with one href per line) and fills one input field per description attribute; all listed
assets receive the same description.

Users are geospatial specialists, not professional programmers. Maintainability and readability
take priority over elegance. Sister project: `../topo-rapidmapping` (publishes assets to the same
STAC API); same conventions apply here.

## Core principle

Simple code, few modules, functions instead of classes (exception: the one tkinter window class).

## Architecture

```
GUI_stac_assetDescription_editor.py            tkinter GUI (light/dark theme), entry point, logging setup
processingScripts/stac_asset_editor.py         core logic: parse href, build description, GET + PATCH
processingScripts/configuration.py             INT/PROD hostnames, API path, description attributes + suggestions
processingScripts/utilities/credentials.py     copied unchanged from topo-rapidmapping
processingScripts/utilities/proxy_handler.py   copied unchanged from topo-rapidmapping
requirements/requirements.txt                  dependencies
.claude/CLAUDE.md                              this file
secrets/                                       stac_credentials.json, proxy_config.json (git-ignored)
logs/                                          one log file per day (git-ignored via *.log)
```

- Only the GUI and `README.md` live in the project root. The GUI puts `processingScripts/` on
  `sys.path` (same pattern as `../topo-GDWHimport/GUI_GDWHimport.py`), so the scripts in there
  import each other by plain name (`from configuration import ...`, `from utilities import ...`).
- On start the GUI checks `REQUIRED_MODULES` and, only if one is missing, runs
  `pip install -r requirements/requirements.txt` with the same interpreter (`ensure_requirements`,
  before the core imports). A new dependency must be added to both `requirements.txt` and
  `REQUIRED_MODULES`.
- Keep the two files in `processingScripts/utilities/` identical to topo-rapidmapping. Fix bugs
  there first, then copy.
- No new module, class, or dependency without a brief justification. Only `requests` is required.
- Paths are anchored at the project root (`PROJECT_DIR` in `stac_asset_editor.py`, one level above
  `processingScripts/`), never at the working directory. `secrets/` and `logs/` stay in the root.

## Python 3.6 compatibility (hard requirement)

The tool must run on Python 3.6. Do not use anything newer:

- No walrus `:=`, no positional-only `/`, no `match`, no `f"{x=}"`, no `dict | dict`.
- No built-in generics (`list[str]`) or `X | None`; use `typing.List` / `Optional` or no hint.
- No `from __future__ import annotations` (3.7+), no `dataclasses` (3.7+).
- Inside f-string expressions: no backslash and no reuse of the enclosing quote character.
- Do not rely on `dict` ordering for anything that reaches the output; `DESCRIPTION_FIELDS`
  is a list of tuples for that reason.
- Stdlib calls must exist in 3.6 (e.g. no `logging.basicConfig(force=...)`,
  no `subprocess.run(capture_output=...)`).
- Python 3.6 is not installed on the development machine. After every change, check with
  `vermin --target=3.6- <files>` (expected result: "Minimum required versions: 3.6").

## GUI style

Look and feel follow `../topo-GDWHimport/GUI_GDWHimport.py`: `clam` theme, identical
`LIGHT` / `DARK` colour dictionaries, dark mode as default, header bar with the Dark/Hell
toggle, `Section.TLabelframe` with accent-coloured titles, Segoe UI 9 bold field labels,
Courier New 9 for URLs and log, dark title bar via DWM. The main action button is a `tk.Button`
whose text is amber while input is incomplete and green when ready. Raw `tk` widgets are not
reached by the ttk style and must be coloured in `_apply_theme`. Use `ttk.Scrollbar`, not
`scrolledtext`, so scrollbars follow the theme.

## STAC API facts (verified 2026-09-30)

- Transactional API: `https://<host>/api/stac/v0.9/`, Basic Auth, same as topo-rapidmapping.
  Spec: https://data.geo.admin.ch/api/stac/static/spec/v0.9/apitransactional.html
- Asset href: `https://<host>/<collection>/<item>/<asset>`
  maps to `collections/<collection>/items/<item>/assets/<asset>`.
- Hosts: INT `sys-data.int.bgdi.ch`, PROD `data.geo.admin.ch`.
- `PATCH` on an asset changes only the fields sent. `PUT` erases every optional field missing
  from the payload (title, gsd, proj:epsg, description, ...).
- Reading (GET) is public; credentials are needed only for writing.
- Field names differ per API version: v0.9 `eo:gsd` / `checksum:multihash`, v1 `gsd` / `file:checksum`.
  `description` is the same in both.
- Description format: `Name: value` pairs joined by `", "`, in this order: Area, TerrainModel,
  SourceReferenceSystem, CameraSystem, Acquisition time, LineId, Commentary. Multiple values
  inside one attribute are comma-separated without a space. Empty attributes are omitted.

## Critical domain logic (do not change without reason)

- **PATCH only, description only**: never send PUT and never send any field other than
  `description`. The tool must not alter the asset file, title, type, checksum, gsd or EPSG.
- **INT/PROD**: INT stays the default. The href host must match the selected environment,
  otherwise the asset is rejected. Never make PROD the default by accident.
- **No silent overwrite**: an asset that already has a description is skipped (WARNING) unless
  the user ticks the overwrite option. Writing always requires a confirmation dialog.
- **Exact text**: the description is written exactly as shown in the preview. Do not normalise,
  reformat or "correct" user input beyond trimming leading/trailing whitespace per attribute.
- **Credentials**: never commit, log, or include in error messages.

## Errors and logging

Error messages must be understandable to non-programmers: what happened, why, what to do.
Every asset ends with exactly one of SUCCESS / WARNING / ERROR. Use `logging`, not `print()`.
Code comments and user-facing texts are in German.

## Process for every change

1. Read the existing code before changing anything.
2. Look for the smallest solution.
3. No incidental refactoring, no unnecessary renaming.
4. Test with "Prüfen (nichts schreiben)" first; test real writes on INT before PROD.
5. Report briefly at the end: Changed / Tested / Risks.
6. `git add`, `git commit`, `git push` are done by the user, never by Claude.
