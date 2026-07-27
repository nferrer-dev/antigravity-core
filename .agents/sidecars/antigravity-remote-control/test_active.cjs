const CDP = require('chrome-remote-interface');
CDP({port: 39203}, async (client) => {
  const {Runtime} = client;
  const res = await Runtime.evaluate({
    expression: `
      Array.from(document.querySelectorAll('span[data-testid^="convo-pill-"]'))
        .map(el => {
          const a = el.closest('a');
          return {
            text: el.innerText,
            classList: a ? Array.from(a.classList) : []
          };
        })
        .slice(0, 5)
    `,
    returnByValue: true
  });
  console.log(JSON.stringify(res.result.value, null, 2));
  client.close();
}).on('error', err => {
  console.error(err);
});
