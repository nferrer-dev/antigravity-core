const CDP = require('chrome-remote-interface');
(async function() {
    try {
        const client = await CDP({ port: 9000 });
        const { Runtime } = client;
        
        const script = `
            const msgs = Array.from(document.querySelectorAll('[data-testid="user-input-step"]'));
            const target = msgs.find(m => m.textContent.includes('Did it work?'));
            target ? target.outerHTML : 'Not found';
        `;
        const result = await Runtime.evaluate({ expression: script });
        console.log(result.result.value);
        
        await client.close();
    } catch (e) {
        console.error(e);
    }
})();
