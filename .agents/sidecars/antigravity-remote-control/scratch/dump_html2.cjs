const CDP = require('chrome-remote-interface');
const fs = require('fs');
(async function() {
    try {
        const client = await CDP({ port: 9000 });
        const { Runtime } = client;
        let res = await Runtime.evaluate({ expression: `document.body.outerHTML` });
        fs.writeFileSync('scratch/dump_html2.html', res.result.value || '');
        await client.close();
    } catch(e) {
        console.error(e);
    }
})();
