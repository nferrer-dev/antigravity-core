const fs = require('fs');
const j = JSON.parse(fs.readFileSync('current_snap.html', 'utf8'));
const match = j.html.match(/data-tooltip-id="([^"]+)"/g);
if (match) {
    const sends = match.filter(s => s.includes('send'));
    console.log("Send tooltips found:", sends);
} else {
    console.log("No tooltips found.");
}
