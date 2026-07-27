const CDP = require('chrome-remote-interface');
const fs = require('fs');

(async function() {
    try {
        const client = await CDP({ port: 9000 });
        const { DOM, Runtime } = client;
        
        const doc = await DOM.getDocument({ depth: -1 });
        const node = await DOM.querySelector({ nodeId: doc.root.nodeId, selector: 'input[type="file"]' });
        
        if (node && node.nodeId) {
            console.log('Uploading file...');
            await DOM.setFileInputFiles({ files: ['C:/Projects/antigravity-core/.agents/sidecars/antigravity_phone_chat/scratch/test_image.png'], nodeId: node.nodeId });
            
            console.log('Waiting 3 seconds for UI to update...');
            await new Promise(r => setTimeout(r, 3000));
            
            console.log('Dumping HTML...');
            let res = await Runtime.evaluate({ expression: `document.body.outerHTML` });
            fs.writeFileSync('scratch/dump_html_with_file.html', res.result.value || '');
            console.log('Saved to dump_html_with_file.html');
        }
        await client.close();
    } catch (e) {
        console.error(e);
    }
})();
