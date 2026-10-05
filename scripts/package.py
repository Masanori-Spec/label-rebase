"""Freeze an exact positive allowlist; distribute original source/data only."""
from pathlib import Path
import argparse, hashlib, json, zipfile
parser=argparse.ArgumentParser();parser.add_argument('--final',action='store_true');args=parser.parse_args()
root=Path(__file__).resolve().parents[1];out=root.parent/'label-rebase-output';out.mkdir(exist_ok=True)
FILES='''.gitignore
.github/workflows/native-gate.yml
.github/workflows/verify.yml
README.md
package.json
package-lock.json
dist/index.html
src/core.mjs
src/export.mjs
src/zip.mjs
src/project.mjs
src/demo.mjs
web/index.html
web/styles.css
web/i18n.mjs
web/app.mjs
tests/core.test.mjs
tests/project.test.mjs
tests/server.test.mjs
tests/browser.mjs
oracle/reference.py
oracle/test_rebase.py
oracle/test_bundle.py
oracle/README.md
oracle/fixtures/canonical.json
oracle/fixtures/canonical-expected.csv
oracle/fixtures/precision-boundary.json
oracle/fixtures/precision-boundary-expected.csv
scripts/build.mjs
scripts/serve.mjs
scripts/server-path.mjs
scripts/solve-json.mjs
scripts/export-demo.mjs
scripts/native-qgis.py
scripts/freeze-gate.py
scripts/verify-bundle.py
scripts/verify-boundary.mjs
scripts/package.py
fixtures/old.csv
fixtures/new.csv
fixtures/decisions.json
docs/sources.md
docs/dependencies.md
docs/native-contract.md
docs/qgis-export-guide.md
docs/product-scope.md
docs/verification.md
evidence/native-gate.json'''.splitlines()
if args.final:
 FILES+='''evidence/hosted-verification.json
evidence/browser-verification.json
evidence/native-cli.json
evidence/native-browser.json
evidence/desktop-ja.png
evidence/mobile-ja.png
evidence/desktop-en.png
evidence/mobile-en.png'''.splitlines()
manifest=[]
for rel in sorted(FILES):
 p=root/rel;assert p.is_file() and not p.is_symlink(),f'Missing/symlink: {rel}'
 assert not any(x in p.parts for x in ('node_modules','__pycache__','.toolchain','test-results')),rel
 raw=p.read_bytes();assert len(raw)<2_000_000,rel
 if p.suffix=='.png':assert rel.startswith('evidence/') and raw[:8]==b'\x89PNG\r\n\x1a\n'
 else:raw.decode('utf8');assert b'\0' not in raw,rel
 manifest.append({'path':rel,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
archive=out/'label-rebase-source.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
 for row in manifest:
  info=zipfile.ZipInfo(row['path'],date_time=(2026,10,5,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,(root/row['path']).read_bytes())
with zipfile.ZipFile(archive) as z:
 assert sorted(z.namelist())==sorted(FILES)
 for row in manifest:assert hashlib.sha256(z.read(row['path'])).hexdigest()==row['sha256']
report={'project':'LabelRebase','version':'0.1.0','status':'final evidence included' if args.final else 'release candidate; complete hosted UI CI pending','fileCount':len(manifest),'files':manifest,'archive':{'name':archive.name,'bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()},'distribution':'Exact positive allowlist: original code, synthetic inputs, authored XML, docs and our own numerical/PNG evidence only. No QGIS/font/browser/dependency binaries, basemaps, private data or patent material.'}
(out/'label-rebase-source-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
(out/'label-rebase.html').write_bytes((root/'dist/index.html').read_bytes())
(out/'label-rebase-example.zip').write_bytes((root/'artifacts/demo/label-rebase-demo.zip').read_bytes())
print(json.dumps({'fileCount':len(manifest),**report['archive']},indent=2))
