const fs = require('fs');
const htmlIdle = fs.readFileSync('C:/Users/nferr/.gemini/antigravity/brain/eee4402c-9228-44d1-ba6b-366d51379fa5/scratch/dom3.html', 'utf8');
const { JSDOM } = require('jsdom');
const dom = new JSDOM(htmlIdle).window.document;
const btn = dom.querySelector('button[aria-label="Cancel (Ctrl+D)"]');
console.log(btn.outerHTML);
let p = btn;
for(let i=0; i<4; i++) {
    console.log('Class:', p.className, '| Style:', p.style.cssText);
    p = p.parentElement;
}
