const fs = require('fs');
const html = fs.readFileSync('scratch/dump_html_with_file.html', 'utf8');
const cheerio = require('cheerio');
const $ = cheerio.load(html);

// The compose box is probably the last element with role="textbox"
const composeBox = $('[role="textbox"]').last();
const container = composeBox.closest('form, .relative'); // try to find a container
let buttons = [];

container.find('button').each((i, el) => {
    buttons.push({
        text: $(el).text().trim(),
        ariaLabel: $(el).attr('aria-label'),
        title: $(el).attr('title'),
        classes: $(el).attr('class')
    });
});
if (buttons.length === 0) {
    // maybe just print all buttons on the page?
    $('button').each((i, el) => {
        buttons.push({
            text: $(el).text().trim(),
            ariaLabel: $(el).attr('aria-label'),
            title: $(el).attr('title'),
            classes: $(el).attr('class')
        });
    });
}
console.log(buttons.slice(-10)); // just print the last 10 buttons on the page, they are usually in the compose box!
