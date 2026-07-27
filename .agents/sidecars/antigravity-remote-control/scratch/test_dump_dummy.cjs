const CDP = require('chrome-remote-interface');
(async function() {
    try {
        const client = await CDP({ port: 9000 });
        const { Runtime } = client;
        
        const script = `(() => {
            const els = document.querySelectorAll('*');
            return Array.from(els).map(b => ({
                tag: b.tagName,
                label: b.getAttribute('aria-label') || '',
                text: b.textContent || '',
                html: b.outerHTML.substring(0, 200)
            })).filter(b => b.text.toLowerCase().includes('dummy') || b.label.toLowerCase().includes('dummy') || b.html.toLowerCase().includes('dummy'));
        })()`;
        
        const result = await Runtime.evaluate({ expression: script, returnByValue: true });
        console.log('Dummy elements:', JSON.stringify(result.result.value, null, 2));
        
        await client.close();
    } catch (e) {
        console.error(e);
    }
})();
