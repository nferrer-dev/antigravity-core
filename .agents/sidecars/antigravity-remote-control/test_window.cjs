const CDP = require('chrome-remote-interface');

async function run() {
    let client;
    try {
        client = await CDP({ port: 63798 });
        const { Runtime } = client;
        await Runtime.enable();

        let res = await Runtime.evaluate({
            expression: `
                Object.keys(window).filter(k => k.toLowerCase().includes('stop') || k.toLowerCase().includes('cancel') || k.toLowerCase().includes('abort')).join(', ')
            `,
            returnByValue: true
        });
        console.log('Window keys:', res.result.value);

    } catch (err) {
        console.error('Error:', err);
    } finally {
        if (client) await client.close();
    }
}

run();
