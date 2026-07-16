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
            
            // Dispatch a change event on the file input
            const resolved = await DOM.resolveNode({ nodeId: node.nodeId });
            await Runtime.callFunctionOn({
                objectId: resolved.object.objectId,
                functionDeclaration: 'function() { this.dispatchEvent(new Event("change", { bubbles: true })); }',
            });
            
            console.log('Uploaded and dispatched change event. Waiting 2s...');
            await new Promise(r => setTimeout(r, 2000));
            
            // Dump buttons
            const script = `(() => {
                const btns = document.querySelectorAll('button');
                return Array.from(btns).map(b => ({
                    label: b.getAttribute('aria-label') || '',
                    text: b.textContent || '',
                    html: b.outerHTML.substring(0, 200)
                })).filter(b => b.label.toLowerCase().includes('remove') || b.label.toLowerCase().includes('delete'));
            })()`;
            
            const result = await Runtime.evaluate({ expression: script, returnByValue: true });
            console.log('Remove buttons:', JSON.stringify(result.result.value, null, 2));
        }
        await client.close();
    } catch (e) {
        console.error(e);
    }
})();
