const fs = require('fs');
const jsdom = require('jsdom');

function getTexts(file) {
    const html = fs.readFileSync(file, 'utf8');
    const dom = new jsdom.JSDOM(html);
    const btns = dom.window.document.querySelectorAll('button[aria-label="Good response"]');
    const texts = [];
    btns.forEach(b => {
        let group = b.closest('.group');
        if (group) {
            let clone = group.cloneNode(true);
            Array.from(clone.querySelectorAll('button')).forEach(e => e.remove());
            texts.push(clone.textContent.substring(0, 100).trim().replace(/\n/g, ' '));
        }
    });
    return texts;
}

const texts1 = getTexts('test_dom.html');
const texts2 = getTexts('test_dom2.html');

console.log('--- texts1 ---');
texts1.forEach(t => console.log(t));
console.log('--- texts2 ---');
texts2.forEach(t => console.log(t));

const diff = texts1.filter(t => !texts2.includes(t));
const diff2 = texts2.filter(t => !texts1.includes(t));
console.log('--- MISSING IN DOM2 ---', diff);
console.log('--- NEW IN DOM2 ---', diff2);
