"""Create an exact, own-source-only WIP native gate snapshot."""
from pathlib import Path
import json,hashlib,zipfile
root=Path(__file__).resolve().parents[1];out=root.parent/'label-rebase-output';out.mkdir(exist_ok=True)
files='''.gitignore
.github/workflows/native-gate.yml
README.md
package.json
package-lock.json
src/core.mjs
src/export.mjs
src/zip.mjs
scripts/export-demo.mjs
scripts/solve-json.mjs
scripts/native-qgis.py
scripts/freeze-gate.py
fixtures/old.csv
fixtures/new.csv
fixtures/decisions.json
tests/core.test.mjs
docs/sources.md
docs/dependencies.md
docs/native-contract.md'''.splitlines()
items=[]
for rel in sorted(files):
 p=root/rel;assert p.is_file() and not p.is_symlink(),rel
 b=p.read_bytes();b.decode('utf8');assert b'\0' not in b and len(b)<1000000
 items.append({'path':rel,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()})
archive=out/'label-rebase-native-gate-source.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
 for i in items:
  info=zipfile.ZipInfo(i['path'],date_time=(2026,10,5,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,(root/i['path']).read_bytes())
report={'status':'WIP native consumer gate, not a verified release','project':'LabelRebase','files':items,'archive':{'name':archive.name,'bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()},'exclusions':'No vendor binaries, fonts, basemaps, real datasets, private notes or patent material'}
(out/'label-rebase-native-gate-manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report['archive']))
