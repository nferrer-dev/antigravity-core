const http = require('http');
const fs = require('fs');
http.get('http://127.0.0.1:3000/snapshot', (resp) => {
  let data = '';
  resp.on('data', (c) => data += c);
  resp.on('end', () => {
    const s = JSON.parse(data);
    fs.writeFileSync('dom_dump.html', s.html);
    console.log("Dumped to dom_dump.html, length:", s.html.length);
  });
}).on("error", (err) => console.log("Error: " + err.message));
