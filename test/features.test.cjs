const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { test, describe, before, after } = require('node:test');
const { chromium } = require('playwright');
const html = fs.readFileSync(path.join(__dirname, '../src/include/simple_ui.hpp'), 'utf8').match(/R"DUCKUI\(([\s\S]*)\)DUCKUI"/)[1];
const exportJS = fs.readFileSync(path.join(__dirname, '../src/include/export_ui.hpp'), 'utf8').match(/R"DUCKEXPORT\(([\s\S]*)\)DUCKEXPORT"/)[1];
const rows = [{ name: '日本語,"quoted"\nline', amount: 0, enabled: false, id: '9007199254740993' }, { name: 'second', amount: null, enabled: true, id: '42' }];
const features = { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [139.7, 35.7] }, properties: { name: '</script><img src=x onerror="window.injected=true">日本語', amount: 0, enabled: false, missing: null } }] };
const columns = [{ column_name: 'shape', data_type: 'GEOMETRY', is_geometry: true }, { column_name: 'alt', data_type: 'GEOMETRY', is_geometry: true }, { column_name: 'name', data_type: 'VARCHAR', is_geometry: false }];
const libraries = `window.maplibregl={Map:class{addControl(){} on(event,callback){if(event==='load')setTimeout(callback,0)} fitBounds(b){window.mapBounds=b}},NavigationControl:class{}};
window.deck={MapboxOverlay:class{setProps(props){window.mapLayers=props.layers}},GeoJsonLayer:class{constructor(options){Object.assign(this,options)}}};`;
let browser, server, baseURL, lastGeoURL, lastMapSQL;
describe('DuckGL map and download features', () => {
  before(async () => {
    server = http.createServer(async (request, response) => {
      const url = new URL(request.url, 'http://localhost');
      if (url.pathname === '/') { response.setHeader('Content-Type', 'text/html'); response.end(html); return; }
      if (url.pathname === '/export.js') { response.setHeader('Content-Type', 'application/javascript'); response.end(exportJS); return; }
      response.setHeader('Content-Type', 'application/json');
      if (url.pathname === '/api/tables') response.end(JSON.stringify([{ table_name: 'places', table_schema: 'main', table_catalog: 'memory' }]));
      else if (url.pathname.startsWith('/api/columns/')) response.end(JSON.stringify(columns));
      else if (url.pathname.startsWith('/api/geojson/')) { lastGeoURL = url; response.end(JSON.stringify(features)); }
      else if (url.pathname === '/api/query-map') { lastMapSQL = ''; for await (const part of request) lastMapSQL += part; response.end(JSON.stringify(features)); }
      else if (url.pathname === '/api/query') response.end(JSON.stringify(rows));
      else { response.statusCode = 404; response.end(JSON.stringify({ error: 'Not found' })); }
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    baseURL = `http://127.0.0.1:${server.address().port}`;
    browser = await chromium.launch({ channel: process.env.UI_BROWSER_CHANNEL || undefined, args: ['--disable-gpu'] });
  });
  after(async () => {
    if (browser) await browser.close();
    if (server) await new Promise(resolve => { server.close(resolve); server.closeAllConnections(); });
  });
  async function pageFor(t, mode) {
    const context = await browser.newContext({ acceptDownloads: true });
    const page = await context.newPage();
    page.setDefaultTimeout(5000);
    t.after(() => context.close());
    await page.route('https://**/*', route => route.fulfill({ contentType: route.request().url().endsWith('.css') ? 'text/css' : 'application/javascript', body: route.request().url().endsWith('.css') ? '' : libraries }));
    await page.goto(baseURL);
    if (mode === 'query') { await page.getByRole('button', { name: 'Run query', exact: true }).click(); await page.locator('#result-content td').first().waitFor(); }
    if (mode === 'map') { await page.getByRole('button', { name: 'places memory.main', exact: true }).click(); await page.waitForFunction(() => window.mapLayers?.length); }
    return page;
  }
  async function download(page, format) {
    await page.getByLabel('Download format', { exact: true }).selectOption(format);
    const waiting = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Download', exact: true }).click();
    const file = await waiting;
    return { name: file.suggestedFilename(), data: fs.readFileSync(await file.path()) };
  }
  test('CSV downloads all query rows with quotes, newlines, NULL and exact IDs', async t => {
    const page = await pageFor(t, 'query');
    const file = await download(page, 'csv');
    assert(file.name.endsWith('.csv'));
    assert.equal(file.data.toString().replace(/^\uFEFF/, ''), '"name","amount","enabled","id"\r\n"日本語,""quoted""\nline","0","false","9007199254740993"\r\n"second","","true","42"\r\n');
  });
  test('JSON downloads query values without type or precision loss', async t => {
    const page = await pageFor(t, 'query');
    const file = await download(page, 'json');
    assert(file.name.endsWith('.json')); assert.deepEqual(JSON.parse(file.data), rows);
  });
  test('GeoJSON downloads the loaded geometry and complete properties', async t => {
    const page = await pageFor(t, 'map');
    const file = await download(page, 'geojson');
    assert(file.name.endsWith('.geojson')); assert.deepEqual(JSON.parse(file.data), features);
  });
  test('SVG downloads a standalone vector overview', async t => {
    const page = await pageFor(t, 'map');
    const file = await download(page, 'svg');
    assert(file.name.endsWith('.svg'));
    const parsed = await page.evaluate(source => { const xml = new DOMParser().parseFromString(source, 'image/svg+xml'); return { errors: xml.querySelectorAll('parsererror').length, circles: xml.querySelectorAll('circle').length, scripts: xml.querySelectorAll('script').length }; }, file.data.toString());
    assert.deepEqual(parsed, { errors: 0, circles: 1, scripts: 0 });
  });
  test('PNG downloads a real rasterized geometry overview', async t => {
    const page = await pageFor(t, 'map');
    const file = await download(page, 'png');
    assert(file.name.endsWith('.png'));
    assert.deepEqual([...file.data.subarray(0, 8)], [137,80,78,71,13,10,26,10]);
    assert.equal(file.data.readUInt32BE(16), 1000); assert.equal(file.data.readUInt32BE(20), 450);
    assert(file.data.length > 1000);
  });
  test('interactive HTML embeds map data safely and opens without the DuckGL server', async t => {
    const page = await pageFor(t, 'map');
    const file = await download(page, 'map-html');
    assert(file.name.endsWith('.html'));
    const saved = await browser.newPage(); t.after(() => saved.close());
    let apiCalls = 0;
    await saved.route('**/*', route => { if (route.request().url().includes('/api/')) apiCalls++; return route.fulfill({ contentType: route.request().url().endsWith('.css') ? 'text/css' : 'application/javascript', body: route.request().url().endsWith('.css') ? '' : libraries }); });
    await saved.setContent(file.data.toString());
    await saved.waitForFunction(() => window.mapLayers?.length);
    assert.deepEqual(await saved.evaluate(() => window.mapLayers[0].data), features);
    assert.equal(await saved.locator('img').count(), 0); assert.equal(await saved.evaluate(() => window.injected), undefined);
    assert.equal(apiCalls, 0);
  });
  test('column details and geometry selection choose the requested geometry', async t => {
    const page = await pageFor(t, 'map');
    await page.getByText('Columns', { exact: true }).click();
    assert((await page.locator('#columns').textContent()).includes('VARCHAR'));
    await page.getByLabel('Geometry column', { exact: true }).selectOption('alt');
    await page.getByRole('button', { name: 'Show on map', exact: true }).click();
    await page.waitForFunction(() => !document.getElementById('show-map').disabled);
    assert.equal(lastGeoURL.searchParams.get('geometry'), 'alt');
  });
  test('source CRS control sends an explicit projection for the map', async t => {
    const page = await pageFor(t, 'map');
    await page.getByLabel('Source CRS', { exact: true }).fill('EPSG:3857');
    await page.getByRole('button', { name: 'Show on map', exact: true }).click();
    await page.waitForFunction(() => !document.getElementById('show-map').disabled);
    assert.equal(lastGeoURL.searchParams.get('source_crs'), 'EPSG:3857');
  });
  test('Map query renders the submitted SQL and keeps its export provenance', async t => {
    const page = await pageFor(t);
    const sql = 'SELECT ST_Point(139.7,35.7) AS shape WHERE true';
    await page.locator('#sql-editor').fill(sql);
    await page.getByRole('button', { name: 'Map query', exact: true }).click();
    await page.waitForFunction(() => window.mapLayers?.length);
    assert.equal(lastMapSQL, sql);
    assert((await page.locator('#map-caption').textContent()).includes('SQL query'));
    const waiting = page.waitForEvent('download'); await page.getByRole('button', { name: 'Export HTML', exact: true }).click();
    assert(fs.readFileSync(await (await waiting).path(), 'utf8').includes('SELECT ST_Point(139.7,35.7)'));
  });
  test('clicking a feature shows safe property text including false, zero and NULL', async t => {
    const page = await pageFor(t, 'map');
    await page.evaluate(feature => window.mapLayers[0].onClick({ object: feature }), features.features[0]);
    const panel = page.locator('#feature-panel');
    await panel.waitFor({ state: 'visible' });
    const text = await panel.textContent();
    assert(text.includes('日本語') && text.includes('false') && text.includes('0') && text.includes('NULL'));
    assert.equal(await panel.locator('img').count(), 0); assert.equal(await page.evaluate(() => window.injected), undefined);
    await page.getByRole('button', { name: 'Close feature', exact: true }).click(); assert(await panel.isHidden());
  });
  test('mobile query results scroll horizontally without crushing values or widening the page', async t => {
    const page = await pageFor(t, 'query');
    await page.setViewportSize({ width: 390, height: 844 });
    assert(await page.locator('#result-content').evaluate(element => element.scrollWidth > element.clientWidth));
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  });
});
