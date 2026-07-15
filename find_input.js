const cheerio = require('cheerio');
const fs = require('fs');
const html = fs.readFileSync('snap_test.html', 'utf8');
const $ = cheerio.load(html);

const rootChildren = $('#root').children();
console.log('#root children ids:', rootChildren.map((i, el) => $(el).attr('id')).get());
console.log('#root children classes:', rootChildren.map((i, el) => $(el).attr('class')).get());

// Look for conversation-view
const convoView = $('[data-testid="conversation-view"]');
console.log('convoView length:', convoView.length);
if (convoView.length) {
    console.log('convoView parent id:', convoView.parent().attr('id'));
    console.log('convoView parent class:', convoView.parent().attr('class'));
    
    // Look higher up
    let cur = convoView;
    for(let i=0; i<5; i++) {
        cur = cur.parent();
        console.log(`Parent ${i+2} tag: <${cur.prop('tagName')}> id: ${cur.attr('id')} class: ${cur.attr('class')}`);
    }
}
