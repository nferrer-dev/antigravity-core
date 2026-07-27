const CDP = require('chrome-remote-interface');
const fs = require('fs');
(async function() {
    try {
        const client = await CDP({ port: 9000 });
        const { DOM, Runtime } = client;
        
        fs.writeFileSync('scratch/dummy2.txt', 'hello world 2');
        
        const doc = await DOM.getDocument({ depth: -1 });
        const node = await DOM.querySelector({ nodeId: doc.root.nodeId, selector: 'input[type="file"]' });
        
        if (node && node.nodeId) {
            await DOM.setFileInputFiles({ files: ['C:/Projects/antigravity-core/.agents/sidecars/antigravity_phone_chat/scratch/dummy2.txt'], nodeId: node.nodeId });
            
            await new Promise(r => setTimeout(r, 2000));
            
            const script = `document.body.innerText`;
            const result = await Runtime.evaluate({ expression: script });
            fs.writeFileSync('scratch/dump_body.txt', result.result.value);
            console.log('Dumped body text to scratch/dump_body.txt');
        }
        await client.close();
    } catch (e) {
        console.error(e);
    }
})();
