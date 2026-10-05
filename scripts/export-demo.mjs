import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { exportFiles, exportZip } from '../src/export.mjs';

// Usage: node scripts/export-demo.mjs [output-directory] [request.json]
// The optional request is a test adapter, not an alternate reconciliation path.
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const out = path.resolve(process.argv[2] || path.join(root, 'artifacts/demo'));
const request = process.argv[3]
  ? JSON.parse(await fs.readFile(path.resolve(process.argv[3]), 'utf8'))
  : {
      oldCSV: await fs.readFile(path.join(root, 'fixtures/old.csv'), 'utf8'),
      newCSV: await fs.readFile(path.join(root, 'fixtures/new.csv'), 'utf8'),
      oldCRS: 'EPSG:3857',
      newCRS: 'EPSG:3857',
      decisions: JSON.parse(await fs.readFile(path.join(root, 'fixtures/decisions.json'), 'utf8')),
    };
const { decisions = {}, ...input } = request;
const files = await exportFiles(input, decisions);
const zip = await exportZip(input, decisions);
await fs.mkdir(out, { recursive: true });
for (const [name, contents] of Object.entries(files)) {
  await fs.writeFile(path.join(out, name), contents);
}
await fs.writeFile(path.join(out, 'input.json'), JSON.stringify({ ...input, decisions }, null, 2));
await fs.writeFile(path.join(out, 'label-rebase-demo.zip'), zip);
console.log(`Exported ${out}`);
