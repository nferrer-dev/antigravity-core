const CDP = require('chrome-remote-interface');

async function run() {
    let client;
    try {
        client = await CDP({ port: 63798 });
        const { Runtime } = client;
        await Runtime.enable();

        let res = await Runtime.evaluate({
            expression: `
                Object.keys(window).filter(k => !/webkit|moz|ms|on|Performance|Web|Canvas|RTC|DOM|CSS|HTML|SVG|URL|IDB|Event|Error|File|Crypto|Media|Video|Audio|Text|Data|Mime|Math|JSON/.test(k))
            `,
            returnByValue: true
        });
        console.log('Custom globals:', res.result.value);

    } catch (err) {
        console.error('Error:', err);
    } finally {
        if (client) await client.close();
    }
}

run();
