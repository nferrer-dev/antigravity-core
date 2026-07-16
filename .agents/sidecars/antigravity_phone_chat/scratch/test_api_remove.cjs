const CDP = require('chrome-remote-interface');
const path = require('path');
const fs = require('fs');
const http = require('http');

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
            
            let res = await Runtime.evaluate({ expression: `document.querySelectorAll('img.object-cover').length` });
            console.log('Chips before API call:', res.result.value);
            
            // 2. Call the API
            console.log('Calling /remove-attachment API...');
            await new Promise((resolve, reject) => {
                const req = http.request({
                    hostname: '127.0.0.1',
                    port: 3000,
                    path: '/remove-attachment',
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                }, res => {
                    let data = '';
                    res.on('data', chunk => data += chunk);
                    res.on('end', () => {
                        console.log('API Response:', data);
                        resolve();
                    });
                });
                req.on('error', reject);
                req.write('{}');
                req.end();
            });
            
            console.log('Waiting 2 seconds...');
            await new Promise(r => setTimeout(r, 2000));
            
            let res2 = await Runtime.evaluate({ expression: `document.querySelectorAll('img.object-cover').length` });
            console.log('Chips after API call:', res2.result.value);
        }
        await client.close();
    } catch (e) {
        console.error(e);
    }
})();
