/**
 * GitHub-hosted synthetic browser check for the local Winman review interface.
 * No real FS, Winman export, credentials, private paths or client values.
 */
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { mkdir } = require('node:fs/promises');
const { chromium } = require('playwright');

(async () => {
const pretendSourceId = 'SYNTHETIC:BS-A:42';
const fixture = {
  config: {},
  entries: [{
    source_id: pretendSourceId,
    caption: 'Invented trade creditors awaiting classification review',
    section: 'BS-A',
    amount: '12345678.90',
    previous_amount: '12340000.00',
    risk: 'Synthetic example only: deliberately needs an accountant decision.',
    target_hint: '',
    review_status: 'Needs review',
  }],
  fields: [{
    field_id: 'SYNTHETIC_LIABILITY_FIELD',
    section: 'BS-A',
    sheet: 'Invented_Native_Schedule',
    anchor_text: 'Synthetic trade creditors',
  }],
  warnings: [{
    code: 'SYNTHETIC_WARNING',
    severity: 'Review',
    title: 'Invented opening and closing creditor evidence requires attention',
    period: 'Synthetic FY 2025-26',
    source_period: 'Synthetic FY 2024-25',
    target_period: 'Synthetic FY 2025-26',
    tolerance: '0',
    difference: '5678.90',
    explanation: 'These numbers and names are invented solely to test the interface.',
    suggested_action: 'Review illustrative classifications; do not approve any return.',
    evidence: [{
      source: 'synthetic_very_long_reference_filename_for_wrapping_validation.xlsx',
      sheet: 'Synthetic_Long_Named_Statement_Of_Liabilities',
      cell: 'C224',
      description: 'Synthetic liability evidence with a deliberately very long caption that must wrap even at narrow viewport widths',
      amount: '12345678.90',
    }],
  }],
  issues: [],
  unresolved: [{ source_id: pretendSourceId }],
  latest_saved: null,
  latest_benchmark: null,
  latest_preflight: null,
  latest_entity_schema: null,
  latest_import_intake: null,
  entity_discovery: null,
};

const worker = spawn('python', [
  '-m', 'workbook_mapping_lab.review_browser', '--no-browser', '--port', '0',
], {
  env: { ...process.env, PYTHONPATH: 'src' },
  stdio: ['ignore', 'pipe', 'pipe'],
});
let browser;
try {
  const baseUrl = await new Promise((resolve, reject) => {
    let output = '';
    let errors = '';
    const timer = setTimeout(() => reject(new Error('Local synthetic server did not start')), 15000);
    worker.stdout.on('data', data => {
      output += String(data);
      const match = output.match(/http:\/\/127\.0\.0\.1:\d+\//);
      if (match) {
        clearTimeout(timer);
        resolve(match[0]);
      }
    });
    worker.stderr.on('data', data => { errors += String(data).slice(0, 600); });
    worker.on('error', err => { clearTimeout(timer); reject(err); });
    worker.on('exit', code => {
      clearTimeout(timer);
      reject(new Error('Local synthetic server exited ' + code + ': ' + errors));
    });
  });
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
  const externalRequests = [];
  page.on('request', request => {
    const url = new URL(request.url());
    if (url.hostname !== '127.0.0.1' && url.hostname !== 'localhost')
      externalRequests.push(url.origin);
  });
  await page.route('**/api/state', route => route.fulfill({
    status: 200, contentType: 'application/json; charset=utf-8',
    body: JSON.stringify(fixture),
  }));
  await page.goto(baseUrl, { waitUntil: 'load' });
  await page.waitForFunction(() => document.querySelector('#metric-extracted')?.textContent === '1');
  assert.equal(await page.locator('#metric-extracted').textContent(), '1');
  assert.equal(await page.locator('#unresolved-count').textContent(), '1');

  await page.locator('.tab[data-view="warnings"]').click();
  const warningButton = page.locator('#warning-list .warning-card').first();
  assert.equal(await warningButton.count(), 1);
  await warningButton.press('Space');
  assert.equal(await warningButton.getAttribute('aria-pressed'), 'true');
  assert.equal(await warningButton.evaluate(el => document.activeElement === el), true,
    'Space must preserve keyboard focus after selecting a warning');
  const focusOutlineWidth = await warningButton.evaluate(el => parseFloat(getComputedStyle(el).outlineWidth));
  assert.ok(focusOutlineWidth >= 2, 'Selected warning requires visible keyboard focus');
  assert.match(await page.locator('#warning-explanation').innerText(), /Source period: Synthetic FY 2024-25/);
  assert.equal(await page.locator('.evidence-line').count(), 1);

  await mkdir('test-artifacts', { recursive: true });
  await page.screenshot({ path: 'test-artifacts/synthetic-warning-wide.png', animations: 'disabled', scale: 'css' });

  await page.setViewportSize({ width: 320, height: 760 });
  const narrow = await page.evaluate(() => {
    const row = document.querySelector('.evidence-line');
    const first = row?.children[0]?.getBoundingClientRect();
    const second = row?.children[1]?.getBoundingClientRect();
    return {
      pageScrollWidth: document.documentElement.scrollWidth,
      width: window.innerWidth,
      gridColumns: row ? getComputedStyle(row).gridTemplateColumns : '',
      labelBottom: first?.bottom ?? 0,
      amountTop: second?.top ?? 0,
    };
  });
  assert.ok(narrow.pageScrollWidth <= narrow.width + 2,
    'Warnings page must not create document-wide horizontal overflow at 320 CSS px: ' + JSON.stringify(narrow));
  assert.ok(narrow.amountTop >= narrow.labelBottom - 1,
    'Evidence must stack rather than overlap at 320 CSS px: ' + JSON.stringify(narrow));
  await page.screenshot({ path: 'test-artifacts/synthetic-warning-narrow.png', animations: 'disabled', scale: 'css' });

  await page.locator('.tab[data-view="mapping"]').click();
  const mappingRow = page.locator('#mapping-table tbody tr[data-id]').first();
  await mappingRow.press('Enter');
  assert.ok((await mappingRow.getAttribute('class') || '').includes('selected'));
  assert.equal(await mappingRow.evaluate(el => document.activeElement === el), true,
    'Mapping row keyboard action must retain row focus');
  const mapOutline = await mappingRow.evaluate(el => parseFloat(getComputedStyle(el).outlineWidth));
  assert.ok(mapOutline >= 2, 'Mapping row must show a visible focus outline');
  const mappingOverflow = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth, width: window.innerWidth,
  }));
  assert.ok(mappingOverflow.scroll <= mappingOverflow.width + 2,
    'Mapping table must scroll within its own area without page-wide overflow');

  assert.deepEqual(externalRequests, [], 'The local UI must not call external origins');
  console.log('SYNTHETIC_BROWSER_PASS: warning focus, ARIA, 320 CSS-pixel reflow, mapping focus, no external calls');
  console.log('No actual Chrome 200% zoom or client data was tested.');
} finally {
  if (browser) await browser.close();
  worker.kill('SIGTERM');
}
})().catch(err => { console.error(err); process.exitCode = 1; });
