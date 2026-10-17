#pragma once
static constexpr char DUCKGL_SIMPLE_HTML[] = R"DUCKUI(<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DuckGL</title><script src="https://unpkg.com/maplibre-gl@3.6.0/dist/maplibre-gl.js"></script><link href="https://unpkg.com/maplibre-gl@3.6.0/dist/maplibre-gl.css" rel="stylesheet"><script src="https://unpkg.com/deck.gl@9.0.0/dist.min.js"></script><style>
:root{color-scheme:light;--ink:#1e293b;--muted:#64748b;--line:#e2e8f0;--accent:#176b52;--surface:#fff;font-family:system-ui,-apple-system,sans-serif}
*{box-sizing:border-box}body{margin:0;background:#f6f8fa;color:var(--ink);font-size:14px}button,input,select,textarea{font:inherit}button,a,input,select,textarea{outline-offset:3px}button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible,summary:focus-visible{outline:3px solid #69b99e}button{cursor:pointer;border:1px solid var(--line);border-radius:6px;background:white;padding:8px 12px;color:var(--ink)}button:hover{background:#edf5f1}button:disabled{cursor:wait;opacity:.55}.primary{background:var(--accent);color:white;border-color:var(--accent)}.primary:hover{background:#11533f}header{height:68px;padding:0 24px;display:flex;align-items:center;justify-content:space-between;background:white;border-bottom:1px solid var(--line);gap:12px}h1{font-size:20px;margin:0;letter-spacing:-.5px}h2{font-size:15px;margin:0}p{line-height:1.5}.muted,.hint{color:var(--muted)}.hint{font-size:12px;margin:8px 0 0}.brand{display:flex;align-items:baseline;gap:12px}.workspace{display:grid;grid-template-columns:240px minmax(0,1fr);min-height:calc(100vh - 68px)}aside{background:white;border-right:1px solid var(--line);padding:20px;min-width:0}.toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}.search{width:100%;padding:9px 10px;border:1px solid var(--line);border-radius:6px;margin:16px 0 10px}.table-list{display:grid;gap:4px;max-height:65vh;overflow:auto}.table-button{width:100%;text-align:left;border-color:transparent;overflow-wrap:anywhere}.table-button[aria-current=true]{background:#e8f4ee;color:var(--accent);border-color:#b8dfcd}.table-schema{display:block;color:var(--muted);font-size:11px;margin-top:3px}.main{padding:24px;min-width:0}.card{background:white;border:1px solid var(--line);border-radius:9px;padding:20px;margin-bottom:20px}textarea{width:100%;min-height:135px;resize:vertical;padding:14px;border:1px solid var(--line);border-radius:6px;background:#fafbfc;color:var(--ink);font-family:ui-monospace,SFMono-Regular,monospace;font-size:13px;line-height:1.6;margin:14px 0}#status{font-size:13px;color:var(--muted);overflow-wrap:anywhere}#status[data-error=true]{color:#a62626}.result-scroll{overflow:auto;max-height:48vh;margin-top:16px}.results{border-collapse:collapse;min-width:100%;font-size:13px}.results th,.results td{text-align:left;padding:10px 12px;border-bottom:1px solid var(--line);white-space:pre-wrap;max-width:340px;overflow-wrap:anywhere;vertical-align:top}.results th{background:#f7faf8;position:sticky;top:0;font-weight:600}.null{color:#94a3b8;font-style:italic}.empty{padding:20px 0;color:var(--muted)}details>summary{cursor:pointer;font-weight:600;min-height:24px}select{border:1px solid var(--line);border-radius:5px;padding:7px;background:white}label{font-weight:500}.chart-controls{display:flex;gap:16px;align-items:end;flex-wrap:wrap;margin-top:18px}.chart-controls label{display:grid;gap:6px}a{color:var(--accent)}[hidden]{display:none!important}@media(max-width:720px){header{height:auto;min-height:68px;padding:16px}.brand .muted{display:none}.workspace{grid-template-columns:1fr}aside{border-right:0;border-bottom:1px solid var(--line);padding:16px}.table-list{max-height:150px}.main{padding:16px}.card{padding:16px}.results th,.results td{padding:8px}.header-link{font-size:12px}}
 .workspace{grid-template-columns:300px minmax(0,1fr)}.map-main{position:relative;min-height:calc(100vh - 68px);min-width:0}#map{position:absolute;inset:0;background:#edf2ef}.map-notice{position:absolute;top:16px;left:16px;right:72px;background:white;padding:12px 16px;border:1px solid var(--line);border-radius:8px;z-index:2}.map-notice p{margin:4px 0}aside textarea{min-height:150px}aside .table-list{max-height:26vh}.query-controls{margin-top:24px}#result-panel{position:absolute;bottom:16px;left:16px;right:16px;z-index:2;margin:0;padding:16px;box-shadow:0 4px 24px #0001}#result-panel .result-scroll{max-height:28vh}.table-actions{display:flex;gap:8px;margin:10px 0}.table-actions button{flex:1}@media(max-width:720px){.workspace{grid-template-columns:1fr}.map-main{height:65vh;min-height:430px}aside .table-list{max-height:140px}#result-panel{left:8px;right:8px;bottom:8px}.map-notice{left:8px;right:60px}}</style></head><body><header><div class="brand"><h1>DuckGL</h1><span class="muted">Explore your data on a map</span></div></header><div class="workspace"><aside aria-label="Database tables"><div class="toolbar"><h2>Tables</h2><button id="refresh" type="button" aria-label="Refresh tables">Refresh</button></div><label for="table-search" class="hint">Find a table</label><input id="table-search" class="search" type="search" placeholder="Filter tables" autocomplete="off"><div id="tables" class="table-list">Loading tables…</div><div class="table-actions"><button id="show-map" type="button" disabled>Show on map</button><button id="preview-table" type="button" disabled>Preview rows</button></div><div class="query-controls"><div class="toolbar"><h2>SQL query</h2><button class="primary" id="run" type="button">Run query</button></div><label for="sql-editor" class="hint">Write a query or select a table</label><textarea id="sql-editor" spellcheck="false">SELECT 1 AS id;</textarea><p class="hint">Ctrl / ⌘ + Enter to run</p><p id="status" role="status" aria-live="polite">Ready</p></div></aside><main class="map-main" aria-label="Map and results"><div id="map" aria-label="Geospatial map"></div><div class="map-notice"><h2>Map</h2><p id="map-caption" class="muted">Select a spatial table to display its geometry.</p></div><section id="result-panel" class="card" hidden aria-label="Query results"><div class="toolbar"><h2>Results <span id="result-meta" class="muted"></span></h2><button id="close-results" type="button" aria-label="Close results">Close</button></div><div id="result-content" class="result-scroll" aria-busy="false"></div></section></main></div><script>
const $ = id => document.getElementById(id);
let tables = [], selectedTable = null, lastRows = [], queryGeneration = 0;
function quoteIdentifier(value) { return '"' + String(value).replace(/"/g, '""') + '"'; }
function qualifiedTable(table) { return quoteIdentifier(table.table_schema || 'main') + '.' + quoteIdentifier(table.table_name); }
function setStatus(message, error = false) { $('status').textContent = message; $('status').dataset.error = String(error); }
async function api(url, options) {
    const response = await fetch(url, options);
    let value;
    try { value = await response.json(); } catch (_) { throw new Error('The server returned an invalid response.'); }
    if (!response.ok || value?.error) throw new Error(value?.error || 'Request failed (' + response.status + ').');
    return value;
}
function renderTable(target, rows, limit = 200) {
    target.replaceChildren();
    if (!Array.isArray(rows) || !rows.length) { const empty = document.createElement('p'); empty.className = 'empty'; empty.textContent = 'No rows returned.'; target.appendChild(empty); return; }
    const columns = Object.keys(rows[0]);
    const table = document.createElement('table'); table.className = 'results';
    const head = table.createTHead().insertRow();
    for (const column of columns) { const cell = document.createElement('th'); cell.scope = 'col'; cell.textContent = column; head.appendChild(cell); }
    const body = table.createTBody();
    for (const row of rows.slice(0, limit)) {
        const tr = body.insertRow();
        for (const column of columns) { const cell = tr.insertCell(); const value = row[column]; cell.textContent = value === null ? 'NULL' : typeof value === 'object' ? JSON.stringify(value) : String(value); if (value === null) cell.className = 'null'; }
    }
    target.appendChild(table);
    if (rows.length > limit) { const note = document.createElement('p'); note.className = 'hint'; note.textContent = 'Showing ' + limit + ' of ' + rows.length.toLocaleString() + ' rows.'; target.appendChild(note); }
}
function renderTables() {
    const list = $('tables'); list.replaceChildren();
    const filter = $('table-search').value.trim().toLocaleLowerCase();
    const matches = tables.filter(table => (table.table_schema + '.' + table.table_name).toLocaleLowerCase().includes(filter));
    if (!matches.length) { list.textContent = tables.length ? 'No matching tables.' : 'No tables found.'; return; }
    for (const table of matches) {
        const button = document.createElement('button'); button.type = 'button'; button.className = 'table-button';
        button.setAttribute('aria-current', String(selectedTable === table));
        const name = document.createElement('span'); name.textContent = table.table_name;
        const schema = document.createElement('span'); schema.className = 'table-schema'; schema.textContent = table.table_schema || 'main';
        button.append(name, schema); button.addEventListener('click', () => selectTable(table)); list.appendChild(button);
    }
}
async function refreshTables() {
    const button = $('refresh'); button.disabled = true;
    try { const result = await api('/api/tables'); if (!Array.isArray(result)) throw new Error('Invalid table list.'); tables = result; renderTables(); setStatus('Tables updated.'); }
    catch (error) { $('tables').textContent = 'Could not load tables. Use Refresh to retry.'; setStatus(error.message, true); }
    finally { button.disabled = false; }
}
async function executeQuery() {
    const sql = $('sql-editor').value;
    if (!sql.trim()) { setStatus('Enter a SQL query first.', true); $('sql-editor').focus(); return; }
    if ($('run').disabled) return;
    const generation = ++queryGeneration, start = performance.now();
    $('run').disabled = true; $('run').textContent = 'Running…'; $('result-content').setAttribute('aria-busy', 'true'); setStatus('Running query…');
    try {
        const rows = await api('/api/query', {method:'POST', headers:{'Content-Type':'text/plain'}, body:sql});
        if (generation !== queryGeneration) return;
        if (!Array.isArray(rows)) throw new Error('Invalid query results.');
        lastRows = rows; renderTable($('result-content'), rows); $('result-meta').textContent = rows.length.toLocaleString() + ' rows · ' + ((performance.now()-start)/1000).toFixed(2) + ' s';
        queryCompleted(); setStatus('Query complete.');
    } catch (error) { if (generation === queryGeneration) { setStatus(error.message, true); } }
    finally { if (generation === queryGeneration) { $('run').disabled = false; $('run').textContent = 'Run query'; $('result-content').setAttribute('aria-busy', 'false'); } }
}
$('run').addEventListener('click', executeQuery);
$('refresh').addEventListener('click', refreshTables);
$('table-search').addEventListener('input', renderTables);
$('sql-editor').addEventListener('keydown', event => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); executeQuery(); } });

let map = null, overlay = null, pendingFeatures = null, geoGeneration = 0;
function selectTable(table) { selectedTable = table; renderTables(); $('sql-editor').value = 'SELECT * FROM ' + qualifiedTable(table) + ' LIMIT 200'; $('show-map').disabled = false; $('preview-table').disabled = false; loadMapTable(); }
function queryCompleted() { $('result-panel').hidden = false; }
function geometryCoordinates(geometry, points) {
    if (!geometry) return;
    if (geometry.type === 'GeometryCollection') { for (const child of geometry.geometries || []) geometryCoordinates(child, points); return; }
    function visit(coordinates) { if (!Array.isArray(coordinates)) return; if (typeof coordinates[0] === 'number' && typeof coordinates[1] === 'number') { if (Number.isFinite(coordinates[0]) && Number.isFinite(coordinates[1]) && Math.abs(coordinates[0]) <= 180 && Math.abs(coordinates[1]) <= 90) points.push(coordinates.slice(0,2)); } else for (const item of coordinates) visit(item); }
    visit(geometry.coordinates);
}
function renderFeatures(collection) {
    pendingFeatures = collection; if (!overlay) return;
    overlay.setProps({layers:[new deck.GeoJsonLayer({id:'selected-table',data:collection,filled:true,stroked:true,getFillColor:[23,107,82,160],getLineColor:[23,107,82,230],lineWidthMinPixels:2,pointRadiusMinPixels:6,pickable:true})]});
    const points = []; for (const feature of collection.features) geometryCoordinates(feature.geometry, points);
    if (points.length) { let west=180,south=90,east=-180,north=-90; for (const [x,y] of points) { west=Math.min(west,x);east=Math.max(east,x);south=Math.min(south,y);north=Math.max(north,y); } map.fitBounds([[west,south],[east,north]], {padding:60,maxZoom:13,duration:500}); }
}
async function loadMapTable() {
    if (!selectedTable) return; const table = selectedTable, generation = ++geoGeneration; $('show-map').disabled = true; setStatus('Loading ' + table.table_name + '…');
    try { const collection = await api('/api/geojson/' + encodeURIComponent(table.table_name) + '?schema=' + encodeURIComponent(table.table_schema || 'main')); if (generation !== geoGeneration) return; if (!Array.isArray(collection.features)) throw new Error('Invalid GeoJSON response.'); renderFeatures(collection); $('map-caption').textContent = table.table_name + ' · ' + collection.features.length.toLocaleString() + ' features'; setStatus(collection.features.length ? 'Map updated.' : 'No geometry found in this table.'); }
    catch (error) { if (generation === geoGeneration) setStatus(error.message + ' Use Preview rows to inspect the table.', true); }
    finally { if (generation === geoGeneration) $('show-map').disabled = false; }
}
function initMap() {
    if (!window.maplibregl || !window.deck) { $('map-caption').textContent = 'Map libraries could not load. Check your connection and reload.'; return; }
    try { map = new maplibregl.Map({container:'map',style:'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',center:[139.7,35.7],zoom:4}); map.addControl(new maplibregl.NavigationControl(), 'top-right'); map.on('load', () => { overlay = new deck.MapboxOverlay({layers:[]}); map.addControl(overlay); if (pendingFeatures) renderFeatures(pendingFeatures); }); map.on('error', () => { $('map-caption').textContent = 'Map tiles could not load. Queries and table previews are still available.'; }); }
    catch (error) { $('map-caption').textContent = 'Could not initialize the map: ' + error.message; }
}
$('show-map').addEventListener('click', loadMapTable); $('preview-table').addEventListener('click', executeQuery); $('close-results').addEventListener('click', () => { $('result-panel').hidden = true; });
initMap(); refreshTables();
</script></body></html>)DUCKUI";
