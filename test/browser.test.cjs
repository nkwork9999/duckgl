const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const { chromium } = require('playwright');
const source = fs.readFileSync(path.join(__dirname, '../src/include/simple_ui.hpp'), 'utf8');
const html = source.match(/R"DUCKUI\(([\s\S]*)\)DUCKUI"/)[1];
const isMap = html.includes('<title>DuckGL</title>');
let queryCount = 0, tablesFail = false, geoURL = '';
const rows = [{name:'<img src=x onerror="window.injected=true">', amount:0}, {name:'quoted,"value"',amount:null}, {name:'Tokyo',amount:12.5}];
const server = http.createServer(async (request, response) => {
    const url = new URL(request.url, 'http://localhost');
    if (url.pathname === '/') { response.setHeader('Content-Type','text/html'); response.end(html); return; }
    response.setHeader('Content-Type','application/json');
    if (url.pathname === '/api/tables') {
        response.statusCode = tablesFail ? 500 : 200;
        response.end(JSON.stringify(tablesFail ? {error:'Table connection failed'} : [{table_name:'orders',table_schema:'analytics'},{table_name:'odd"name<img>',table_schema:'main'}])); return;
    }
    if (url.pathname.startsWith('/api/geojson/')) {
        geoURL = request.url;
        response.end(JSON.stringify({type:'FeatureCollection',features:[{type:'Feature',geometry:{type:'Point',coordinates:[139.7,35.7]},properties:{}}]})); return;
    }
    if (url.pathname === '/api/query') {
        queryCount++; let body = ''; for await (const part of request) body += part;
        if (body === 'BAD_RESPONSE') { response.end('not JSON'); return; }
        if (body === 'FAIL') { response.statusCode=400; response.end(JSON.stringify({error:'Syntax error: <script>bad</script>'})); return; }
        if (body === 'EMPTY') { response.end('[]'); return; }
        if (body === 'SLOW') await new Promise(resolve => setTimeout(resolve, 200));
        response.end(JSON.stringify(rows)); return;
    }
    response.statusCode=404; response.end('{}');
});
const libraries = `window.Plotly={newPlot:async(id,traces)=>{window.chartTraces=traces;document.getElementById(id).textContent='Chart preview';}};
window.maplibregl={Map:class{addControl(){} on(event,callback){if(event==='load')setTimeout(callback,0)} fitBounds(bounds){window.mapBounds=bounds}},NavigationControl:class{}};
window.deck={MapboxOverlay:class{setProps(props){window.mapLayers=props.layers}},GeoJsonLayer:class{constructor(options){Object.assign(this,options)}}};`;
(async () => {
    await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
    let browser;
    try {
        browser = await chromium.launch({headless:true,channel:process.env.UI_BROWSER_CHANNEL || undefined});
        const page = await browser.newPage({viewport:{width:1280,height:900},acceptDownloads:true});
        const errors=[]; page.on('pageerror', error => errors.push(error.message));
        await page.route('https://**/*', route => route.fulfill({contentType:route.request().url().endsWith('.css')?'text/css':'application/javascript',body:route.request().url().endsWith('.css')?'':libraries}));
        await page.goto('http://127.0.0.1:' + server.address().port);
        await page.getByRole('button',{name:'orders analytics'}).waitFor();
        await page.getByRole('button',{name:'orders analytics'}).click();
        assert.equal(await page.locator('#sql-editor').inputValue(), 'SELECT * FROM "analytics"."orders" LIMIT 200');
        if (isMap) {
            await page.waitForFunction(() => window.mapBounds);
            assert(geoURL.includes('schema=analytics'));
            assert.deepEqual(await page.evaluate(() => window.mapBounds),[[139.7,35.7],[139.7,35.7]]);
            await page.getByRole('button',{name:'Preview rows'}).click();
        }
        await page.locator('#result-content td').first().waitFor();
        assert.equal(await page.locator('#result-content img').count(),0);
        assert.equal(await page.locator('#result-content td').nth(1).textContent(),'0');
        assert.equal(await page.locator('#result-content td').nth(3).textContent(),'NULL');
        assert.equal(await page.evaluate(() => window.injected),undefined);
        await page.locator('#table-search').fill('odd');
        assert.equal(await page.locator('.table-button').count(),1);
        assert.equal(await page.locator('#tables img').count(),0);
        await page.locator('#table-search').fill('');
        if (!isMap) {
            await page.getByText('Chart results',{exact:true}).click();
            await page.getByRole('button',{name:'Draw chart'}).click();
            await page.waitForFunction(() => window.chartTraces);
            assert.deepEqual(await page.evaluate(() => window.chartTraces[0].y),[0,null,12.5]);
            const downloadPromise=page.waitForEvent('download'); await page.getByRole('button',{name:'Download results as CSV'}).click();
            const download=await downloadPromise; const csv=fs.readFileSync(await download.path(),'utf8');
            assert(csv.includes('"quoted,""value"""')); assert(csv.includes(',"0"'));
            assert.equal(await page.getByRole('link',{name:'Dashboards & reports'}).getAttribute('href'),'/advanced');
        }
        const outputDir = process.env.UI_SCREENSHOT_DIR || os.tmpdir(); fs.mkdirSync(outputDir,{recursive:true});
        await page.screenshot({path:path.join(outputDir,(isMap?'duckgl':'duckdbi')+'-desktop.png'),fullPage:true});
        const beforeEmpty = queryCount;
        await page.locator('#sql-editor').fill(' '); await page.getByRole('button',{name:'Run query',exact:true}).click();
        assert.equal(queryCount,beforeEmpty); assert((await page.locator('#status').textContent()).includes('Enter a SQL query'));
        await page.locator('#sql-editor').fill('FAIL'); await page.locator('#sql-editor').press('Control+Enter');
        await page.waitForFunction(() => document.getElementById('status').textContent.includes('Syntax error'));
        assert.equal(await page.locator('#status script').count(),0);
        await page.locator('#sql-editor').fill('BAD_RESPONSE'); await page.getByRole('button',{name:'Run query',exact:true}).click();
        await page.waitForFunction(() => document.getElementById('status').textContent.includes('invalid response'));
        await page.locator('#sql-editor').fill('SLOW'); const beforeSlow=queryCount;
        await page.getByRole('button',{name:'Run query',exact:true}).click(); await page.locator('#sql-editor').press('Control+Enter');
        await page.waitForFunction(() => document.getElementById('run').disabled === false);
        assert.equal(queryCount,beforeSlow+1);
        await page.locator('#sql-editor').fill('EMPTY'); await page.getByRole('button',{name:'Run query',exact:true}).click();
        await page.getByText('No rows returned.',{exact:true}).waitFor();
        tablesFail=true; await page.getByRole('button',{name:'Refresh tables'}).click();
        await page.getByText('Could not load tables. Use Refresh to retry.',{exact:true}).waitFor();
        tablesFail=false; await page.getByRole('button',{name:'Refresh tables'}).click(); await page.getByRole('button',{name:'orders analytics'}).waitFor();
        assert.equal(await page.locator('#status').textContent(),'Tables updated.');
        await page.setViewportSize({width:375,height:812});
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        await page.screenshot({path:path.join(outputDir,(isMap?'duckgl':'duckdbi')+'-mobile.png'),fullPage:true});
        assert.deepEqual(errors,[]);
        console.log('Browser regressions passed: rendering, identifiers, filtering, shortcuts, errors, retry, duplicate requests, charts/CSV, mobile layout.');
    } finally { if(browser) await browser.close(); await new Promise(resolve=>server.close(resolve)); }
})().catch(error=>{console.error(error);process.exitCode=1});
