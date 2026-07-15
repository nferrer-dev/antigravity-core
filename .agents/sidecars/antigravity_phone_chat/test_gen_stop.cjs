const CDP = require('chrome-remote-interface');

async function run() {
    let client;
    try {
        client = await CDP({ port: 63798 });
        const { Runtime } = client;
        await Runtime.enable();

        console.log('Sending message: Count to 1000 really slowly...');
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

        let html = await Runtime.evaluate({
            expression: 'document.documentElement.outerHTML',
            returnByValue: true
        });
        const len1 = html.result.value.length;
        console.log('DOM size before stop:', len1);

        console.log('Clicking Stop button (Cancel Ctrl+D)...');
        await Runtime.evaluate({
            expression: `
                const stopBtn = document.querySelector('button[aria-label="Cancel (Ctrl+D)"], button svg.lucide-square')?.closest('button') || document.querySelector('button[aria-label="Cancel (Ctrl+D)"]');
                if (stopBtn) stopBtn.click();
            `
        });

        console.log('Waiting 3 seconds...');
        await new Promise(r => setTimeout(r, 3000));

        html = await Runtime.evaluate({
            expression: 'document.documentElement.outerHTML',
            returnByValue: true
        });
        const len2 = html.result.value.length;
        console.log('DOM size after stop:', len2);

        console.log('Waiting 3 more seconds...');
        await new Promise(r => setTimeout(r, 3000));

        html = await Runtime.evaluate({
            expression: 'document.documentElement.outerHTML',
            returnByValue: true
        });
        const len3 = html.result.value.length;
        console.log('DOM size after 6 seconds:', len3);

    } catch (err) {
        console.error('Error:', err);
    } finally {
        if (client) await client.close();
    }
}

run();
