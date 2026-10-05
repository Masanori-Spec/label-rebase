/**
 * Authored end-to-end QA for the actual distributable LabelRebase app.
 * Run only on a GitHub-hosted Ubuntu 22.04 runner. Never remove the sandbox.
 * BASE_URL can point at the built single-file app; the default serves modules.
 * This test does not import the app's reconciliation or export implementation.
 */
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {chromium, expect as baseExpect} from '@playwright/test';

const ROOT = path.resolve(process.env.LABEL_REBASE_PROJECT_DIR || process.env.PROJECT_DIR || fileURLToPath(new URL('..', import.meta.url)));
const OUT = path.join(ROOT, 'artifacts', 'browser');
const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:4173/web/';
const OLD = await readFile(path.join(ROOT, 'fixtures', 'old.csv'), 'utf8');
const NEW = await readFile(path.join(ROOT, 'fixtures', 'new.csv'), 'utf8');
const DECISIONS = {A: 'follow', B: 'keep', D: 'follow'};
const DEFAULT_OLD = {key: 'key', x: 'x', y: 'y', labelX: 'label_x', labelY: 'label_y', rotation: 'rotation', show: 'show'};
const DEFAULT_NEW = {key: 'key', x: 'x', y: 'y', text: 'text'};
const ERRORS = [];
const report = {ok: false, baseURL: BASE_URL, commit: process.env.GITHUB_SHA || null, startedAt: new Date().toISOString(), checks: [], screenshots: [], downloads: [], errors: ERRORS};
let browser;
let currentPage;
let failure;

const expect = baseExpect.configure({timeout: 8000});
await mkdir(OUT, {recursive: true});

async function check(name, action) {
  const entry = {name, ok: false};
  report.checks.push(entry);
  try {
    const detail = await action();
    entry.ok = true;
    if (detail !== undefined) entry.detail = detail;
    console.log(`PASS ${name}`);
  } catch (error) {
    entry.error = error.stack || String(error);
    throw error;
  }
}

async function screenshot(page, name) {
  await page.screenshot({path: path.join(OUT, name), fullPage: true, animations: 'disabled'});
  report.screenshots.push(name);
}

async function noOverflow(page) {
  const dimensions = await page.evaluate(() => ({viewport: innerWidth, document: document.documentElement.scrollWidth, body: document.body.scrollWidth}));
  assert.ok(dimensions.document <= dimensions.viewport + 1, `Document horizontal overflow: ${JSON.stringify(dimensions)}`);
  assert.ok(dimensions.body <= dimensions.viewport + 1, `Body horizontal overflow: ${JSON.stringify(dimensions)}`);
  return dimensions;
}

async function assertCleared(page) {
  // No auto-wait here: stale exports/results must be invalidated by the input
  // event itself, before parsing an imported file or doing another analysis.
  assert.equal(await page.locator('#export').isDisabled(), true, 'A changed input left an old export enabled');
  assert.equal(await page.locator('#saveProject').isDisabled(), true, 'A changed input left an old project save enabled');
  assert.equal(await page.locator('[data-decision-key]').count(), 0, 'Old decision controls survived an input change');
  const result = page.locator('#result');
  assert.ok(!(await result.isVisible()) || (await result.innerText()).trim() === '', 'Old results remain visible after an input change');
}

async function assertBlocked(page) {
  await expect(page.locator('#export')).toBeDisabled();
  await expect(page.locator('#saveProject')).toBeDisabled();
  await expect(page.locator('#status')).toHaveAttribute('data-kind', 'error');
  await expect(page.locator('#status')).not.toHaveText('');
  assert.equal(await page.locator('[data-decision-key]').count(), 0);
  const result = page.locator('#result');
  assert.ok(!(await result.isVisible()) || (await result.innerText()).trim() === '', 'Invalid input kept stale result cards');
}

