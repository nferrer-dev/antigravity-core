const CDP = require('chrome-remote-interface');

async function run() {
    let client;
    try {
        client = await CDP({ port: 63798 });
        const { Runtime } = client;
        await Runtime.enable();

        console.log('Sending message...');
        await Runtime.evaluate({
            expression: `
                const el = document.querySelector('.ProseMirror');
                if (el) {
                    el.innerHTML = '<p>Count to 1000 really slowly</p>';
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    setTimeout(() => {
                        const sendBtn = document.querySelector('button[aria-label="Send message"]');
                        if (sendBtn) sendBtn.click();
                    }, 100);
                }
            `,
            awaitPromise: true
        });

        console.log('Waiting 2 seconds for generation to start...');
        await new Promise(r => setTimeout(r, 2000));

        let check = await Runtime.evaluate({
            expression: '!!document.querySelector(`[data-testid="agent-loading"]`)',
            returnByValue: true
        });
        console.log('Is generating started?', check.result.value);

        console.log('Clicking Stop button...');
        await Runtime.evaluate({
            expression: `
                const stopBtn = document.querySelector('button[aria-label="Cancel (Ctrl+D)"], button svg.lucide-square')?.closest('button') || document.querySelector('button[aria-label="Cancel (Ctrl+D)"]');
                if (stopBtn) stopBtn.click();
            `
        });

        console.log('Waiting 2 seconds...');
        await new Promise(r => setTimeout(r, 2000));

        check = await Runtime.evaluate({
            expression: '!!document.querySelector(`[data-testid="agent-loading"]`)',
            returnByValue: true
        });
        console.log('Is generating after stop?', check.result.value);

    } catch (err) {
        console.error('Error:', err);
    } finally {
        if (client) await client.close();
    }
}

run();
