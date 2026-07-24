const fs = require('fs');
const html = fs.readFileSync('c:\\Projects\\antigravity-core\\scratch\\sidebar_dom.html', 'utf8');

const regex = /data-testid="convo-pill-[^"]+"/g;
const matches = html.match(regex) || [];
const unique = new Set(matches);
console.log("Unique pills:", unique.size);

// Try to find section headers
const sections = html.match(/<h2[^>]*>(.*?)<\/h2>/g) || [];
console.log("Sections:", sections);

// Find all elements that look like they could be other groups
const groups = html.match(/<div[^>]*class="[^"]*text-sm font-medium truncate m-0[^"]*"[^>]*>(.*?)<\/div>/g) || [];
console.log("Groups:", groups);
