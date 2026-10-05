# Product scope

LabelRebase helps a GIS user revisit intentional label placement after a point-data refresh. The bounded unit of value is a stable-key decision and a usable native handoff, not another generic validator.

## Input and matching

Old UTF-8 CSV: explicit stable string key, projected point X/Y and label X/Y; rotation and visibility are optional. New CSV: the same key definition, projected point X/Y and single-line label text. Both source declarations must be identical and belong to the supported projected CRS family. The source project must confirm that label positions share that coordinate frame.

Exact string equality is the only identity. `007`, `7`, and ` 7 ` are distinct. No provider FIDs, row numbers, Unicode normalization or proximity joins. Duplicate/missing keys, half-empty label coordinates, malformed CSV/numbers and incompatible CRS declarations block export.

Existing automatic labels remain automatic, retaining rotation and visibility. Moved pinned labels require a per-key choice: follow the displacement, keep absolute map coordinates, or reset manual position and rotation. Hidden state is preserved even when resetting. A bulk choice for currently unresolved items is available for more than 25 decisions; each key retains its own editable decision. New points become automatic. Removed keys receive a receipt and are not reassigned.

## Output and limits

Typed CSV, authored minimal QML, relative QGS, source-text SHA-256 receipt and reusable JSON containing both original inputs. Extra source columns are intentionally not copied into the minimal native CSV. New point coordinates and label text are preserved.

Maximum 5,000 data rows and 2 MB of UTF-8 bytes per CSV, whether pasted or loaded. At most 256 columns; each column name is at most 256 characters. Saved project JSON is limited to 13 MB of UTF-8 bytes. Numeric values must be within ±10¹² and at most 30 significant digits/decimal places; rotation is between -360 and360 degrees. Label text is at most500 characters. CSV arithmetic uses decimal integers; QGIS's Real fields and renderer ultimately use floating-point coordinates, so its precision and font availability still apply. Schema errors block output rather than trying to repair ambiguous data.

No QGZ/QGD reading, reprojection, arbitrary style round-trips, multiline/rule-based/polygon labeling or guaranteed collision-free layout. The preview shows anchor movement schematically and omits native text sizing, rotation and collision placement. It shows at most200 points, and the ledger shows at most100 rows; export includes all validated rows. Review in QGIS at the intended map scale.

## Alternatives and unvalidated assumptions

QGIS auxiliary storage, joins and field calculator expressions are existing manual alternatives. AttributeTransfer focuses on proximity; Project Packager packages dependencies. The workflow distinction here is deliberate stable-key movement policy plus native output and a source-hashed receipt. No market demand, paid customer usage, exclusive novelty or patentability has been established.
