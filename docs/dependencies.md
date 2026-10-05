# Distribution and dependencies

Production browser runtime: zero third-party dependencies. No remote requests are needed to process local CSV data. All fixtures are synthetic and authored for this project.

Development-only: @playwright/test 1.56.0 from the npm registry (Apache-2.0); its transitive package metadata remains in package-lock.json. No downloaded implementations are included in release ZIPs. QGIS/PyQGIS and DejaVu fonts are installed only in hosted verification from Ubuntu distribution packages. They are not bundled, copied, linked as runtime libraries, or published with the app. This project is a standalone CSV/XML producer, not a QGIS plugin.

The distribution script uses an exact positive file allowlist. It rejects symlinks, excluded directories, unexpected binary content and unlisted artifacts. Native PNG evidence may show only our synthetic points/text; it must not contain basemaps or external datasets. Source/license choices for a public repository are handled separately; no license grant is invented here.
