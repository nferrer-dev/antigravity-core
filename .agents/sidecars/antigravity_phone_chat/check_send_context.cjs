const fs = require('fs');
const html = fs.readFileSync('dom_generating.html', 'utf8');
const lines = html.replace(/>/g, '>\n').split('\n');
const idx = lines.findIndex(l => l.includes('lucide-arrow-right'));
if (idx !== -1) {
    console.log(lines.slice(Math.max(0, idx - 15), idx + 15).join('\n'));
} else {
    console.log('Not found');
}
