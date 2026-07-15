const html = require('fs').readFileSync('test_dom.html', 'utf8');
const jsdom = require('jsdom');
const dom = new jsdom.JSDOM(html);
const btns = dom.window.document.querySelectorAll('button[aria-label="Good response"]');
btns.forEach(b => {
    let curr = b;
    for(let i=0; i<7; i++) curr = curr.parentElement;
    console.log('---');
    console.log(curr.textContent.substring(0, 100).replace(/\n/g, ' '));
});
