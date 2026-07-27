import puppeteer from 'puppeteer';

async function runScenario(name, injectScript, background = false) {
    console.log(`\n--- Running Scenario: ${name} (Background: ${background}) ---`);
    const browser = await puppeteer.launch({ headless: true });
    const page = await browser.newPage();
    await page.goto('about:blank');

    const client = await page.target().createCDPSession();
    await client.send('Runtime.enable');
    await client.send('Runtime.addBinding', { name: '__agySyncTrigger' });
    
    if (background) {
        // Send page to background to simulate hidden tab
        await client.send('Page.enable');
        await client.send('Page.setWebLifecycleState', { state: 'hidden' });
    }

    let triggers = 0;
    client.on('Runtime.bindingCalled', (evt) => {
        if (evt.name === '__agySyncTrigger') triggers++;
    });

    await page.evaluate(injectScript);

    await page.evaluate(() => {
        window.mutationsCount = 0;
        setInterval(() => {
            const div = document.createElement('div');
            div.textContent = Math.random();
            document.body.appendChild(div);
            window.mutationsCount++;
        }, 10); // Every 10ms (100 mutations/sec)
    });

    await new Promise(r => setTimeout(r, 2000));
    const finalMutations = await page.evaluate(() => window.mutationsCount);
    
    console.log(`Mutations created: ${finalMutations}`);
    console.log(`Sync triggers received: ${triggers}`);
    
    await browser.close();
    return triggers;
}

const scenarioB = `
(function() {
    function triggerSync() {
        if (window.__agySyncTrigger) window.__agySyncTrigger(JSON.stringify({}));
    }
    let rafId = null;
    function rafSync() {
        if (rafId) return;
        rafId = requestAnimationFrame(() => {
            rafId = null;
            triggerSync();
        });
    }
    window.__agyObserver = new MutationObserver((mutations) => {
        rafSync();
    });
    window.__agyObserver.observe(document.body, { childList: true, subtree: true });
})();
`;

const scenarioD = `
(function() {
    function triggerSync() {
        if (window.__agySyncTrigger) window.__agySyncTrigger(JSON.stringify({}));
    }
    let syncTimeout = null;
    function throttledSync() {
        if (!syncTimeout) {
            syncTimeout = setTimeout(() => {
                syncTimeout = null;
                triggerSync();
            }, 50);
        }
    }
    window.__agyObserver = new MutationObserver((mutations) => {
        throttledSync();
    });
    window.__agyObserver.observe(document.body, { childList: true, subtree: true });
})();
`;

async function main() {
    await runScenario('B: requestAnimationFrame (Foreground)', scenarioB, false);
    await runScenario('B: requestAnimationFrame (Background)', scenarioB, true);
    await runScenario('D: 50ms throttle (Background)', scenarioD, true);
}

main().catch(console.error);
