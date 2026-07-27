const CDP = require('chrome-remote-interface');

async function run() {
    let client;
    try {
        client = await CDP({ port: 63798 });
        const { Input, Runtime } = client;
        await Runtime.enable();

        await Runtime.evaluate({
            expression: `
                const el = document.querySelector('.ProseMirror');
                if (el) {
                    el.innerHTML = '<p>Write a 500 word essay about the history of Rome. Be extremely verbose and take your time.</p>';
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    setTimeout(() => {
                        const sendBtn = document.querySelector('button[aria-label="Send message"]');
                        if (sendBtn) sendBtn.click();
                    }, 100);
                }
            `,
            awaitPromise: true
        });

        console.log('Waiting 2.5 seconds...');
        await new Promise(r => setTimeout(r, 2500));

        let res = await Runtime.evaluate({
            expression: 'document.querySelectorAll(".message-content").length ? document.querySelectorAll(".message-content")[document.querySelectorAll(".message-content").length - 1].textContent : "none"',
            returnByValue: true
        });
        console.log('Text before stop (len ' + res.result.value.length + '):', res.result.value.substring(0, 50));

        console.log('Clicking Cancel (Ctrl+D)...');
        await Runtime.evaluate({
            expression: `
                const cancel = document.querySelector('[data-tooltip-id="input-send-button-cancel-tooltip"]');
                if (cancel) cancel.click();
            `
        });

        console.log('Waiting 4 seconds...');
        await new Promise(r => setTimeout(r, 4000));

        res = await Runtime.evaluate({
            expression: 'document.querySelectorAll(".message-content").length ? document.querySelectorAll(".message-content")[document.querySelectorAll(".message-content").length - 1].textContent : "none"',
            returnByValue: true
        });
        console.log('Text after 4s (len ' + res.result.value.length + '):', res.result.value.substring(0, 50));

        let isGen = await Runtime.evaluate({
            expression: '!!document.querySelector(\'[data-testid="agent-loading"]\')',
            returnByValue: true
        });
        console.log('Is generating?', isGen.result.value);

    } catch (err) {
        console.error('Error:', err);
    } finally {
        if (client) await client.close();
    }
}

run();
