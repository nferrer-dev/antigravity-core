const cdp = require('chrome-remote-interface');
(async function() {
    try {
        const client = await cdp({ port: 7800 });
        const { Runtime } = client;
        await Runtime.enable();
        const res = await Runtime.evaluate({
            expression: '(() => { const exactBtn = document.querySelector(\'[aria-label="New Conversation"]\'); if (exactBtn) { exactBtn.click(); return true; } return false; })()',
            returnByValue: true
        });
        console.log("CLICKED:", res.result.value);
        await client.close();
    } catch (err) {
        console.error(err);
    }
})();
