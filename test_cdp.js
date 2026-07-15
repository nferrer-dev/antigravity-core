const CDP = require('chrome-remote-interface');
(async function() {
    let client;
    try {
        client = await CDP({ port: 9222 });
        const { Runtime } = client;
        
        const exp = (() => {
            return Array.from(document.querySelectorAll('button')).map(b => b.getAttribute('aria-label') + ' | ' + b.className).filter(l => l.includes('model') || l.includes('Model') || l.includes('conversation'));
        })();
        
        const result = await Runtime.evaluate({ expression: exp, returnByValue: true });
        console.log(result.result.value);
    } catch (err) {
        console.error(err);
    } finally {
        if (client) await client.close();
    }
})();
