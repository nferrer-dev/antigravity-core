const fs = require('fs');
const html = fs.readFileSync('scratch/dump_html_after_remove_btn.html', 'utf8');
const cheerio = require('cheerio');
const $ = cheerio.load(html);
const imgs = $('img.object-cover');
console.log('Found imgs:', imgs.length);