async function pendingDemo(page) {
  await page.locator('#demo').click();
  await expect(page.locator('#oldCSV')).toHaveValue(OLD);
  await expect(page.locator('#newCSV')).toHaveValue(NEW);
  await expect(page.locator('#oldCRS')).toHaveValue('EPSG:3857');
  await expect(page.locator('#newCRS')).toHaveValue('EPSG:3857');
  await page.locator('#analyze').click();
  await expect(page.locator('[data-decision-key]')).toHaveCount(3);
  const keys = await page.locator('[data-decision-key]').evaluateAll(nodes => nodes.map(node => node.dataset.decisionKey).sort());
  assert.deepEqual(keys, ['A', 'B', 'D']);
  for (const key of keys) await expect(page.locator(`[data-decision-key="${key}"]`)).toHaveValue('');
  await expect(page.locator('#export')).toBeDisabled();
}

async function choose(page, decisions = DECISIONS) {
  for (const [key, value] of Object.entries(decisions)) await page.locator(`[data-decision-key="${key}"]`).selectOption(value);
  await expect(page.locator('#export')).toBeEnabled();
}

async function readyDemo(page) {
  await pendingDemo(page);
  await choose(page);
}

async function assertDecisions(page, decisions = DECISIONS) {
  for (const [key, value] of Object.entries(decisions)) await expect(page.locator(`[data-decision-key="${key}"]`)).toHaveValue(value);
}

