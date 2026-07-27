const CDP = require('chrome-remote-interface');
(async function() {
    try {
        const client = await CDP({ port: 9000 });
        const { Runtime } = client;
        
        const script = `(() => {
            const btns = Array.from(document.querySelectorAll('button'));
            return btns.map(b => ({
                label: b.getAttribute('aria-label') || '',
                className: b.className,
                html: b.outerHTML.substring(0, 300)
            })).filter(b => b.html.includes('svg') || b.label.toLowerCase().includes('remove') || b.label.toLowerCase().includes('delete') || b.label.toLowerCase().includes('cancel'));
        })()`;
        
        const result = await Runtime.evaluate({ expression: script, returnByValue: true });
        console.log('Possible remove buttons:', JSON.stringify(result.result.value, null, 2));
        
        await client.close();
    } catch (e) {
        console.error(e);
    }
})();
