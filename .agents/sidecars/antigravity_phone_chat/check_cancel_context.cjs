const fs = require('fs');
const html = fs.readFileSync('dom_generating.html', 'utf8');
const lines = html.replace(/>/g, '>\n').split('\n');
const idx = lines.findIndex(l => l.includes('aria-label="Cancel (Ctrl+D)"'));
if (idx !== -1) {
    console.log(lines.slice(Math.max(0, idx - 10), idx + 10).join('\n'));
}
