const html = require('fs').readFileSync('test_dom.html', 'utf8');
const jsdom = require('jsdom');
const dom = new jsdom.JSDOM(html);
const btns = dom.window.document.querySelectorAll('button[aria-label="Good response"]');
btns.forEach(b => {
    let msgContainer = b.closest('[data-testid="conversation-message"]') || b.closest('.message') || b.parentElement.parentElement.parentElement;
    console.log('MSG TEXT:', msgContainer ? msgContainer.textContent.substring(0, 50).replace(/\n/g, ' ') : 'NO CONTAINER');
});
