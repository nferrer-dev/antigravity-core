const fs = require('fs');
const htmlGen = fs.readFileSync('dom_generating.html', 'utf8');
const { JSDOM } = require('jsdom');
const dom = new JSDOM(htmlGen).window.document;
const loading = dom.querySelector('[data-testid="agent-loading"]');
if (loading) console.log('Loading text:', loading.textContent);
else console.log('No agent-loading element found');
