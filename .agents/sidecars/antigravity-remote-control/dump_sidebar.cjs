const CDP = require('chrome-remote-interface');
CDP({port: 39203}, async (client) => {
  const {Runtime} = client;
  const res = await Runtime.evaluate({
    expression: `
      Array.from(document.querySelectorAll('a')).map(a => {
        const span = a.querySelector('span[data-testid^="convo-pill-"]');
        if (span) {
          return {
            title: span.innerText,
            classList: Array.from(a.classList)
          };
        }
        return null;
      }).filter(Boolean)
    `,
    returnByValue: true
  });
  require('fs').writeFileSync('sidebar_dump.json', JSON.stringify(res.result.value, null, 2));
  client.close();
}).on('error', err => {
  console.error(err);
});
