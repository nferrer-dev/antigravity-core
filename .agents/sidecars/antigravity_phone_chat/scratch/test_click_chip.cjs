const CDP = require('chrome-remote-interface');
const path = require('path');
const fs = require('fs');

(async function() {
    try {
        const client = await CDP({ port: 9000 });
        const { DOM, Runtime, Input } = client;
        
        // 1. Upload a file
        const doc = await DOM.getDocument({ depth: -1 });
        const node = await DOM.querySelector({ nodeId: doc.root.nodeId, selector: 'input[type="file"]' });
        
        if (node && node.nodeId) {
            console.log('Uploading file...');
            const absolutePath = path.resolve('scratch/test_image.png');
            await DOM.setFileInputFiles({ files: [absolutePath], nodeId: node.nodeId });
            
            console.log('Waiting 3 seconds for UI to update...');
            await new Promise(r => setTimeout(r, 3000));
            
            let res = await Runtime.evaluate({ expression: `document.querySelectorAll('.hover\\\\:opacity-50.cursor-pointer').length` });
            console.log('Chips before click:', res.result.value);
            
            // 2. Click the chips
            console.log('Clicking chips...');
            await Runtime.evaluate({ expression: `
                document.querySelectorAll('.hover\\\\:opacity-50.cursor-pointer').forEach(c => c.click());
            ` });
            
            console.log('Waiting 2 seconds...');
            await new Promise(r => setTimeout(r, 2000));
            
            let res2 = await Runtime.evaluate({ expression: `document.querySelectorAll('.hover\\\\:opacity-50.cursor-pointer').length` });
            console.log('Chips after click:', res2.result.value);
        }
        await client.close();
    } catch (e) {
        console.error(e);
    }
})();
