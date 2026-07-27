const CDP = require('chrome-remote-interface');
async function run() {
    const client = await CDP({ port: 9222 });
    const { Runtime } = client;
    const res = await Runtime.evaluate({
        expression: `
            (() => {
                const els = Array.from(document.querySelectorAll('*'));
                return els.filter(el => el.children.length === 0 && el.innerText).map(el => el.innerText.trim());
            })();
        `,
        returnByValue: true
    });
    console.log(JSON.stringify(res.result.value.filter(t => t.toLowerCase().includes('running')), null, 2));
    await client.close();
}
run().catch(console.error);
