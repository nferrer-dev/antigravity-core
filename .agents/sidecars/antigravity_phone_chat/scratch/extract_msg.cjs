const fs = require('fs');
const html = fs.readFileSync('scratch/dump_html.html', 'utf8');

const regex = /<div role="article" aria-label="User message".*?<\/div><\/div><\/div><\/div><\/div><\/div><\/div><\/div>/g;
const matches = [...html.matchAll(regex)];

if (matches.length > 0) {
    const lastMessage = matches[matches.length - 1][0];
    console.log('Last message includes img?:', lastMessage.includes('<img'));
    
    if (lastMessage.includes('<img')) {
        const imgRegex = /<img.*?src="(.*?)".*?>/g;
        const imgMatches = [...lastMessage.matchAll(imgRegex)];
        console.log('Images in last message:');
        imgMatches.forEach(m => console.log(m[1].substring(0, 50) + '...'));
    }
    
    // Also print text content
    console.log('Text content:', lastMessage.replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim());
} else {
    console.log('No user messages found');
}
