const fs = require('fs');
const html = fs.readFileSync('C:/Users/nferr/.gemini/antigravity/brain/eee4402c-9228-44d1-ba6b-366d51379fa5/scratch/dom3.html', 'utf8');
const jsdom = require('jsdom');
const { JSDOM } = jsdom;
const dom = new JSDOM(html);
const editable = dom.window.document.querySelector('[contenteditable="true"]');
if (editable) {
    let parent = editable.parentElement;
    while (parent && parent.tagName !== 'BODY') {
        const buttons = parent.querySelectorAll('button');
        if (buttons.length > 0) {
            console.log('Found buttons in parent:');
            buttons.forEach(b => console.log('Button aria-label:', b.getAttribute('aria-label'), '| class:', b.className, '| HTML:', b.innerHTML.replace(/\s+/g, ' ')));
            break;
        }
        parent = parent.parentElement;
    }
}
