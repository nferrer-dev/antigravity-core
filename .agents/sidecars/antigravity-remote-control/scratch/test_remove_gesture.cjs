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
            console.log('Uploaded. Waiting 2s...');
            await new Promise(r => setTimeout(r, 2000));
            
            // Find the remove button nodeId
            const script = `(() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const target = btns.find(b => {
                    const text = b.textContent || b.getAttribute('aria-label') || '';
                    return text.includes('dummy.txt');
                });
                if (target) {
                    target.setAttribute('data-test-remove-target', 'true');
                    return true;
                }
                return false;
            })()`;
            
            const result = await Runtime.evaluate({ expression: script, returnByValue: true });
            if (result.result.value) {
                console.log('Found button, clicking with userGesture');
                const btnNode = await DOM.querySelector({ nodeId: doc.root.nodeId, selector: '[data-test-remove-target="true"]' });
                if (btnNode && btnNode.nodeId) {
                    const resolved = await DOM.resolveNode({ nodeId: btnNode.nodeId });
                    await Runtime.callFunctionOn({
                        objectId: resolved.object.objectId,
                        functionDeclaration: 'function() { this.click(); }',
                        userGesture: true
                    });
                    console.log('Clicked!');
                }
            } else {
                console.log('Button not found via script');
            }
        }
        await client.close();
    } catch (e) {
        console.error(e);
    }
})();
