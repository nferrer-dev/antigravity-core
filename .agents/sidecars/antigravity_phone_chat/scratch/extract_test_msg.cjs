const fs = require('fs');
const html = fs.readFileSync('scratch/dump_html.html', 'utf8');

const regex = /<div role="article" aria-label="User message".*?<\/div><\/div><\/div><\/div><\/div><\/div><\/div><\/div>/g;
const matches = [...html.matchAll(regex)];

const target = matches.find(m => m[0].includes('Test from script'));

if (target) {
    const msgHtml = target[0];
    console.log('Includes img?:', msgHtml.includes('<img'));
} else {
    console.log('No user messages found with that text');
}
