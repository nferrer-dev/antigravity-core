const fs = require('fs');
const htmlGen = fs.readFileSync('dom_generating.html', 'utf8');
const { JSDOM } = require('jsdom');
const dom = new JSDOM(htmlGen).window.document;
const avatars = dom.querySelectorAll('div');
let target = null;
avatars.forEach(a => {
    if (a.textContent && a.textContent.includes('Thought for 1s')) {
        target = a;
    }
});
if (target) {
    let p = target;
    for(let i=0; i<3 && p.parentElement; i++) p = p.parentElement;
    console.log(p.outerHTML.slice(0, 1000));
} else {
    console.log('not found');
}
