const CDP = require('chrome-remote-interface');
const path = require('path');

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
            
            // 2. Focus the compose box
            console.log('Focusing compose box...');
            let res = await Runtime.evaluate({ expression: `
                const box = document.querySelector('[role="textbox"]');
                if (box) box.focus();
                !!box;
            ` });
            console.log('Focused?', res.result.value);
            
            // 3. Send Backspace
            console.log('Sending Backspace...');
            await Input.dispatchKeyEvent({ type: 'keyDown', key: 'Backspace', code: 'Backspace', windowsVirtualKeyCode: 8, nativeVirtualKeyCode: 8 });
            await Input.dispatchKeyEvent({ type: 'keyUp', key: 'Backspace', code: 'Backspace', windowsVirtualKeyCode: 8, nativeVirtualKeyCode: 8 });
            
            console.log('Waiting 2 seconds...');
            await new Promise(r => setTimeout(r, 2000));
            
            // 4. Dump HTML to see if attachment is gone
            let htmlRes = await Runtime.evaluate({ expression: `document.body.outerHTML` });
            require('fs').writeFileSync('scratch/dump_html_after_backspace.html', htmlRes.result.value || '');
            console.log('Dumped to scratch/dump_html_after_backspace.html');
        }
        await client.close();
    } catch (e) {
        console.error(e);
    }
})();
