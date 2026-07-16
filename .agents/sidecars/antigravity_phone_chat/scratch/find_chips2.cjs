const fs = require('fs');
const html = fs.readFileSync('scratch/dump_html_after_backspace.html', 'utf8');
const cheerio = require('cheerio');
const $ = cheerio.load(html);
const chips = $('.hover\\:opacity-50.cursor-pointer');
console.log('Found chips:', chips.length);
