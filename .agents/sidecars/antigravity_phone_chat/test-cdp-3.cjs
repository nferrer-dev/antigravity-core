const cdp = require('chrome-remote-interface');
(async function() {
    let client;
    try {
        client = await cdp({ port: 9000, target: '4F80951B295F539668591F8AF0FB99DB' });
        const { Runtime } = client;
        
        const res = await Runtime.evaluate({
            expression: `(() => {
                let btns = Array.from(document.querySelectorAll('button[aria-label^="Select model"]'));
                return btns.map(b => b.outerHTML);
            })()`,
            returnByValue: true,
            awaitPromise: true
        });
        console.log(res);
    } catch (err) {
        console.error(err);
    } finally {
        if (client) {
            await client.close();
        }
    }
})();
