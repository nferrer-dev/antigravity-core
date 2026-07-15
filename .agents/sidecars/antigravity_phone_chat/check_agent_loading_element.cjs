const fs = require('fs');
const htmlGen = fs.readFileSync('dom_generating.html', 'utf8');
const { JSDOM } = require('jsdom');
const dom = new JSDOM(htmlGen).window.document;
const loading = dom.querySelector('[data-testid="agent-loading"]');
console.log(loading.outerHTML);
