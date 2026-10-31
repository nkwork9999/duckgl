#pragma once

static constexpr char DUCKGL_EXPORT_JS[] = R"DUCKEXPORT(
function reportEscape(value) {
    return String(value).replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
}
function reportCell(value) {
    return reportEscape(value === null ? 'NULL' : typeof value === 'object' ? JSON.stringify(value) : String(value));
}
function reportMap(collection) {
    if (!collection || !Array.isArray(collection.features) || !collection.features.length) return '<p>No geometry loaded.</p>';
    const points = [];
    for (const feature of collection.features) geometryCoordinates(feature.geometry, points);
    if (!points.length) return '<p>No finite geographic coordinates to display.</p>';
    let west=180, east=-180, south=90, north=-90;
    for (const [x,y] of points) { west=Math.min(west,x); east=Math.max(east,x); south=Math.min(south,y); north=Math.max(north,y); }
    const width=1000, height=450, padding=28;
    const scale=Math.min((width-2*padding)/Math.max(east-west,0.000001), (height-2*padding)/Math.max(north-south,0.000001));
    const project = point => {
        if (!Array.isArray(point) || !Number.isFinite(point[0]) || !Number.isFinite(point[1]) || Math.abs(point[0])>180 || Math.abs(point[1])>90) return null;
        return [(width/2+(point[0]-(west+east)/2)*scale).toFixed(3), (height/2-(point[1]-(south+north)/2)*scale).toFixed(3)];
    };
    const line = coordinates => {
        if (!Array.isArray(coordinates)) return '';
        let output='', pen=false;
        for (const coordinate of coordinates) {
            const point=project(coordinate);
            if (!point) { pen=false; continue; }
            output+=(pen?'L':'M')+point.join(' '); pen=true;
        }
        return output;
    };
    const fills=[], strokes=[], dots=[];
    function draw(geometry, depth=0) {
        if (!geometry || depth>32) return '';
        const coordinates=geometry.coordinates;
        switch (geometry.type) {
        case 'Point': {
            const point=project(coordinates);
            if (point) dots.push('<circle cx="'+point[0]+'" cy="'+point[1]+'" r="6" fill="#176b52" stroke="#fff" stroke-width="2"/>'); return '';
        }
        case 'MultiPoint': return Array.isArray(coordinates)?coordinates.map(point=>draw({type:'Point',coordinates:point},depth+1)).join(''):'';
        case 'LineString': strokes.push('<path d="'+line(coordinates)+'" fill="none" stroke="#176b52" stroke-width="2"/>'); return '';
        case 'MultiLineString': return Array.isArray(coordinates)?coordinates.map(points=>draw({type:'LineString',coordinates:points},depth+1)).join(''):'';
        case 'Polygon': fills.push('<path d="'+(Array.isArray(coordinates)?coordinates.map(ring=>line(ring)+'Z').join(''):'')+'" fill="#b8dfcd" fill-rule="evenodd" stroke="#176b52" stroke-width="2"/>'); return '';
        case 'MultiPolygon': return Array.isArray(coordinates)?coordinates.map(rings=>draw({type:'Polygon',coordinates:rings},depth+1)).join(''):'';
        case 'GeometryCollection': return Array.isArray(geometry.geometries)?geometry.geometries.map(child=>draw(child,depth+1)).join(''):'';
        default: return '';
        }
    }
    for (const feature of collection.features) draw(feature.geometry);
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 '+width+' '+height+'" role="img" aria-label="Geometry overview"><rect width="1000" height="450" fill="#f1f6f3"/>'+fills.join('')+strokes.join('')+dots.join('')+'</svg><p class="note">Geometry overview in longitude/latitude, without base-map tiles. N is up. '+collection.features.length.toLocaleString()+' features.</p>';
}
function buildDuckGLReport() {
    const columns=lastRows.length?Object.keys(lastRows[0]):[];
    const table=columns.length?'<div class="table-wrap"><table><thead><tr>'+columns.map(column=>'<th scope="col">'+reportEscape(column)+'</th>').join('')+'</tr></thead><tbody>'+lastRows.map(row=>'<tr>'+columns.map(column=>'<td>'+reportCell(row[column])+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>':'<p>No rows returned.</p>';
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; style-src &#39;unsafe-inline&#39;; base-uri &#39;none&#39;; form-action &#39;none&#39;"><title>DuckGL report</title><style>'+
    '*{box-sizing:border-box}body{margin:0;color:#1e293b;background:#fff;font:15px/1.5 system-ui,-apple-system,sans-serif}.report{max-width:1120px;margin:auto;padding:36px}header{border-bottom:2px solid #176b52;padding-bottom:18px;margin-bottom:24px}h1{font-size:28px;margin:0 0 8px}h2{font-size:19px;margin:26px 0 12px}p{margin:8px 0}.note{font-size:12px;color:#475569}svg{display:block;width:100%;max-height:450px;border:1px solid #dbe6df;border-radius:8px}pre{white-space:pre-wrap;overflow-wrap:anywhere;padding:16px;background:#f5f7f6;border:1px solid #e2e8f0;border-radius:6px;font:13px/1.6 ui-monospace,monospace}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;table-layout:fixed}th,td{padding:9px 10px;border:1px solid #dbe2e8;text-align:left;vertical-align:top;white-space:pre-wrap;overflow-wrap:anywhere}th{background:#edf5f0}thead{display:table-header-group}section{margin-bottom:24px}@media(max-width:600px){.report{padding:18px}th,td{padding:6px;font-size:12px}}@page{size:A4 landscape;margin:14mm}@media print{body{font-size:10pt}.report{max-width:none;padding:0}header{margin-bottom:12px;padding-bottom:10px}h1{font-size:21pt}h2{font-size:14pt;break-after:avoid}svg{max-height:95mm;break-inside:avoid}pre{font-size:9pt}.table-wrap{overflow:visible}th,td{padding:6px;white-space:pre-wrap}tr{break-inside:avoid}section{margin-bottom:14px}}'+
    '</style></head><body><article class="report"><header><h1>DuckGL report</h1><p class="note">Saved '+reportEscape(new Date().toISOString())+'</p><p>Snapshot of the last successful query and loaded geometry. Opening this report does not run SQL.</p></header>'+
    (pendingFeatures?'<section><h2>Map</h2><p>'+reportEscape(lastMapLabel)+'</p>'+(lastMapQuery?'<pre>'+reportEscape(lastMapQuery)+'</pre>':'')+reportMap(pendingFeatures)+'</section>':'')+
    '<section><h2>Last successful SQL query</h2><pre>'+reportEscape(lastQuery || 'No query run.')+'</pre></section><section><h2>Query results ('+lastRows.length.toLocaleString()+' rows)</h2>'+table+'</section></article></body></html>';
}
let reportBusy=false;
function updateDuckGLExportState() {
    const disabled=reportBusy || $('run').disabled || (!lastQuery && !pendingFeatures);
    $('export-html').disabled=disabled; $('export-pdf').disabled=disabled;
    const queryFormat=['csv','json'].includes($('download-format').value);
    $('download').disabled=reportBusy || $('run').disabled || (queryFormat?!lastQuery:!pendingFeatures);
}
function saveDuckGLFile(data, type, extension) {
    const blob=data instanceof Blob?data:new Blob([data],{type});
    const url=URL.createObjectURL(blob), link=document.createElement('a');
    link.href=url; link.download='duckgl-'+new Date().toISOString().slice(0,10)+'.'+extension;
    document.body.appendChild(link); link.click(); link.remove(); setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function resultCSV() {
    const columns=lastRows.length?Object.keys(lastRows[0]):[];
    const cell=value=>'"'+(value===null||value===undefined?'':typeof value==='object'?JSON.stringify(value):String(value)).replace(/"/g,'""')+'"';
    return '\uFEFF'+(columns.length?[columns,...lastRows.map(row=>columns.map(column=>row[column]))].map(row=>row.map(cell).join(',')).join('\r\n')+'\r\n':'');
}
function mapSVG() {
    const svg=reportMap(pendingFeatures).match(/<svg[\s\S]*?<\/svg>/);
    if (!svg) throw new Error('No geographic geometry is available for an image.');
    return svg[0].replace('<svg ', '<svg width="1000" height="450" ');
}
async function mapPNG() {
    const url=URL.createObjectURL(new Blob([mapSVG()],{type:'image/svg+xml'}));
    try {
        const image=new Image();
        await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=()=>reject(new Error('Could not render map overview.'));image.src=url;});
        const canvas=document.createElement('canvas'); canvas.width=1000; canvas.height=450;
        canvas.getContext('2d').drawImage(image,0,0,1000,450);
        return await new Promise((resolve,reject)=>canvas.toBlob(blob=>blob?resolve(blob):reject(new Error('Could not encode PNG.')),'image/png'));
    } finally { URL.revokeObjectURL(url); }
}
function interactiveMapHTML() {
    const center=map?.getCenter?.();
    const camera=center?{center:[center.lng,center.lat],zoom:map.getZoom(),bearing:map.getBearing(),pitch:map.getPitch()}:null;
    const state=JSON.stringify({collection:pendingFeatures,label:lastMapLabel,sql:lastMapQuery,camera}).replace(/</g,'\\u003c').replace(/>/g,'\\u003e').replace(/&/g,'\\u0026').replace(/\u2028/g,'\\u2028').replace(/\u2029/g,'\\u2029');
    const closeScript='</'+'script>';
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DuckGL interactive map</title>'+
    '<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@3.6.0/dist/maplibre-gl.css"><script src="https://unpkg.com/maplibre-gl@3.6.0/dist/maplibre-gl.js">'+closeScript+'<script src="https://unpkg.com/deck.gl@9.0.0/dist.min.js">'+closeScript+
    '<style>*{box-sizing:border-box}body{margin:0;font:14px system-ui;color:#1e293b}header{padding:16px;background:white}h1{font-size:20px;margin:0}p{margin:6px 0;overflow-wrap:anywhere}pre{white-space:pre-wrap}#map{height:75vh;min-height:420px}#details{padding:16px;overflow-wrap:anywhere}dt{font-weight:600}dd{margin:4px 0 12px}</style></head><body><header><h1>DuckGL map</h1><p>'+reportEscape(lastMapLabel)+'</p><p>Data is embedded. Map libraries and base-map tiles need internet access. Click a feature to inspect it.</p>'+(lastMapQuery?'<pre>'+reportEscape(lastMapQuery)+'</pre>':'')+'</header><div id="map" aria-label="Interactive map"></div><aside id="details" aria-label="Feature properties"></aside><script id="map-data" type="application/json">'+state+closeScript+
    '<script>'+geometryCoordinates.toString()+`
    const state=JSON.parse(document.getElementById('map-data').textContent);
    function inspect(feature){if(!feature)return;const target=document.getElementById('details');target.replaceChildren();const list=document.createElement('dl');for(const [key,value] of Object.entries(feature.properties||{})){const term=document.createElement('dt'),definition=document.createElement('dd');term.textContent=key;definition.textContent=value===null?'NULL':typeof value==='object'?JSON.stringify(value):String(value);list.append(term,definition);}target.appendChild(list);}
    try {
        const map=new maplibregl.Map(Object.assign({container:'map',style:'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',center:[0,0],zoom:1},state.camera||{}));
        map.addControl(new maplibregl.NavigationControl(),'top-right');
        map.on('load',()=>{const overlay=new deck.MapboxOverlay({layers:[]});map.addControl(overlay);overlay.setProps({layers:[new deck.GeoJsonLayer({id:'snapshot',data:state.collection,filled:true,stroked:true,getFillColor:[23,107,82,160],getLineColor:[23,107,82,230],lineWidthMinPixels:2,pointRadiusMinPixels:6,pickable:true,onClick:info=>inspect(info.object)})]});
        if(!state.camera){const points=[];for(const feature of state.collection.features)geometryCoordinates(feature.geometry,points);if(points.length){let w=180,s=90,e=-180,n=-90;for(const [x,y] of points){w=Math.min(w,x);s=Math.min(s,y);e=Math.max(e,x);n=Math.max(n,y);}map.fitBounds([[w,s],[e,n]],{padding:40,maxZoom:13});}}});
    }catch(error){document.getElementById('details').textContent='Could not load map libraries. Check your connection and reload. '+error.message;}
    `+closeScript+'</body></html>';
}
async function downloadDuckGL() {
    if ($('download').disabled || reportBusy) return;
    const format=$('download-format').value;
    reportBusy=true; updateDuckGLExportState(); setStatus('Preparing download…');
    try {
        if(format==='csv') saveDuckGLFile(resultCSV(),'text/csv;charset=utf-8','csv');
        else if(format==='json') saveDuckGLFile(JSON.stringify(lastRows,null,2),'application/json','json');
        else if(format==='geojson') saveDuckGLFile(JSON.stringify(pendingFeatures,null,2),'application/geo+json','geojson');
        else if(format==='svg') saveDuckGLFile(mapSVG(),'image/svg+xml','svg');
        else if(format==='png') saveDuckGLFile(await mapPNG(),'image/png','png');
        else if(format==='map-html') saveDuckGLFile(interactiveMapHTML(),'text/html;charset=utf-8','html');
        setStatus('Download ready.');
    } catch(error) { setStatus(error.message,true); }
    finally {reportBusy=false;updateDuckGLExportState();}
}
function exportDuckGLReport(kind) {
    if (reportBusy || (!lastQuery && !pendingFeatures)) return;
    reportBusy=true; updateDuckGLExportState(); setStatus('Preparing '+kind.toUpperCase()+' report…');
    try {
        const report=buildDuckGLReport();
        if (kind==='html') {
            const url=URL.createObjectURL(new Blob([report],{type:'text/html;charset=utf-8'}));
            const link=document.createElement('a'); link.href=url; link.download='duckgl-report-'+new Date().toISOString().slice(0,10)+'.html';
            document.body.appendChild(link); link.click(); link.remove(); setTimeout(()=>URL.revokeObjectURL(url),1000);
            setStatus('HTML report downloaded. It opens offline.');
        } else {
            const printable=window.open('', '_blank');
            if (!printable) throw new Error('Allow pop-ups to open the PDF report.');
            printable.opener=null;
            printable.addEventListener('load',()=>{ printable.focus(); printable.print(); },{once:true});
            printable.document.open(); printable.document.write(report); printable.document.close();
            setStatus('Choose Save as PDF in the print dialog.');
        }
    } catch (error) { setStatus('Could not export report: '+error.message,true); }
    finally { reportBusy=false; updateDuckGLExportState(); }
}
$('export-html').addEventListener('click',()=>exportDuckGLReport('html'));
$('export-pdf').addEventListener('click',()=>exportDuckGLReport('pdf'));
$('download').addEventListener('click',downloadDuckGL);
$('download-format').addEventListener('change',updateDuckGLExportState);
updateDuckGLExportState();
)DUCKEXPORT";
