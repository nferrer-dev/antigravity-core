const html = require('fs').readFileSync('test_dom.html', 'utf8');
const jsdom = require('jsdom');
const dom = new jsdom.JSDOM(html);
const btns = dom.window.document.querySelectorAll('button[aria-label="Good response"]');
btns.forEach(b => {
    let container = b.closest('.group');
    console.log(container ? container.textContent.substring(0, 100).replace(/\n/g, ' ') : 'NO CONTAINER');
});
