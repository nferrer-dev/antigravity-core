const CDP = require('chrome-remote-interface');
const fs = require('fs');
(async function() {
    try {
        const client = await CDP({ port: 9000 });
        const { Runtime } = client;
        
        const script = `
            const msgs = Array.from(document.querySelectorAll('[data-ag-id]'));
            msgs.map(m => m.outerHTML).join('\\n')
        `;
        const result = await Runtime.evaluate({ expression: script });
        const html = result.result.value || '';
        fs.writeFileSync('scratch/dump_html.html', html);
        console.log('Dumped html');
        await client.close();
    } catch (e) {
        console.error(e);
    }
})();
