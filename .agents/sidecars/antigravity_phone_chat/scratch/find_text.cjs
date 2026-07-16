const fs = require('fs');
const html = fs.readFileSync('scratch/dump_html_after_backspace.html', 'utf8');
const cheerio = require('cheerio');
const $ = cheerio.load(html);
console.log('Textareas:', $('textarea').length);
console.log('ContentEditables:', $('[contenteditable="true"]').length);
