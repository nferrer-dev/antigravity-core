const CDP = require('chrome-remote-interface');
async function run() {
    try {
        const client = await CDP({ port: 7800 });
        const { Runtime } = client;
        const res = await Runtime.evaluate({ 
            expression: `
            (async () => {
    try {
        const state = { mode: 'Unknown', model: 'Unknown' };

        // 1. Get Mode (Fast/Planning)
        const allEls = Array.from(document.querySelectorAll('*'));

        // 2. Get Model
        const KNOWN_MODELS = ["Gemini", "Claude", "GPT"];
        const textNodes2 = allEls.filter(el => el.children.length === 0 && el.innerText);
        
        // 3. Get Running Tasks
        const taskRegex = /^\\d+\\s+(task|subagent)(s)?(\\s+running)?$/i;
        const taskEl = textNodes2.find(el => {
            return taskRegex.test(el.innerText.trim()) && el.closest('button');
        });
        
        if (taskEl) {
            state.runningTasksText = taskEl.innerText.trim();
        } else {
            state.runningTasksText = null;
        }

        return state;
    } catch (e) {
        return { error: e.toString() };
    }
})()
            `,
            awaitPromise: true,
            returnByValue: true
        });
        console.log(JSON.stringify(res.result.value, null, 2));
        await client.close();
    } catch (e) {
        console.error(e);
    }
}
run();
