fetch('http://localhost:3000/snapshot').then(r => r.json()).then(j1 => {
  setTimeout(() => {
    fetch('http://localhost:3000/snapshot').then(r => r.json()).then(j2 => {
      const getIds = html => (html.match(/<button[^>]*aria-label="Good response"[^>]*data-ag-id="([^"]+)"/g) || []).map(m => m.match(/data-ag-id="([^"]+)"/)[1]);
      console.log('Snapshot 1:', getIds(j1.html));
      console.log('Snapshot 2:', getIds(j2.html));
    });
  }, 1500);
});
