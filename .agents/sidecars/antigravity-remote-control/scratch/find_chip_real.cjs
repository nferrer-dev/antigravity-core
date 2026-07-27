const fs = require('fs');
const html = fs.readFileSync('scratch/dump_html_real_image.html', 'utf8');
const cheerio = require('cheerio');
const $ = cheerio.load(html);

// Find chips by the class "object-cover" (since the image has class="h-16 w-16 object-cover")
const imgs = $('img.object-cover');
console.log('Found imgs:', imgs.length);

if (imgs.length > 0) {
    imgs.each((i, el) => {
        // print out its ancestors to see if there's a button
        let parent = $(el).parent();
        console.log('--- Image', i, '---');
        let levels = 0;
        while (parent && parent.length > 0 && levels < 5) {
            console.log('Level', levels, 'tag:', parent.prop('tagName'), 'classes:', parent.attr('class'));
            parent = parent.parent();
            levels++;
        }
        
        // Also look for any button near this image (e.g. siblings or parent siblings)
        let container = $(el).parent().parent();
        let buttons = container.find('button');
        console.log('Buttons in container:', buttons.length);
        if (buttons.length > 0) {
            console.log(container.html());
        }
    });
}
