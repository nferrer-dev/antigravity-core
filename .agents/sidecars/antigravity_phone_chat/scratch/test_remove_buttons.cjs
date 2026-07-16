const CDP = require('chrome-remote-interface');
(async function() {
    try {
        const client = await CDP({ port: 9000 });
        const { Runtime } = client;
        
        const script = `(() => {
            const btns = document.querySelectorAll('button');
            return Array.from(btns).map(b => ({
                label: b.getAttribute('aria-label') || b.textContent || b.className,
                html: b.outerHTML.substring(0, 150)
            })).filter(b => b.label && b.label.toLowerCase().includes('remove'));
        })()`;
        
        const result = await Runtime.evaluate({ expression: script, returnByValue: true });
        console.log('Remove buttons:', result.result.value);
        
        await client.close();
    } catch (e) {
        console.error(e);
    }
})();
