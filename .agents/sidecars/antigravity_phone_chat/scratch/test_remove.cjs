const CDP = require('chrome-remote-interface');
const fs = require('fs');
(async function() {
    try {
        const client = await CDP({ port: 9000 });
        const { DOM, Runtime } = client;
        
        // create a dummy file
        fs.writeFileSync('scratch/dummy.txt', 'hello world');
        
        console.log('Uploading dummy file...');
        const doc = await DOM.getDocument({ depth: -1 });
        const node = await DOM.querySelector({ nodeId: doc.root.nodeId, selector: 'input[type="file"]' });
        
        if (node && node.nodeId) {
            await DOM.setFileInputFiles({ files: ['C:/Projects/antigravity-core/.agents/sidecars/antigravity_phone_chat/scratch/dummy.txt'], nodeId: node.nodeId });
            console.log('Uploaded. Waiting 2s for UI to render chip...');
            await new Promise(r => setTimeout(r, 2000));
            
            // Now run a script in the page to find the remove button
            const script = `(() => {
                const els = Array.from(document.querySelectorAll('*'));
                // Find element containing dummy.txt
                const chip = els.find(el => el.textContent && el.textContent.includes('dummy.txt') && el.children.length === 0);
                if (!chip) return 'Chip not found';
                
                // Traverse up and find button
                let parent = chip.parentElement;
                while (parent) {
                    const btn = parent.querySelector('button');
                    if (btn) {
                        return {
                            buttonOuterHTML: btn.outerHTML,
                            chipText: chip.textContent
                        };
                    }
                    parent = parent.parentElement;
                }
                return 'Button not found in ancestors';
            })()`;
            
            const result = await Runtime.evaluate({ expression: script, returnByValue: true });
            console.log('Result:', result.result.value);
            
            // Clean up
            const removeScript = `(() => {
                const btn = document.querySelector('button[aria-label="Remove file"]');
                if (btn) { btn.click(); return 'clicked aria-label="Remove file"'; }
                
                // try to find any button with a tooltip or aria-label containing remove
                const allBtns = document.querySelectorAll('button');
                for (const b of allBtns) {
                    if (b.getAttribute('aria-label') && b.getAttribute('aria-label').toLowerCase().includes('remove')) {
                        b.click();
                        return 'clicked ' + b.getAttribute('aria-label');
                    }
                }
                return 'could not click';
            })()`;
            
            const rmResult = await Runtime.evaluate({ expression: removeScript, returnByValue: true });
            console.log('Remove result:', rmResult.result.value);
            
        }
        await client.close();
    } catch (e) {
        console.error(e);
    }
})();
