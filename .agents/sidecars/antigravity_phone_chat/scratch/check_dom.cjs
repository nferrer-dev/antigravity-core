const CDP = require('chrome-remote-interface');
(async function() {
    try {
        const client = await CDP({ port: 9000 });
        const { DOM } = client;
        
        const doc = await DOM.getDocument({ depth: -1 });
        const { nodeIds } = await DOM.querySelectorAll({
            nodeId: doc.root.nodeId,
            selector: 'button[aria-label="Remove file"]'
        });
        
        console.log('Found remove buttons:', nodeIds.length);
        for (const id of nodeIds) {
            console.log('Button found with id:', id);
        }
        await client.close();
    } catch (e) {
        console.error(e);
    }
})();
