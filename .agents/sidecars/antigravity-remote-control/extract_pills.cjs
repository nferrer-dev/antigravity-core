const fs = require('fs');
const html = fs.readFileSync('dom_dump.html', 'utf8');

// The active chat would be the one whose text matches "Testing System Functionality" or similar
// Let's just find the first few `w-full group` that contain `convo-pill` and print their class lists
const regex = /<div[^>]*class="([^"]*)"[^>]*>(?:(?!<div[^>]*class="[^"]*w-full group).)*?convo-pill-.*?<\/div>/gis;
let m;
let count = 0;
while ((m = regex.exec(html)) !== null && count < 5) {
    console.log("MATCH", count);
    console.log("CLASSES:", m[1]);
    console.log("HTML:", m[0]);
    console.log("---");
    count++;
}
