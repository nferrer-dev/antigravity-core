const CDP = require('chrome-remote-interface');
const fs = require('fs');

async function run() {
    let client;
    try {
        client = await CDP({ port: 63798 });
        const { Runtime, DOM } = client;
        await Runtime.enable();
        await DOM.enable();

        console.log('Connected to CDP. Evaluating click...');
        
        // Find and click the Cancel button
        const evalRes = await Runtime.evaluate({
            expression: `
                (function() {
                    const stopBtn = document.querySelector('button[aria-label="Cancel (Ctrl+D)"], button svg.lucide-square')?.closest('button') || document.querySelector('button[aria-label="Cancel (Ctrl+D)"]');
                    if (stopBtn) {
                        stopBtn.click();
                        return true;
                    }
                    return false;
                })()
            `,
            returnByValue: true
        });
        
        console.log('Click result:', evalRes.result.value);

        console.log('Waiting 3 seconds...');
        await new Promise(r => setTimeout(r, 3000));

        const htmlRes = await Runtime.evaluate({
            expression: 'document.documentElement.outerHTML',
            returnByValue: true
        });

        fs.writeFileSync('dom_after_cancel.html', htmlRes.result.value);
        console.log('Saved dom_after_cancel.html');

        const loadingCheck = await Runtime.evaluate({
            expression: `
                (function() {
                    const el = document.querySelector('[data-testid="agent-loading"]');
                    return el ? el.textContent : null;
                })()
            `,
            returnByValue: true
        });
        console.log('Agent loading text after cancel:', loadingCheck.result.value);

    } catch (err) {
        console.error('Error:', err);
    } finally {
        if (client) {
            await client.close();
        }
    }
}

run();
