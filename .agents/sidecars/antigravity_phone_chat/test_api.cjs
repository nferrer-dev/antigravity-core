const CDP = require('chrome-remote-interface');

async function run() {
    let client;
    try {
        client = await CDP({ port: 63798 });
        const { Runtime } = client;
        await Runtime.enable();

        let res = await Runtime.evaluate({
            expression: `
                function getMethods(obj) {
                    if (!obj) return null;
                    return Object.getOwnPropertyNames(obj).concat(
                        Object.getOwnPropertyNames(Object.getPrototypeOf(obj) || {})
                    );
                }
                JSON.stringify({
                    agent: getMethods(window.agent),
                    ide: getMethods(window.ide)
                })
            `,
            returnByValue: true
        });
        console.log('API:', JSON.parse(res.result.value));

    } catch (err) {
        console.error('Error:', err);
    } finally {
        if (client) await client.close();
    }
}

run();
