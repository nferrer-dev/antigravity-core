const CDP = require('chrome-remote-interface');
const fs = require('fs');
const path = require('path');

(async function() {
    try {
        const client = await CDP({ port: 9000 });
        const { DOM, Runtime } = client;
        
        const doc = await DOM.getDocument({ depth: -1 });
        const node = await DOM.querySelector({ nodeId: doc.root.nodeId, selector: 'input[type="file"]' });
        
        if (node && node.nodeId) {
            console.log('Uploading real_image.png...');
            const absolutePath = path.resolve('scratch/real_image.png');
            await DOM.setFileInputFiles({ files: [absolutePath], nodeId: node.nodeId });
            
            console.log('Waiting 3 seconds...');
            await new Promise(r => setTimeout(r, 3000));
            
            let htmlRes = await Runtime.evaluate({ expression: `document.body.outerHTML` });
            fs.writeFileSync('scratch/dump_html_real_image.html', htmlRes.result.value || '');
            console.log('Dumped HTML.');
        }
        await client.close();
    } catch (e) {
        console.error(e);
    }
})();
