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
    (pendingFeatures?'<section><h2>Map</h2><p>'+reportEscape(lastMapLabel)+'</p>'+reportMap(pendingFeatures)+'</section>':'')+
    '<section><h2>Last successful SQL query</h2><pre>'+reportEscape(lastQuery || 'No query run.')+'</pre></section><section><h2>Query results ('+lastRows.length.toLocaleString()+' rows)</h2>'+table+'</section></article></body></html>';
}
let reportBusy=false;
function updateDuckGLExportState() {
    const disabled=reportBusy || $('run').disabled || (!lastQuery && !pendingFeatures);
    $('export-html').disabled=disabled; $('export-pdf').disabled=disabled;
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
updateDuckGLExportState();
)DUCKEXPORT";
