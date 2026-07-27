const CDP = require('chrome-remote-interface');
const path = require('path');
const fs = require('fs');

(async function() {
    try {
        const client = await CDP({ port: 9000 });
        const { DOM, Runtime } = client;
        
        // 1. Upload a file
        const doc = await DOM.getDocument({ depth: -1 });
        const node = await DOM.querySelector({ nodeId: doc.root.nodeId, selector: 'input[type="file"]' });
        
        if (node && node.nodeId) {
            console.log('Uploading real_image.png...');
            const absolutePath = path.resolve('scratch/real_image.png');
            await DOM.setFileInputFiles({ files: [absolutePath], nodeId: node.nodeId });
            
            console.log('Waiting 3 seconds...');
            await new Promise(r => setTimeout(r, 3000));
            
            // 2. Click the remove buttons
            console.log('Clicking remove buttons...');
            let clickRes = await Runtime.evaluate({ expression: `
                (function() {
                    let btns = document.querySelectorAll('.group.relative.inline-flex button');
                    let clicked = 0;
                    btns.forEach(b => {
                        b.click();
                        clicked++;
                    });
                    return clicked;
                })();
            ` });
            console.log('Clicked', clickRes.result.value, 'buttons');
            
            console.log('Waiting 2 seconds...');
            await new Promise(r => setTimeout(r, 2000));
            
            let htmlRes = await Runtime.evaluate({ expression: `document.body.outerHTML` });
            fs.writeFileSync('scratch/dump_html_after_remove_btn.html', htmlRes.result.value || '');
            console.log('Dumped HTML.');
        }
        await client.close();
    } catch (e) {
        console.error(e);
    }
})();
