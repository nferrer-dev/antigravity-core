const html = require('fs').readFileSync('test_dom.html', 'utf8');
const jsdom = require('jsdom');
const dom = new jsdom.JSDOM(html);
const btns = dom.window.document.querySelectorAll('button[aria-label="Good response"]');
btns.forEach(b => {
    let curr = b;
    let found = [];
    while (curr && curr.tagName !== 'BODY') {
        let attrs = Array.from(curr.attributes).filter(a => a.name.startsWith('data-') && a.name !== 'data-ag-id' && a.name !== 'data-ag-rem');
        if (attrs.length) found.push(curr.tagName + ' ' + attrs.map(a => a.name + '=' + a.value).join(', '));
        curr = curr.parentElement;
    }
    console.log(found.join(' | '));
    console.log('---');
});
