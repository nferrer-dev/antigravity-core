const CDP = require('chrome-remote-interface');

async function run() {
    let client;
    try {
        client = await CDP({ port: 63798 });
        const { Input, Runtime } = client;
        await Runtime.enable();

        console.log('Sending message: Write a very very long poem...');
        await Runtime.evaluate({
            expression: `
                const el = document.querySelector('.ProseMirror');
                if (el) {
                    el.innerHTML = '<p>Write a very very long poem, at least 500 words</p>';
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    setTimeout(() => {
                        const sendBtn = document.querySelector('button[aria-label="Send message"]');
                        if (sendBtn) sendBtn.click();
                    }, 100);
                }
            `,
            awaitPromise: true
        });

        console.log('Waiting 3 seconds for generation...');
        await new Promise(r => setTimeout(r, 3000));

        let res = await Runtime.evaluate({
            expression: 'document.querySelectorAll(".message-content").length ? document.querySelectorAll(".message-content")[document.querySelectorAll(".message-content").length - 1].textContent : "none"',
            returnByValue: true
        });
        console.log('Text before stop (len ' + res.result.value.length + '):', res.result.value.substring(0, 50));

        console.log('Sending Ctrl+D...');
        await Input.dispatchKeyEvent({ type: 'keyDown', key: 'Control', code: 'ControlLeft', windowsVirtualKeyCode: 17, nativeVirtualKeyCode: 17 });
        await Input.dispatchKeyEvent({ type: 'keyDown', key: 'd', code: 'KeyD', windowsVirtualKeyCode: 68, nativeVirtualKeyCode: 68, modifiers: 2 });
        await Input.dispatchKeyEvent({ type: 'keyUp', key: 'd', code: 'KeyD', windowsVirtualKeyCode: 68, nativeVirtualKeyCode: 68, modifiers: 2 });
        await Input.dispatchKeyEvent({ type: 'keyUp', key: 'Control', code: 'ControlLeft', windowsVirtualKeyCode: 17, nativeVirtualKeyCode: 17 });

        console.log('Waiting 5 seconds...');
        await new Promise(r => setTimeout(r, 5000));

        res = await Runtime.evaluate({
            expression: 'document.querySelectorAll(".message-content").length ? document.querySelectorAll(".message-content")[document.querySelectorAll(".message-content").length - 1].textContent : "none"',
            returnByValue: true
        });
        console.log('Text after 5s (len ' + res.result.value.length + '):', res.result.value.substring(0, 50));

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
