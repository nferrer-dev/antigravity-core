const fs = require('fs');
const html = fs.readFileSync('scratch/dump_html_with_file.html', 'utf8');
const cheerio = require('cheerio');
const $ = cheerio.load(html);
const chip = $('.hover\\:opacity-50.cursor-pointer').first();
console.log(chip.parent().parent().html());
