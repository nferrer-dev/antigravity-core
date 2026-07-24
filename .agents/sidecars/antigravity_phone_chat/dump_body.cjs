const cdp = require('chrome-remote-interface');
(async function() {
    try {
        const client = await cdp({ port: 7800 });
        const { Runtime } = client;
        await Runtime.enable();
        const res = await Runtime.evaluate({
            expression: '(() => { return document.body.innerHTML; })()',
            returnByValue: true
        });
        const fs = require('fs');
        fs.writeFileSync('dump_body.html', res.result.value);
        console.log("Written to dump_body.html");
        await client.close();
    } catch (err) {
        console.error(err);
    }
})();
