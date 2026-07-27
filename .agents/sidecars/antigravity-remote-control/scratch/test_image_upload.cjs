const CDP = require('chrome-remote-interface');
const fs = require('fs');

// Create a valid 1x1 PNG image
const pngBase64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";
const pngBuffer = Buffer.from(pngBase64, 'base64');

(async function() {
    try {
        const client = await CDP({ port: 9000 });
        const { DOM, Runtime } = client;
        
        fs.writeFileSync('scratch/test_image.png', pngBuffer);
        
        const doc = await DOM.getDocument({ depth: -1 });
        const node = await DOM.querySelector({ nodeId: doc.root.nodeId, selector: 'input[type="file"]' });
        
        if (node && node.nodeId) {
            await DOM.setFileInputFiles({ files: ['C:/Projects/antigravity-core/.agents/sidecars/antigravity_phone_chat/scratch/test_image.png'], nodeId: node.nodeId });
            
            console.log('Uploaded image. Waiting 3 seconds for React to process...');
            await new Promise(r => setTimeout(r, 3000));
            
            const script = `
                const inputArea = document.querySelector('[data-testid="user-input-step"]') || document.body;
                inputArea.outerHTML;
            `;
            const result = await Runtime.evaluate({ expression: script });
            const html = result.result.value || '';
            fs.writeFileSync('scratch/dump_input_area.html', html);
            console.log('Dumped input area html');
        }
        await client.close();
    } catch (e) {
        console.error(e);
    }
})();
