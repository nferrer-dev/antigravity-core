const WebSocket = require('ws');
const ws = new WebSocket('ws://127.0.0.1:9000/devtools/page/E698F92DB9A7D87C1CB2497F230E3189');
let id = 1;
function call(method, params = {}) {
    return new Promise(resolve => {
        const cid = id++;
        const listener = (msg) => {
            const d = JSON.parse(msg);
            if (d.id === cid) {
                ws.off('message', listener);
                resolve(d.result);
            }
        };
        ws.on('message', listener);
        ws.send(JSON.stringify({ id: cid, method, params }));
    });
}
ws.on('open', async () => {
    // Listen for fileChooserOpened
    ws.on('message', async (data) => {
        const msg = JSON.parse(data);
        if (msg.method === 'Page.fileChooserOpened') {
            console.log('File chooser opened natively!');
            const path = require('path').resolve('test_doc.pdf');
            await call('Page.handleFileChooser', { action: 'accept', files: [path] });
            console.log('Handled File Chooser.');
            setTimeout(async () => {
                const doc = await call('DOM.getDocument', { depth: -1 });
                const { nodeIds: chips } = await call('DOM.querySelectorAll', { nodeId: doc.root.nodeId, selector: 'button[aria-label^="Remove"]' });
                console.log('Attachment chips found:', chips.length);
                ws.close();
            }, 2000);
        }
    });

    const fs = require('fs');
    fs.writeFileSync('test_doc.pdf', 'fake pdf content');

    await call('Page.enable');
    await call('Page.setInterceptFileChooserDialog', { enabled: true });

    const doc = await call('DOM.getDocument', { depth: -1 });
    const { nodeIds } = await call('DOM.querySelectorAll', { nodeId: doc.root.nodeId, selector: 'input[type="file"]' });
    
    if (nodeIds.length > 0) {
        const { object } = await call('DOM.resolveNode', { nodeId: nodeIds[0] });
        
        await call('Runtime.callFunctionOn', {
            objectId: object.objectId,
            functionDeclaration: 'function() { this.click(); }',
            userGesture: true
        });
        console.log('Clicked input with userGesture: true');
    } else {
        console.log("Input not found!");
        ws.close();
    }
});
