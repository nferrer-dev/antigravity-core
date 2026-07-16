const CDP = require('chrome-remote-interface');
(async function() {
    try {
        const client = await CDP({ port: 9000 });
        const { Runtime } = client;
        
        const script = `
            document.querySelector('[data-testid="user-input-step"]') ? document.querySelector('[data-testid="user-input-step"]').outerHTML : 'no input'
        `;
        const result = await Runtime.evaluate({ expression: script });
        console.log(result.result.value);
        
        await client.close();
    } catch (e) {
        console.error(e);
    }
})();
