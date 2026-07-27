const fs = require('fs');
const html = fs.readFileSync('scratch/dump_html_with_file.html', 'utf8');
const cheerio = require('cheerio');
const $ = cheerio.load(html);

const buttons = [];
$('button').each((i, el) => {
    const ariaLabel = $(el).attr('aria-label');
    if (ariaLabel && (ariaLabel.toLowerCase().includes('remove') || ariaLabel.toLowerCase().includes('clear') || ariaLabel.toLowerCase().includes('delete'))) {
        buttons.push({ ariaLabel });
    }
});
console.log('Remove buttons:', buttons);

// Also look for any 'x' icons that might not have an aria-label
$('svg, i, span').each((i, el) => {
    if ($(el).attr('class') && $(el).attr('class').includes('lucide-x')) {
        let parent = $(el).closest('button');
        console.log('Found an X icon. Parent button aria-label:', parent.attr('aria-label'));
    }
});
