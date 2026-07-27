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
            
            // Wait 2 seconds for React to render
            await new Promise(r => setTimeout(r, 2000));
            
            // Dump buttons
            const script = `(() => {
                const btns = Array.from(document.querySelectorAll('button'));
                return btns.map(b => ({
                    label: b.getAttribute('aria-label') || '',
                    className: b.className,
                    html: b.outerHTML.substring(0, 300)
                })).filter(b => b.html.includes('svg'));
            })()`;
            
            const result = await Runtime.evaluate({ expression: script, returnByValue: true });
            console.log('Buttons with SVGs:', JSON.stringify(result.result.value, null, 2));
        }
        await client.close();
    } catch (e) {
        console.error(e);
    }
})();
