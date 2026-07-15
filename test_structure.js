const fs = require('fs');
const jsdom = require('jsdom');
const html = fs.readFileSync('test_dom.html', 'utf8');
const dom = new jsdom.JSDOM(html);
const btns = dom.window.document.querySelectorAll('button[aria-label="Good response"]');
btns.forEach(b => {
    let g = b.closest('.group');
    let p = g.querySelector('.prose');
    if (!p) {
        console.log("NO PROSE: ", g.innerHTML.substring(0, 150));
    }
});