async function saveDownload(page, selector, filename, suggestedName) {
  const waiting = page.waitForEvent('download');
  await page.locator(selector).click();
  const download = await waiting;
  assert.equal(await download.failure(), null);
  if (suggestedName) assert.equal(download.suggestedFilename(), suggestedName);
  else assert.match(download.suggestedFilename(), /\.zip$/i);
  const destination = path.join(OUT, filename);
  await download.saveAs(destination);
  const bytes = await readFile(destination);
  assert.ok(bytes.length > 0);
  report.downloads.push({filename, suggestedFilename: download.suggestedFilename(), bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex')});
  return destination;
}

async function verifyDownloadedZip(zipPath, request, name) {
  // Python reads the exact browser download, checks safe/unique members and
  // CRCs, extracts it, and passes those bytes to the independent Decimal oracle.
  // No browser-side ZIP parser or producer function can supply the expectation.
  const destination = path.join(OUT, name);
  const inputPath = path.join(OUT, `${name}-input.json`);
  await writeFile(inputPath, JSON.stringify(request, null, 2) + '\n');
  execFileSync('python3', ['-c', `
import pathlib, shutil, sys, zipfile
source, target = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
assert not target.exists(), 'Refuse stale extracted artifacts; start from a fresh checkout'
target.mkdir(parents=True)
required = {'rebased.csv','rebased.csvt','rebased.qml','rebased.qgs','decisions.json','labelrebase-project.json','README.txt'}
with zipfile.ZipFile(source) as archive:
    names = archive.namelist()
    assert len(names) == len(set(names)) and set(names) == required, 'Unexpected or duplicate archive members'
    assert archive.testzip() is None, 'ZIP CRC failure'
    for member in archive.infolist():
        assert member.filename in required and not member.is_dir(), 'Unsafe archive path'
        assert member.file_size <= 8_000_000, 'Unexpected expanded archive size'
        (target / member.filename).write_bytes(archive.read(member))
shutil.copyfile(source, target / 'downloaded.zip')
`, zipPath, destination], {cwd: ROOT, encoding: 'utf8', timeout: 30000});
  const text = execFileSync('python3', [path.join(ROOT, 'scripts', 'verify-bundle.py'), destination, '--input', inputPath], {cwd: ROOT, encoding: 'utf8', timeout: 30000});
  const verified = JSON.parse(text);
  assert.equal(verified.ok, true);
  assert.ok(verified.verified.includes('ZIP CRC and member equality'));
  await writeFile(path.join(OUT, `${name}-verification.json`), JSON.stringify(verified, null, 2) + '\n');
  return verified;
}

async function openPage(viewport, mobile = false) {
  const context = await browser.newContext({viewport, deviceScaleFactor: 1, isMobile: mobile, hasTouch: mobile, acceptDownloads: true, locale: 'ja-JP', reducedMotion: 'reduce'});
  const page = await context.newPage();
  currentPage = page;
  page.setDefaultTimeout(10000);
  page.on('pageerror', error => ERRORS.push({kind: 'pageerror', message: error.message}));
  page.on('console', message => {if (message.type() === 'error') ERRORS.push({kind: 'console', message: message.text()});});
  page.on('dialog', async dialog => {ERRORS.push({kind: 'unexpected-dialog', message: dialog.message()}); await dialog.dismiss();});
  page.on('requestfailed', request => ERRORS.push({kind: 'requestfailed', url: request.url(), message: request.failure()?.errorText}));
  const response = await page.goto(BASE_URL, {waitUntil: 'networkidle'});
  assert.ok(response?.ok(), `App HTTP status: ${response?.status()}`);
  await expect(page.locator('#status')).toHaveAttribute('role', 'status');
  await expect(page.locator('h1')).toBeVisible();
  await expect(page.locator('#lang')).toHaveValue('ja');
  await expect(page.locator('html')).toHaveAttribute('lang', 'ja');
  return page;
}

async function keyboardAudit(page) {
  const required = new Set(['lang', 'demo', 'oldCSV', 'newCSV', 'oldCRS', 'newCRS', 'analyze', 'clear', 'saveProject', 'export']);
  const visited = new Set();
  const evidence = [];
  await page.locator('#lang').focus();
  for (let count = 0; count < 90 && [...required].some(id => !visited.has(id)); count++) {
    await page.keyboard.press('Tab');
    const item = await page.evaluate(() => {
      const node = document.activeElement;
      const style = getComputedStyle(node);
      const rect = node.getBoundingClientRect();
      return {id: node.id, tag: node.tagName, visible: rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.top < innerHeight, focusVisible: node.matches(':focus-visible'), outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth, boxShadow: style.boxShadow};
    });
    if (required.has(item.id)) {
      assert.equal(item.visible, true, `Keyboard focus not visible: ${item.id}`);
      assert.equal(item.focusVisible, true, `No :focus-visible state: ${item.id}`);
      assert.ok((item.outlineStyle !== 'none' && parseFloat(item.outlineWidth) > 0) || item.boxShadow !== 'none', `No visible focus indicator: ${item.id}`);
      visited.add(item.id);
      evidence.push(item);
    }
  }
  assert.deepEqual([...required].filter(id => !visited.has(id)), [], 'Required controls unreachable by Tab');
  const unlabeled = await page.locator('input, textarea, select').evaluateAll(nodes => nodes.filter(node => node.type !== 'hidden' && !node.disabled && !(node.labels?.length || node.getAttribute('aria-label')?.trim() || node.getAttribute('aria-labelledby')?.trim())).map(node => node.id || node.outerHTML.slice(0, 160)));
  assert.deepEqual(unlabeled, [], 'Form controls need accessible names');
  await page.locator('.skip').focus();
  const focusedSkip = await page.locator('.skip').evaluate(node => ({clip: getComputedStyle(node).clipPath, width: node.getBoundingClientRect().width}));
  assert.equal(focusedSkip.clip, 'none');
  assert.ok(focusedSkip.width > 20, 'Focused skip link must be visible and usable');
  await page.locator('#demo').focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('#oldCSV')).toHaveValue(OLD);
  return {requiredControls: [...visited], focusIndicators: evidence};
}

try {
  await check('Hosted Ubuntu 22.04 execution boundary', async () => {
    const release = await readFile('/etc/os-release', 'utf8');
    assert.equal(process.env.GITHUB_ACTIONS, 'true', 'Browser QA runs only in GitHub Actions; do not launch a local/cloud browser');
    assert.equal(process.env.RUNNER_ENVIRONMENT, 'github-hosted', 'Only GitHub-hosted runners are supported');
    assert.equal(process.env.RUNNER_OS, 'Linux');
    assert.match(release, /^ID=ubuntu$/m);
    assert.match(release, /^VERSION_ID="22\.04"$/m);
    assert.notEqual(process.getuid?.(), 0, 'Do not run Chromium as root or disable its sandbox');
    return {runner: process.env.RUNNER_ENVIRONMENT, os: 'Ubuntu 22.04', uid: process.getuid?.()};
  });
  browser = await chromium.launch({chromiumSandbox: true, args: []});
  await check('Chromium sandbox command line independently inspected', async () => {
    const session = await browser.newBrowserCDPSession();
    const {arguments: commandLine} = await session.send('Browser.getBrowserCommandLine');
    await session.detach();
    const forbidden = commandLine.filter(arg => /^--(?:no-sandbox|disable-setuid-sandbox|disable-namespace-sandbox)(?:=|$)/.test(arg));
    if (forbidden.length) {
      await browser.close();
      throw new Error(`Unsafe Chromium launch explicitly stopped: ${forbidden.join(' ')}`);
    }
    report.browser = {version: browser.version(), chromiumSandbox: true, commandLine};
    return {chromiumSandbox: true, forbiddenFlags: forbidden};
  });

  const page = await openPage({width: 1360, height: 900});
  await check('Japanese desktop initial state and layout', async () => {
    await expect(page.locator('#export')).toBeDisabled();
    const dimensions = await noOverflow(page);
    await screenshot(page, 'desktop-ja-initial.png');
    return dimensions;
  });
  await check('All moved pinned labels require explicit decisions', async () => {
    await pendingDemo(page);
    await page.locator('[data-decision-key="A"]').selectOption('follow');
    await expect(page.locator('#export')).toBeDisabled();
    await page.locator('[data-decision-key="B"]').selectOption('keep');
    await expect(page.locator('#export')).toBeDisabled();
    await screenshot(page, 'desktop-ja-pending.png');
    await page.locator('[data-decision-key="D"]').selectOption('follow');
    await expect(page.locator('#export')).toBeEnabled();
    await assertDecisions(page);
    await expect(page.locator('#result tbody tr').filter({hasText: 'Charlie'}).locator('td').nth(5)).toHaveText('自動配置');
    const skipStyle = await page.locator('.skip').evaluate(node => ({clip: getComputedStyle(node).clipPath, width: node.getBoundingClientRect().width}));
    assert.notEqual(skipStyle.clip, 'none', 'Unfocused skip link must be clipped, not painted outside the viewport');
    assert.equal(skipStyle.width, 1);
    await screenshot(page, 'desktop-ja-ready.png');
    await noOverflow(page);
  });
  await check('Japanese and English preserve current inputs and decisions', async () => {
    const selectors = ['#demo', '#clear', '#analyze', '#saveProject', '#export'];
    const japanese = await Promise.all(selectors.map(selector => page.locator(selector).innerText()));
    for (const text of japanese) assert.match(text, /[\u3040-\u30ff\u3400-\u9fff]/, 'Japanese control label missing');
    await page.locator('#lang').selectOption('en');
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    const english = await Promise.all(selectors.map(selector => page.locator(selector).innerText()));
    for (let index = 0; index < selectors.length; index++) {
      assert.notEqual(english[index], japanese[index], `Control did not translate: ${selectors[index]}`);
      assert.doesNotMatch(english[index], /[\u3040-\u30ff\u3400-\u9fff]/);
    }
    await assertDecisions(page);
    await expect(page.locator('#oldCSV')).toHaveValue(OLD);
    await expect(page.locator('#newCSV')).toHaveValue(NEW);
    await expect(page.locator('#export')).toBeEnabled();
    await noOverflow(page);
    await screenshot(page, 'desktop-en-ready.png');
    await page.locator('#lang').selectOption('ja');
    await assertDecisions(page);
    await expect(page.locator('#export')).toBeEnabled();
    return {japanese, english};
  });

  const request = {oldCSV: OLD, newCSV: NEW, oldCRS: 'EPSG:3857', newCRS: 'EPSG:3857', oldMapping: DEFAULT_OLD, newMapping: DEFAULT_NEW, decisions: DECISIONS};
  let savedProject;
  let savedProjectPath;
  await check('Exact downloaded ZIP passes independent Python bundle and Decimal verification', async () => {
    const zipPath = await saveDownload(page, '#export', 'downloaded.zip');
    return await verifyDownloadedZip(zipPath, request, 'extracted');
  });
  await check('Project download preserves both CSVs, CRS, mappings, and decisions', async () => {
    savedProjectPath = await saveDownload(page, '#saveProject', 'labelrebase-project.json', 'labelrebase-project.json');
    savedProject = JSON.parse(await readFile(savedProjectPath, 'utf8'));
    assert.equal(savedProject.format, 'label-rebase-project');
    assert.equal(savedProject.version, 1);
    assert.deepEqual(savedProject.decisions, DECISIONS);
    for (const key of ['oldCSV', 'newCSV', 'oldCRS', 'newCRS', 'oldMapping', 'newMapping']) assert.deepEqual(savedProject.input[key], request[key]);
  });
  await check('Keyboard traversal, activation, and visible focus', async () => keyboardAudit(page));
  await check('Clear resets sources, decisions, results, and export', async () => {
    await readyDemo(page);
    await page.locator('#clear').click();
    await expect(page.locator('#oldCSV')).toHaveValue('');
    await expect(page.locator('#newCSV')).toHaveValue('');
    await assertCleared(page);
    await noOverflow(page);
  });
  await check('Saved project import restores a newly analyzed ready result', async () => {
    await page.locator('#projectFile').setInputFiles(savedProjectPath);
    await expect(page.locator('#oldCSV')).toHaveValue(OLD);
    await expect(page.locator('#newCSV')).toHaveValue(NEW);
    await assertDecisions(page);
    await expect(page.locator('#export')).toBeEnabled();
    await screenshot(page, 'desktop-project-restored.png');
  });

  const invalidCases = [
    {name: 'duplicate stable key', selector: '#oldCSV', value: OLD + 'A,0,0,12,8,0,1\n'},
    {name: 'one-sided label coordinates', selector: '#oldCSV', value: OLD.replace('A,0,0,12,8,0,1', 'A,0,0,12,,0,1')},
    {name: 'non-finite point coordinate', selector: '#newCSV', value: NEW.replace('A,10,20,Alpha', 'A,NaN,20,Alpha')},
    {name: 'mismatched declared projected CRS', selector: '#newCRS', value: 'EPSG:3395'},
    {name: 'unsupported geographic CRS', selector: '#oldCRS', value: 'EPSG:4326'},
    {name: 'malformed quoted CSV', selector: '#oldCSV', value: 'key,x,y,label_x,label_y\nA,0,0,"12,8\n'},
  ];
  for (const invalid of invalidCases) {
    await check(`Edits invalidate ready exports and block ${invalid.name}`, async () => {
      await readyDemo(page);
      await page.locator(invalid.selector).fill(invalid.value);
      await assertCleared(page);
      await page.locator('#analyze').click();
      await assertBlocked(page);
      await noOverflow(page);
      return {status: await page.locator('#status').innerText()};
    });
  }
  await check('Out-of-range follow arithmetic blocks both downloads and recovers without an exception', async () => {
    const errorsBefore = ERRORS.length;
    await page.locator('#demo').click();
    await page.locator('#oldCSV').fill('key,x,y,label_x,label_y,rotation,show\nA,1e12,0,1e-30,0,0,1\n');
    await page.locator('#newCSV').fill('key,x,y,text\nA,-1e12,0,Alpha\n');
    await page.locator('#analyze').click();
    await expect(page.locator('[data-decision-key]')).toHaveCount(1);
    await page.locator('[data-decision-key="A"]').selectOption('keep');
    await expect(page.locator('#export')).toBeEnabled();
    await expect(page.locator('#saveProject')).toBeEnabled();
    await page.locator('[data-decision-key="A"]').selectOption('follow');
    await expect(page.locator('#export')).toBeDisabled();
    await expect(page.locator('#saveProject')).toBeDisabled();
    await expect(page.locator('#status')).toHaveAttribute('data-kind', 'error');
    await expect(page.locator('#status')).not.toHaveText('');
    await expect(page.locator('[data-decision-key="A"]')).toHaveValue('follow');
    assert.equal(ERRORS.length, errorsBefore, 'Invalid follow arithmetic caused an uncaught browser error');
    await screenshot(page, 'desktop-arithmetic-range-blocked.png');
    await page.locator('[data-decision-key="A"]').selectOption('keep');
    await expect(page.locator('#export')).toBeEnabled();
    await expect(page.locator('#saveProject')).toBeEnabled();
    await expect(page.locator('#status')).toHaveAttribute('data-kind', 'ready');
    assert.equal(ERRORS.length, errorsBefore);
  });
  await check('Exact cancellation of wide intermediate arithmetic leaves the tiny final anchor exportable', async () => {
    const errorsBefore = ERRORS.length;
    await page.locator('#demo').click();
    await page.locator('#oldCSV').fill('key,x,y,label_x,label_y,rotation,show\nA,1e12,0,1e12,0,0,1\n');
    await page.locator('#newCSV').fill('key,x,y,text\nA,1e-30,0,Alpha\n');
    await page.locator('#analyze').click();
    await expect(page.locator('[data-decision-key]')).toHaveCount(1);
    await page.locator('[data-decision-key="A"]').selectOption('follow');
    await expect(page.locator('#export')).toBeEnabled();
    await expect(page.locator('#saveProject')).toBeEnabled();
    await expect(page.locator('#status')).toHaveAttribute('data-kind', 'ready');
    await expect(page.locator('.choice-effect')).toContainText(`0.${'0'.repeat(29)}1, 0`);
    assert.equal(ERRORS.length, errorsBefore, 'Exact cancellation caused an uncaught browser error');
    await screenshot(page, 'desktop-arithmetic-cancellation-ready.png');
  });
  await check('Mapping changes invalidate results and duplicate roles block export', async () => {
    await readyDemo(page);
    await page.locator('[data-map-side="old"][data-map-role="x"]').selectOption('y');
    await assertCleared(page);
    await page.locator('#analyze').click();
    await assertBlocked(page);
    await page.locator('[data-map-side="old"][data-map-role="x"]').selectOption('x');
    await page.locator('#analyze').click();
    for (const key of ['A', 'B', 'D']) await expect(page.locator(`[data-decision-key="${key}"]`)).toHaveValue('');
    await expect(page.locator('#export')).toBeDisabled();
  });
  await check('Optional none mappings survive locale changes and saved-project restore', async () => {
    await readyDemo(page);
    for (const role of ['rotation', 'show']) {
      await page.locator(`[data-map-side="old"][data-map-role="${role}"]`).selectOption('');
      await assertCleared(page);
    }
    await page.locator('#analyze').click();
    await choose(page);
    for (const locale of ['en', 'ja']) {
      await page.locator('#lang').selectOption(locale);
      await expect(page.locator('html')).toHaveAttribute('lang', locale);
      for (const role of ['rotation', 'show']) await expect(page.locator(`[data-map-side="old"][data-map-role="${role}"]`)).toHaveValue('');
      await assertDecisions(page);
      await expect(page.locator('#export')).toBeEnabled();
    }
    const projectPath = await saveDownload(page, '#saveProject', 'optional-none-project.json', 'labelrebase-project.json');
    const project = JSON.parse(await readFile(projectPath, 'utf8'));
    assert.equal(project.input.oldMapping.rotation, '');
    assert.equal(project.input.oldMapping.show, '');
    await page.locator('#clear').click();
    await page.locator('#projectFile').setInputFiles(projectPath);
    await assertDecisions(page);
    for (const role of ['rotation', 'show']) await expect(page.locator(`[data-map-side="old"][data-map-role="${role}"]`)).toHaveValue('');
    await expect(page.locator('#export')).toBeEnabled();
  });
  await check('Valid CSV file imports invalidate and reanalyze; repeated same files work', async () => {
    for (let repeat = 0; repeat < 2; repeat++) {
      await readyDemo(page);
      await page.locator('#oldFile').setInputFiles({name: 'old.csv', mimeType: 'text/csv', buffer: Buffer.from(OLD)});
      await assertCleared(page);
      await expect(page.locator('#oldCSV')).toHaveValue(OLD);
      await page.locator('#newFile').setInputFiles({name: 'new.csv', mimeType: 'text/csv', buffer: Buffer.from(NEW)});
      await assertCleared(page);
      await expect(page.locator('#newCSV')).toHaveValue(NEW);
      await page.locator('#analyze').click();
      for (const key of ['A', 'B', 'D']) await expect(page.locator(`[data-decision-key="${key}"]`)).toHaveValue('');
      await choose(page);
    }
  });
  await check('Malformed CSV file imports cannot leave stale exports enabled', async () => {
    const malformed = 'key,x,y,label_x,label_y\nA,0,0,"unterminated';
    for (let repeat = 0; repeat < 2; repeat++) {
      await readyDemo(page);
      await page.locator('#oldFile').setInputFiles({name: 'broken.csv', mimeType: 'text/csv', buffer: Buffer.from(malformed)});
      await assertCleared(page);
      await page.locator('#analyze').click();
      await assertBlocked(page);
    }
  });
  await check('Malformed, unsupported, and semantically invalid projects clear old results', async () => {
    const invalidProjects = [
      '{"format":',
      JSON.stringify({...savedProject, version: 999}),
      JSON.stringify({...savedProject, decisions: {A: 'not-a-policy'}}),
      JSON.stringify({...savedProject, input: {...savedProject.input, newCSV: NEW.replace('A,10,20,Alpha', 'A,NaN,20,Alpha')}}),
    ];
    for (const text of invalidProjects) {
      await readyDemo(page);
      await page.locator('#projectFile').setInputFiles({name: 'invalid-project.json', mimeType: 'application/json', buffer: Buffer.from(text)});
      await assertCleared(page);
      await expect(page.locator('#status')).toHaveAttribute('data-kind', 'error');
      await expect(page.locator('#status')).not.toHaveText('');
      await expect(page.locator('#export')).toBeDisabled();
    }
    // The same valid file can recover from a failed import repeatedly.
    for (let repeat = 0; repeat < 2; repeat++) {
      await page.locator('#projectFile').setInputFiles(savedProjectPath);
      await assertDecisions(page);
      await expect(page.locator('#export')).toBeEnabled();
      if (!repeat) await page.locator('#clear').click();
    }
  });
  await check('Custom-header mappings and reset policy survive an independently verified export', async () => {
    const oldMapping = {key: 'identifier', x: 'easting', y: 'northing', labelX: 'label_e', labelY: 'label_n', rotation: 'angle', show: 'visible'};
    const newMapping = {key: 'stable', x: 'new_e', y: 'new_n', text: 'caption'};
    const oldCSV = OLD.replace(OLD.split('\n')[0], 'identifier,easting,northing,label_e,label_n,angle,visible');
    const newCSV = NEW.replace(NEW.split('\n')[0], 'stable,new_e,new_n,caption');
    await readyDemo(page);
    await page.locator('#oldCSV').fill(oldCSV);
    await assertCleared(page);
    await page.locator('#newCSV').fill(newCSV);
    await assertCleared(page);
    for (const [side, mapping] of [['old', oldMapping], ['new', newMapping]]) {
      for (const [role, column] of Object.entries(mapping)) await page.locator(`[data-map-side="${side}"][data-map-role="${role}"]`).selectOption(column);
    }
    await page.locator('#analyze').click();
    const decisions = {A: 'reset', B: 'keep', D: 'follow'};
    await choose(page, decisions);
    const zipPath = await saveDownload(page, '#export', 'custom-mapping-reset.zip');
    const verified = await verifyDownloadedZip(zipPath, {oldCSV, newCSV, oldCRS: 'EPSG:3857', newCRS: 'EPSG:3857', oldMapping, newMapping, decisions}, 'custom-extracted');
    await screenshot(page, 'desktop-custom-mapping-reset.png');
    return verified;
  });
  await check('HTML-like label text is displayed literally without DOM execution', async () => {
    await readyDemo(page);
    const title = await page.title();
    const malicious = '<img src=x onerror=alert(42)>';
    await page.locator('#newCSV').fill(NEW.replace('Alpha', malicious));
    await assertCleared(page);
    await page.locator('#analyze').click();
    await choose(page);
    await expect(page.locator('#result')).toContainText(malicious);
    await expect(page.locator('#result img')).toHaveCount(0);
    assert.equal(await page.title(), title);
    await noOverflow(page);
    await screenshot(page, 'desktop-literal-label.png');
  });

  await check('Standalone HTML works offline from file:// and exports an independently verified ZIP', async () => {
    const context = await browser.newContext({viewport: {width: 1360, height: 900}, deviceScaleFactor: 1, acceptDownloads: true, locale: 'ja-JP', reducedMotion: 'reduce', offline: true});
    const offlinePage = await context.newPage();
    currentPage = offlinePage;
    offlinePage.setDefaultTimeout(10000);
    offlinePage.on('pageerror', error => ERRORS.push({kind: 'offline-pageerror', message: error.message}));
    offlinePage.on('console', message => {if (message.type() === 'error') ERRORS.push({kind: 'offline-console', message: message.text()});});
    offlinePage.on('requestfailed', request => ERRORS.push({kind: 'offline-requestfailed', url: request.url(), message: request.failure()?.errorText}));
    offlinePage.on('dialog', async dialog => {ERRORS.push({kind: 'offline-unexpected-dialog', message: dialog.message()}); await dialog.dismiss();});
    await offlinePage.goto(pathToFileURL(path.join(ROOT, 'dist', 'index.html')).href, {waitUntil: 'load'});
    await expect(offlinePage.locator('h1')).toBeVisible();
    await expect(offlinePage.locator('#status')).toHaveAttribute('role', 'status');
    await readyDemo(offlinePage);
    const zipPath = await saveDownload(offlinePage, '#export', 'offline-downloaded.zip');
    const verified = await verifyDownloadedZip(zipPath, request, 'offline-extracted');
    await noOverflow(offlinePage);
    await screenshot(offlinePage, 'offline-file-ready.png');
    return {offline: true, protocol: 'file:', ...verified};
  });

  const mobile = await openPage({width: 390, height: 844}, true);
  await check('390×844 Japanese mobile layout and pending decisions', async () => {
    await noOverflow(mobile);
    await pendingDemo(mobile);
    await noOverflow(mobile);
    await screenshot(mobile, 'mobile-ja-pending.png');
    await choose(mobile);
    await noOverflow(mobile);
    await screenshot(mobile, 'mobile-ja-ready.png');
  });
  await check('390×844 English mobile layout preserves choices; edits still block export', async () => {
    await mobile.locator('#lang').selectOption('en');
    await expect(mobile.locator('html')).toHaveAttribute('lang', 'en');
    await assertDecisions(mobile);
    await expect(mobile.locator('#export')).toBeEnabled();
    await noOverflow(mobile);
    await screenshot(mobile, 'mobile-en-ready.png');
    await mobile.locator('#newCRS').fill('EPSG:3395');
    await assertCleared(mobile);
    await mobile.locator('#analyze').click();
    await assertBlocked(mobile);
    await noOverflow(mobile);
    await screenshot(mobile, 'mobile-en-invalid.png');
    await mobile.locator('#clear').click();
    await assertCleared(mobile);
  });
  await check('No uncaught errors, failed requests, or HTML-injection dialogs', async () => assert.deepEqual(ERRORS, []));
  report.ok = true;
} catch (error) {
  failure = error;
  report.failure = error.stack || String(error);
  if (currentPage && !currentPage.isClosed()) {
    try {await screenshot(currentPage, 'failure.png');} catch (screenshotError) {report.screenshotError = String(screenshotError);}
  }
} finally {
  if (browser) await browser.close();
  report.finishedAt = new Date().toISOString();
  await writeFile(path.join(OUT, 'report.json'), JSON.stringify(report, null, 2) + '\n');
}

if (failure) {
  console.error(failure.stack || failure);
  process.exitCode = 1;
} else {
  console.log(`PASS ${report.checks.length} browser checks; artifacts: ${OUT}`);
}
