const CDP = require('chrome-remote-interface');
const fs = require('fs');
(async function() {
    try {
        const client = await CDP({ port: 9000 });
        const { Runtime } = client;
        
        const script = `
            Array.from(document.querySelectorAll('img')).map(img => img.src).join('\\n')
        `;
        const result = await Runtime.evaluate({ expression: script });
        const html = result.result.value || '';
        fs.writeFileSync('scratch/dump_images.txt', html);
        console.log('Dumped images');
        await client.close();
    } catch (e) {
        console.error(e);
    }
})();
