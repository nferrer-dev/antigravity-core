const fs = require('fs');
const cheerio = require('cheerio');
const html = fs.readFileSync('scratch/dump_html_with_file.html', 'utf8');
const $ = cheerio.load(html);
$('[data-tooltip-id]').each((i, el) => {
    console.log('CHIP HTML:', $(el).parent().html());
});
