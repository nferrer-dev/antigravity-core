const CDP = require('chrome-remote-interface');
const fs = require('fs');

(async function() {
    try {
        const client = await CDP({ port: 9000 });
        const { DOM, Runtime } = client;
        
        const doc = await DOM.getDocument({ depth: -1 });
        const node = await DOM.querySelector({ nodeId: doc.root.nodeId, selector: 'input[type="file"]' });
        
        if (node && node.nodeId) {
            console.log('Setting file...');
            await DOM.setFileInputFiles({ files: ['C:/Projects/antigravity-core/.agents/sidecars/antigravity_phone_chat/scratch/test_image.png'], nodeId: node.nodeId });
            
            // Try to trigger a change event so React knows about it
            await Runtime.evaluate({ expression: `
                const input = document.querySelector('input[type="file"]');
                input.dispatchEvent(new Event('change', { bubbles: true }));
            `});
            
            console.log('Waiting 2 seconds...');
            await new Promise(r => setTimeout(r, 2000));
            
            // Check if chip is rendered
            let res = await Runtime.evaluate({ expression: `
                document.querySelector('.absolute.bottom-full.inset-x-0').outerHTML
            ` });
            console.log('Chip area HTML:', res.result.value);
        }
        await client.close();
    } catch (e) {
        console.error(e);
    }
})();
