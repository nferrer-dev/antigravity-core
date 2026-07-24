const cdp = require('chrome-remote-interface');
(async function() {
    try {
        const client = await cdp({ port: 7800 });
        const { Runtime } = client;
        await Runtime.enable();
        const res = await Runtime.evaluate({
            expression: '(() => { const cascade = document.querySelector(\'[data-testid="conversation-view"]\'); if (!cascade) return "no cascade"; return cascade.outerHTML.substring(0, 500); })()',
            returnByValue: true
        });
        console.log(res.result.value);
        await client.close();
    } catch (err) {
        console.error(err);
    }
})();
