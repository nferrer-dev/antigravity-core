const CDP = require('chrome-remote-interface');
(async function() {
    try {
        const client = await CDP({ port: 9000 });
        const { Runtime } = client;
        
        let res = await Runtime.evaluate({ expression: `
            document.querySelector('[contenteditable="true"]').outerHTML
        ` });
        console.log(res.result.value);
        await client.close();
    } catch(e) {
        console.error(e);
    }
})();
