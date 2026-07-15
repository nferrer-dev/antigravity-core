const html = require('fs').readFileSync('test_dom.html', 'utf8');
const jsdom = require('jsdom');
const dom = new jsdom.JSDOM(html);
const btns = dom.window.document.querySelectorAll('button[aria-label="Good response"]');
btns.forEach(b => {
    let group = b.closest('.group');
    if (group) {
        let clone = group.cloneNode(true);
        // Remove known dynamic elements
        Array.from(clone.querySelectorAll('.ag-mobile-copy-btn-container, [aria-label="Copy"], button')).forEach(e => e.remove());
        console.log(clone.textContent.substring(0, 50).replace(/\n/g, ' '));
    }
});
