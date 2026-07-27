fetch('http://localhost:3000/snapshot').then(res => res.json()).then(data => { const html = data.html; const idx = html.indexOf('Test1'); console.log(html.substring(idx - 1000, idx)); })
