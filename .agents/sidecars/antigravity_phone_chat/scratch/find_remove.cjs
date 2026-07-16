const fs = require('fs');
const html = fs.readFileSync('scratch/dump_html_with_file.html', 'utf8');
const cheerio = require('cheerio');
const $ = cheerio.load(html);

const buttons = [];
$('button').each((i, el) => {
    buttons.push({
        text: $(el).text().trim(),
        ariaLabel: $(el).attr('aria-label'),
        title: $(el).attr('title'),
        classes: $(el).attr('class')
    });
});

console.log(buttons.filter(b => 
    (b.ariaLabel && b.ariaLabel.toLowerCase().includes('remove')) || 
    (b.title && b.title.toLowerCase().includes('remove')) ||
    (b.text && b.text.toLowerCase().includes('remove'))
));
