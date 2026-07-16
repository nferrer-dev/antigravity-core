const CDP = require('chrome-remote-interface');
(async function() {
    try {
        const client = await CDP({ port: 9000 });
        const { DOM, Input } = client;
        
        console.log('Testing setFileInputFiles methods...');
        const doc = await DOM.getDocument({ depth: -1 });
        const node = await DOM.querySelector({ nodeId: doc.root.nodeId, selector: 'input[type="file"]' });
        console.log('Found node:', node);
        
        if (node.nodeId) {
            try {
                await DOM.setFileInputFiles({ files: [], nodeId: node.nodeId });
                console.log('DOM.setFileInputFiles SUCCESS');
            } catch (e) {
                console.error('DOM error:', e.message);
            }
        }
        await client.close();
    } catch (e) {
        console.error(e);
    }
})();
