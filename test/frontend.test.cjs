const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../src/duckgl_extension.cpp'), 'utf8');
const html = [...source.matchAll(/R"(\w*)\(([\s\S]*?)\)\1"/g)].map(m => m[2]).join('');
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]).join('\n');
assert(scripts.length > 0);
new vm.Script(scripts); // Check the entire embedded frontend, including all raw-string fragments.
function functionText(name) {
    const start = scripts.indexOf('function ' + name + '(');
    assert(start >= 0, name);
    const rest = scripts.slice(start + 1);
    const next = /\n\s*(?:async )?function /.exec(rest);
    assert(next, 'next function after ' + name);
    return scripts.slice(start, start + 1 + next.index);
}
if (source.includes('DuckDBIServer')) {
    const context = vm.createContext({});
    vm.runInContext(functionText('escapeHTML') + '\n' + functionText('quoteIdentifier'), context);
    assert.equal(context.escapeHTML('<img src=x onerror=alert(1)>'), '&lt;img src=x onerror=alert(1)&gt;');
    assert.equal(context.escapeHTML('a"\'&'), 'a&quot;&#39;&amp;');
    assert.equal(context.quoteIdentifier('odd"name'), '"odd""name"');
    assert.equal(context.quoteIdentifier('日本語'), '"日本語"');
} else {
    class Element {
        constructor() { this.children = []; this.classList = {add() {}}; this.textContent = ''; }
        replaceChildren() { this.children = []; this.textContent = ''; }
        appendChild(child) { this.children.push(child); return child; }
        createTHead() { return this.appendChild(new Element()); }
        createTBody() { return this.appendChild(new Element()); }
        insertRow() { return this.appendChild(new Element()); }
        insertCell() { return this.appendChild(new Element()); }
    }
    const panel = new Element(), content = new Element();
    const document = {getElementById: id => id === 'result-panel' ? panel : content, createElement: () => new Element()};
    const context = vm.createContext({document});
    vm.runInContext(functionText('showResults'), context);
    context.showResults([{ '<script>': '<img onerror=alert(1)>' }]);
    const table = content.children[0];
    assert.equal(table.children[0].children[0].children[0].textContent, '<script>');
    assert.equal(table.children[1].children[0].children[0].textContent, '<img onerror=alert(1)>');
    context.showResults({error: '<img onerror=alert(1)>'});
    assert.equal(content.textContent, 'Error: <img onerror=alert(1)>');
    assert.equal(content.children.length, 0);
    context.showResults([]);
    assert.equal(content.textContent, 'No results');
}
console.log('Embedded JavaScript syntax and rendering regressions passed');
