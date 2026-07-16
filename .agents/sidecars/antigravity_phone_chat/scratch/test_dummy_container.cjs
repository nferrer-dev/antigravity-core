const CDP = require('chrome-remote-interface');
(async function() {
    try {
        const client = await CDP({ port: 9000 });
        const { Runtime } = client;
        
        const script = `(() => {
            const els = Array.from(document.querySelectorAll('*'));
            const dummyEl = els.find(b => b.textContent && b.textContent.includes('dummy') && b.children.length === 0);
            if (!dummyEl) return 'no dummy element';
            
            let parent = dummyEl.parentElement;
            let i = 0;
            while(parent && i < 3) {
                if (parent.querySelector('button, [role="button"]')) {
                    return {
                        html: parent.outerHTML.substring(0, 1000)
                    };
                }
                parent = parent.parentElement;
                i++;
            }
            return 'no button ancestor/sibling';
        })()`;
        
        const result = await Runtime.evaluate({ expression: script, returnByValue: true });
        console.log('Dummy container:', JSON.stringify(result.result.value, null, 2));
        
        await client.close();
    } catch (e) {
        console.error(e);
    }
})();
