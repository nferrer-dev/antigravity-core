const cdp = require('chrome-remote-interface');
(async function() {
    let client;
    try {
        client = await cdp({ port: 9000, target: '4F80951B295F539668591F8AF0FB99DB' });
        const { Runtime } = client;
        
        const res = await Runtime.evaluate({
            expression: `(() => {
                let btn = document.querySelector('button[aria-label^="Select model"]');
                return {
                    found: !!btn,
                    html: btn ? btn.outerHTML : null,
                    text: btn ? btn.innerText : null
                };
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
