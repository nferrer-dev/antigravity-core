const fs = require('fs');
const html = fs.readFileSync('scratch/dump_html2.html', 'utf8');

const regex = /<div role="article" aria-label="User message".*?<\/div><\/div><\/div><\/div><\/div><\/div><\/div><\/div>/g;
const matches = [...html.matchAll(regex)];

const target = matches.find(m => m[0].includes('Test from script'));

if (target) {
    const msgHtml = target[0];
    console.log('Includes img?:', msgHtml.includes('<img'));
    if (msgHtml.includes('<img')) {
        const imgRegex = /<img.*?src="(.*?)".*?>/g;
        const imgMatches = [...msgHtml.matchAll(imgRegex)];
        console.log('Images in last message:');
        imgMatches.forEach(m => console.log(m[1].substring(0, 50) + '...'));
    }
} else {
    console.log('No user messages found with that text');
}
