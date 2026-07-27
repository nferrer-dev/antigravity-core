const fs = require('fs');
const html = fs.readFileSync('scratch/dump_html_with_file.html', 'utf8');
const cheerio = require('cheerio');
const $ = cheerio.load(html);

// Find the container that holds the file chip (e.g. looking for relative inline-block cursor-pointer)
const chips = $('.hover\\:opacity-50.cursor-pointer');
console.log('Found chips:', chips.length);
if (chips.length > 0) {
    console.log(chips.first().parent().html());
}
