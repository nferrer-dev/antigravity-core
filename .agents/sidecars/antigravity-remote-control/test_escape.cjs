const CDP = require('chrome-remote-interface');
const fs = require('fs');

async function run() {
    let client;
    try {
        client = await CDP({ port: 63798 });
        const { Runtime, Input, DOM } = client;
        await Runtime.enable();
        await DOM.enable();

        console.log('Connected to CDP. Sending Escape key...');
        
        await Input.dispatchKeyEvent({
            type: 'keyDown',
            windowsVirtualKeyCode: 27, // Escape
            nativeVirtualKeyCode: 27,
            macCharCode: 27,
            unmodifiedText: '',
            text: ''
        });
        await Input.dispatchKeyEvent({
            type: 'keyUp',
            windowsVirtualKeyCode: 27,
            nativeVirtualKeyCode: 27,
            macCharCode: 27,
            unmodifiedText: '',
            text: ''
        });
        
        console.log('Escape sent!');

        console.log('Waiting 3 seconds...');
        await new Promise(r => setTimeout(r, 3000));

        const htmlRes = await Runtime.evaluate({
            expression: 'document.documentElement.outerHTML',
            returnByValue: true
        });

        fs.writeFileSync('dom_after_escape.html', htmlRes.result.value);
        console.log('Saved dom_after_escape.html');

        const loadingCheck = await Runtime.evaluate({
            expression: `
                (function() {
                    const el = document.querySelector('[data-testid="agent-loading"]');
                    return el ? el.textContent : null;
                })()
            `,
            returnByValue: true
        });
        console.log('Agent loading text after Escape:', loadingCheck.result.value);

    } catch (err) {
        console.error('Error:', err);
    } finally {
        if (client) {
            await client.close();
        }
    }
}

run();
