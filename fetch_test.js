fetch('http://localhost:3000/snapshot')
  .then(r => r.json())
  .then(j => {
    const html = j.html;
    const m = html.match(/<button[^>]*aria-label="(?:Good|Bad) response"[^>]*>/g) || [];
    console.log(m.join('\n'));
  });
