const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const { chromium } = require('playwright');

const source = fs.readFileSync(path.join(__dirname, '../src/include/simple_ui.hpp'), 'utf8');
const html = source.match(/R"DUCKUI\(([\s\S]*)\)DUCKUI"/)[1];
const exportJS = fs.readFileSync(path.join(__dirname, '../src/include/export_ui.hpp'), 'utf8').match(/R\"DUCKEXPORT\(([\s\S]*)\)DUCKEXPORT\"/)[1];
const sql = 'SELECT * FROM "analytics"."orders" LIMIT 200';
const rows = Array.from({ length: 305 }, (_, i) => ({
  '名前 <&"': i === 0 ? '<img src=x onerror="window.injected=true">日本語' : `Row ${i}`,
  amount: i === 1 ? null : i,
  enabled: i % 2 === 0,
}));
const features = { type: 'FeatureCollection', features: [
  { type: 'Feature', geometry: { type: 'Point', coordinates: [139.7, 35.7] }, properties: {} },
  { type: 'Feature', geometry: { type: 'LineString', coordinates: [[139.6, 35.6], [139.8, 35.8]] }, properties: {} },
  { type: 'Feature', geometry: { type: 'Polygon', coordinates: [
    [[139.6, 35.6], [139.8, 35.6], [139.8, 35.8], [139.6, 35.8], [139.6, 35.6]],
    [[139.65, 35.65], [139.75, 35.65], [139.75, 35.75], [139.65, 35.65]],
  ] }, properties: {} },
] };
const server = http.createServer((request, response) => {
  if (request.url === '/export.js') { response.setHeader('Content-Type','application/javascript'); response.end(exportJS); return; }
  if (request.url === '/') { response.setHeader('Content-Type', 'text/html'); response.end(html); return; }
  response.setHeader('Content-Type', 'application/json');
  if (request.url === '/api/tables') response.end(JSON.stringify([{ table_name: 'orders', table_schema: 'analytics' }]));
  else if (request.url.startsWith('/api/geojson/')) response.end(JSON.stringify(features));
  else if (request.url === '/api/query') response.end(JSON.stringify(rows));
  else { response.statusCode = 404; response.end('{}'); }
});

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch({ headless: true, channel: process.env.UI_BROWSER_CHANNEL || undefined });
    const page = await browser.newPage({ acceptDownloads: true });
    await page.route('https://**/*', route => route.fulfill({ contentType: 'application/javascript', body: `
      window.maplibregl={Map:class{addControl(){} on(event,callback){if(event==='load')setTimeout(callback,0)} fitBounds(){}},NavigationControl:class{}};
      window.deck={MapboxOverlay:class{setProps(){}},GeoJsonLayer:class{constructor(options){Object.assign(this,options)}}};
    ` }));
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.getByRole('button', { name: 'Export HTML', exact: true }).waitFor({ timeout: 2000 });
    assert(await page.getByRole('button', { name: 'Export HTML', exact: true }).isDisabled());
    await page.getByRole('button', { name: 'orders analytics' }).click();
    await page.waitForFunction(() => document.getElementById('map-caption').textContent.includes('3 features'));
    await page.getByRole('button', { name: 'Preview rows', exact: true }).click();
    await page.waitForFunction(() => document.getElementById('result-meta').textContent.includes('305 rows'));
    // Editing the editor must not silently relabel the saved successful result.
    await page.locator('#sql-editor').fill('SELECT 999 AS unsent; -- </pre><script>window.injected=true</script>');
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Export HTML', exact: true }).click();
    const download = await downloadPromise;
    assert(download.suggestedFilename().endsWith('.html'));
    const report = fs.readFileSync(await download.path(), 'utf8');
    const offline = await browser.newPage();
    let externalRequests = 0;
    await offline.route('**/*', route => { externalRequests++; return route.abort(); });
    await offline.setContent(report);
    assert.equal(await offline.locator('title').textContent(), 'DuckGL report');
    assert.equal(await offline.locator('script').count(), 0);
    assert.equal(await offline.locator('img').count(), 0);
    assert.equal(await offline.evaluate(() => window.injected), undefined);
    assert.equal(await offline.locator('pre').textContent(), sql);
    assert.equal(await offline.locator('tbody tr').count(), 305);
    assert.equal(await offline.locator('tbody tr').last().locator('td').first().textContent(), 'Row 304');
    assert((await offline.locator('tbody tr').first().textContent()).includes('日本語'));
    assert((await offline.locator('tbody tr').first().textContent()).includes('<img src=x'));
    assert.equal(await offline.locator('svg circle').count(), 1);
    assert.equal(await offline.locator('svg path[fill-rule="evenodd"]').count(), 1);
    assert((await offline.locator('body').textContent()).includes('without base-map tiles'));
    assert.equal(externalRequests, 0);

    // The PDF path uses this same standalone report and the browser print engine.
    const popupPromise = page.waitForEvent('popup');
    await page.getByRole('button', { name: 'Export PDF', exact: true }).click();
    const printable = await popupPromise;
    await printable.waitForLoadState('domcontentloaded');
    assert.equal(await printable.locator('tbody tr').count(), 305);
    const output = process.env.DUCKGL_EXPORT_DIR || os.tmpdir();
    fs.mkdirSync(output, { recursive: true });
    fs.writeFileSync(path.join(output, 'duckgl-report.html'), report);
    const pdf = await printable.pdf({ path: path.join(output, 'duckgl-report.pdf'), preferCSSPageSize: true, printBackground: true });
    assert.equal(pdf.subarray(0, 5).toString(), '%PDF-');
    assert(pdf.length > 10000);
    await offline.screenshot({ path: path.join(output, 'duckgl-report.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    assert(await page.getByRole('button', { name: 'Export PDF', exact: true }).isVisible());
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    console.log('HTML offline snapshot, escaping, 305 rows, vector map, PDF rendering and mobile export regressions passed');
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
