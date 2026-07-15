const fs = require('fs');
const jsdom = require('jsdom');

function getTexts(file) {
    const html = fs.readFileSync(file, 'utf8');
    const dom = new jsdom.JSDOM(html);
    const btns = dom.window.document.querySelectorAll('button[aria-label="Good response"]');
    const texts = [];
    btns.forEach(b => {
        let g = b.closest('.group');
        if (g) {
            let bodyNode = g.querySelector('.prose') || g.querySelector('.whitespace-pre-wrap.text-sm');
            if (bodyNode) {
                let clone = bodyNode.cloneNode(true);
                Array.from(clone.querySelectorAll('button')).forEach(e => e.remove());
                texts.push(clone.textContent.substring(0, 100).trim().replace(/\n/g, ' '));
            } else {
                texts.push("NOT FOUND: " + g.innerHTML.substring(0, 50));
            }
        }
    });
    return texts;
}

const texts1 = getTexts('test_dom.html');
const texts2 = getTexts('test_dom2.html');

const diff = texts1.filter(t => !texts2.includes(t));
const diff2 = texts2.filter(t => !texts1.includes(t));
console.log('--- MISSING IN DOM2 ---', diff);
console.log('--- NEW IN DOM2 ---', diff2);
