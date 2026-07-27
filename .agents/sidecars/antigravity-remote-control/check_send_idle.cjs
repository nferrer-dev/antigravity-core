const fs = require('fs');
const htmlIdle = fs.readFileSync('C:/Users/nferr/.gemini/antigravity/brain/eee4402c-9228-44d1-ba6b-366d51379fa5/scratch/dom3.html', 'utf8');
const { JSDOM } = require('jsdom');
const domIdle = new JSDOM(htmlIdle).window.document;
const sendBtns = domIdle.querySelectorAll('button[aria-label="Send"], svg.lucide-arrow-up, svg.lucide-arrow-right, svg.lucide-send');
console.log('Send buttons found:', sendBtns.length);
sendBtns.forEach(b => console.log(b.outerHTML.slice(0, 200)));
