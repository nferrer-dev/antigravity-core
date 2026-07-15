const fs = require('fs');
const json = JSON.parse(fs.readFileSync('./snap_test.json', 'utf8'));
const html = json.html;
const m = html.match(/<button[^>]*aria-label="(?:Good|Bad) response"[^>]*>/g) || [];
console.log(m.join('\n'));
