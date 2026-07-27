const cdp = require('chrome-remote-interface');
(async function() {
    try {
        const client = await cdp({ port: 7800 });
        const { Runtime } = client;
        await Runtime.enable();
        const res = await Runtime.evaluate({
            expression: '(() => { const cascade = document.querySelector(\'[data-testid="conversation-view"]\'); return cascade ? cascade.querySelectorAll(\'[class*="message"], [data-message], [role="article"]\').length : -1; })()',
            returnByValue: true
        });
        console.log("MESSAGES COUNT:", res.result.value);
        await client.close();
    } catch (err) {
        console.error(err);
    }
})();
