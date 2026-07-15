const html = require('fs').readFileSync('test_dom.html', 'utf8');
const jsdom = require('jsdom');
const dom = new jsdom.JSDOM(html);
const btns = dom.window.document.querySelectorAll('button[aria-label="Good response"]');
const b = btns[0];
let curr = b;
for(let i=0; i<8; i++) {
    console.log(i, curr.tagName, curr.className);
    curr = curr.parentElement;
}
