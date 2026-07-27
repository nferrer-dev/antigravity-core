const CDP = require('chrome-remote-interface');
async function run() {
    try {
        const client = await CDP({ port: 7800 });
        const { Runtime } = client;
        const res = await Runtime.evaluate({ 
            expression: '(async () => { const allEls = Array.from(document.querySelectorAll(\"*\")); const textNodes2 = allEls.filter(el => el.children.length === 0 && el.innerText); const taskRegex = /^\\\\d+\\\\s+(task|subagent)(s)?\\\\s+running$/i; const taskEl = textNodes2.find(el => taskRegex.test(el.innerText.trim()) && el.closest(\"button\")); return taskEl ? taskEl.innerText.trim() : null; })();',
            awaitPromise: true,
            returnByValue: true
        });
        console.log("PILL TEXT:", res.result.value);
    } catch(e) { console.error(e); }
    process.exit(0);
}
run();
