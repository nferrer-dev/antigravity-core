const CDP = require('chrome-remote-interface');
const fs = require('fs');
(async function() {
    try {
        const client = await CDP({ port: 9000 });
        const { DOM, Runtime } = client;
        
        fs.writeFileSync('scratch/dummy.txt', 'hello world');
        
        const doc = await DOM.getDocument({ depth: -1 });
        const node = await DOM.querySelector({ nodeId: doc.root.nodeId, selector: 'input[type="file"]' });
        
        if (node && node.nodeId) {
            await DOM.setFileInputFiles({ files: ['C:/Projects/antigravity-core/.agents/sidecars/antigravity_phone_chat/scratch/dummy.txt'], nodeId: node.nodeId });
            
            const resolved = await DOM.resolveNode({ nodeId: node.nodeId });
            const before = await Runtime.callFunctionOn({
                objectId: resolved.object.objectId,
                functionDeclaration: 'function() { return this.files.length; }',
                returnByValue: true
            });
            console.log('Files before clear:', before.result.value);
            
            await DOM.setFileInputFiles({ files: [], nodeId: node.nodeId });
            
            const after = await Runtime.callFunctionOn({
                objectId: resolved.object.objectId,
                functionDeclaration: 'function() { return this.files.length; }',
                returnByValue: true
            });
            console.log('Files after clear:', after.result.value);
        }
        await client.close();
    } catch (e) {
        console.error(e);
    }
})();
