const CDP = require('chrome-remote-interface');

async function run() {
    let client;
    try {
        client = await CDP({ port: 63798 });
        const { Runtime } = client;
        await Runtime.enable();

        let res = await Runtime.evaluate({
            expression: `
                // Try to find React internals
                const roots = Array.from(document.querySelectorAll('*')).filter(n => Object.keys(n).some(k => k.startsWith('__reactContainer')));
                roots.length > 0 ? "Found React root" : "No React root";
            `,
            returnByValue: true
        });
        console.log(res.result.value);

    } catch (err) {
        console.error('Error:', err);
    } finally {
        if (client) await client.close();
    }
}

run();
