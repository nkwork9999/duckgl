const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../src/include/simple_ui.hpp'), 'utf8');
const html = source.match(/R"DUCKUI\(([\s\S]*)\)DUCKUI"/)[1];
const script = html.match(/<script>([\s\S]*)<\/script>/)[1];
new vm.Script(script);
function isolated(name) {
  const start = script.indexOf('function ' + name + '(');
  assert(start >= 0);
  const rest = script.slice(start + 1);
  const next = /\n(?:async )?function |\n\$\(/.exec(rest);
  assert(next);
  return script.slice(start, start + 1 + next.index);
}
const context = vm.createContext({});
vm.runInContext(isolated('quoteIdentifier') + isolated('qualifiedTable'), context);
assert.equal(context.quoteIdentifier('odd"name'), '"odd""name"');
assert.equal(context.qualifiedTable({table_schema:'other',table_name:'odd"name'}), '"other"."odd""name"');
assert.equal(context.qualifiedTable({table_name:'日本語'}), '"main"."日本語"');
if (script.includes('function csvCell')) {
  vm.runInContext(isolated('csvCell'), context);
  assert.equal(context.csvCell('a,"b"'), '"a,""b"""');
  assert.equal(context.csvCell(null), '""');
  assert.equal(context.csvCell(0), '"0"');
}
assert(html.includes('name="viewport"'));
assert(!html.includes('onclick='));
assert(html.includes('aria-live="polite"'));
console.log('Simple UI syntax, identifier, CSV and accessibility regressions passed');
