const html = require('fs').readFileSync('test_dom.html', 'utf8');
const jsdom = require('jsdom');
const dom = new jsdom.JSDOM(html);
const btns = dom.window.document.querySelectorAll('button[aria-label="Good response"]');
btns.forEach(b => {
    let group = b.closest('.group');
    let prose = group ? group.querySelector('.prose') : null;
    let txt = prose ? prose.textContent : (group ? group.textContent : '');
    console.log(txt.substring(0, 50).replace(/\n/g, ' '));
});
