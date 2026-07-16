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
            
            console.log('Evaluating input.files before clear:');
            let res = await Runtime.evaluate({ expression: `document.querySelector('input[type="file"]').files.length` });
            console.log(res.result.value);
            
            console.log('Clearing with value=""...');
            await Runtime.evaluate({ expression: `document.querySelector('input[type="file"]').value = ""` });
            
            console.log('Evaluating input.files after clear:');
            res = await Runtime.evaluate({ expression: `document.querySelector('input[type="file"]').files.length` });
            console.log(res.result.value);
            
            console.log('Wait, what about DataTransfer? Does the app use a different method to track attachments?');
            // Let's dump all variables attached to the input element or window?
        }
        await client.close();
    } catch (e) {
        console.error(e);
    }
})();
