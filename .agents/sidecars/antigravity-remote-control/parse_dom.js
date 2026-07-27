const fs = require('fs');
const html = fs.readFileSync('dom_dump.html', 'utf8');

// Find all tooltips
const tooltips = html.match(/data-tooltip-id="[^"]*"/g) || [];
const uniqueTooltips = [...new Set(tooltips)];
console.log('Tooltips:');
uniqueTooltips.forEach(t => console.log(t));

// Find project sections and buttons
const projectMatches = html.match(/<h3[^>]*>.*?project.*?<\/h3>.*?<button.*?<\/button>/gi) || [];
if (projectMatches.length > 0) {
    console.log('\nFound buttons near projects:');
    projectMatches.forEach(m => console.log(m.substring(0, 200)));
} else {
    console.log('\nNo buttons found immediately after project H3s.');
}

const allButtons = html.match(/<button[^>]*>.*?<\/button>/gi) || [];
const workspaceButtons = allButtons.filter(b => b.toLowerCase().includes('workspace') || b.toLowerCase().includes('project') || b.toLowerCase().includes('new'));
console.log('\nPotential New/Workspace Buttons:');
workspaceButtons.forEach(b => console.log(b.replace(/<svg.*?>.*?<\/svg>/g, '<svg>...</svg>')));
