const CDP = require('chrome-remote-interface');

async function run() {
    let client;
    try {
        client = await CDP({ port: 63798 });
        const { Input, Runtime } = client;
        await Runtime.enable();

        console.log('Sending message: Count to 1000 really slowly...');
        await Runtime.evaluate({
            expression: `
                const el = document.querySelector('.ProseMirror');
                if (el) {
                    el.innerHTML = '<p>Count to 1000 really slowly part 4</p>';
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    setTimeout(() => {
                        const sendBtn = document.querySelector('button[aria-label="Send message"]');
                        if (sendBtn) sendBtn.click();
                    }, 100);
                }
            `,
            awaitPromise: true
        });

        console.log('Waiting 2 seconds...');
        await new Promise(r => setTimeout(r, 2000));

        let html = await Runtime.evaluate({
            expression: 'document.documentElement.outerHTML',
            returnByValue: true
        });
        console.log('DOM size before stop:', html.result.value.length);

        console.log('Sending Ctrl+C...');
        await Input.dispatchKeyEvent({ type: 'keyDown', key: 'Control', code: 'ControlLeft', windowsVirtualKeyCode: 17, nativeVirtualKeyCode: 17 });
        await Input.dispatchKeyEvent({ type: 'keyDown', key: 'c', code: 'KeyC', windowsVirtualKeyCode: 67, nativeVirtualKeyCode: 67, modifiers: 2 });
        await Input.dispatchKeyEvent({ type: 'keyUp', key: 'c', code: 'KeyC', windowsVirtualKeyCode: 67, nativeVirtualKeyCode: 67, modifiers: 2 });
        await Input.dispatchKeyEvent({ type: 'keyUp', key: 'Control', code: 'ControlLeft', windowsVirtualKeyCode: 17, nativeVirtualKeyCode: 17 });

        console.log('Waiting 3 seconds...');
        await new Promise(r => setTimeout(r, 3000));

        html = await Runtime.evaluate({
            expression: 'document.documentElement.outerHTML',
            returnByValue: true
        });
        console.log('DOM size after 3s:', html.result.value.length);
        
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
