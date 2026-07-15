const fs = require('fs');
const { JSDOM } = require('jsdom');
const html = fs.readFileSync('dom_generating.html', 'utf8');
const dom = new JSDOM(html).window.document;
const buttons = Array.from(dom.querySelectorAll('button')).map(b => ({
    label: b.getAttribute('aria-label') || b.getAttribute('title') || b.textContent.trim().replace(/\s+/g, ' ').substring(0, 50),
    tooltip: b.getAttribute('data-tooltip-id'),
    classes: b.className
}));
console.log(JSON.stringify(buttons, null, 2));
