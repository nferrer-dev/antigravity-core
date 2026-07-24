const CDP = require('chrome-remote-interface');
CDP({port: 39203}, async (client) => {
  const {Runtime} = client;
  const EXP = `(async () => {
    try {
        const elements = Array.from(document.querySelectorAll('h2, div.text-sm.font-medium.truncate.m-0, span[data-testid^="convo-pill-"]'));
        for (const el of elements) {
            if (el.tagName === 'SPAN') {
                const parentA = el.closest('a');
                console.log(parentA ? parentA.className : 'no parent');
                return parentA ? parentA.className : 'no parent';
            }
        }
    } catch(e) {
        return e.message;
    }
  })();`;
  const res = await Runtime.evaluate({ expression: EXP, returnByValue: true, awaitPromise: true });
  console.log(JSON.stringify(res));
  client.close();
}).on('error', err => {
  console.error("CDP Error:", err);
});
