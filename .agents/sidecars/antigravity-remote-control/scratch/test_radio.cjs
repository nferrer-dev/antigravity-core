const puppeteer = require('puppeteer');

(async () => {
    const browser = await puppeteer.launch({ args: ['--no-sandbox', '--disable-setuid-sandbox'] });
    const page = await browser.newPage();
    
    // Serve the public folder
    const express = require('express');
    const app = express();
    app.use(express.static('public'));
    const server = app.listen(3015);
    
    // Inject a radio group into a fake page
    app.get('/test', (req, res) => {
        res.send(`
            <html>
                <head>
                    <link rel="stylesheet" href="/css/style.css">
                    <script src="/js/app_v8.js"></script>
                </head>
                <body>
                    <div id="chatContainer">
                        <div id="chatContent">
                            <vscode-radio data-stable-id="opt-a" name="q1">Option A</vscode-radio>
                            <vscode-radio data-stable-id="opt-b" name="q1">Option B</vscode-radio>
                        </div>
                    </div>
                </body>
            </html>
        `);
    });

    await page.goto('http://localhost:3015/test');
    
    // Stub fetch
    await page.evaluate(() => {
        window.fetchWithAuth = async (url) => {
            console.log('FETCH CALLED', url);
            return { ok: true, json: async () => ({}) };
        };
    });
    
    page.on('console', msg => console.log('PAGE:', msg.text()));

    const radioA = (await page.$$('vscode-radio'))[0];
    const radioB = (await page.$$('vscode-radio'))[1];
    
    console.log('Clicking Option A');
    await radioA.click();
    await new Promise(r => setTimeout(r, 100)); // wait for click to process
    
    let aChecked = await page.evaluate(el => el.checked, radioA);
    let bChecked = await page.evaluate(el => el.checked, radioB);
    console.log('After A click - A checked:', aChecked, 'B checked:', bChecked);
    
    console.log('Clicking Option B');
    await radioB.click();
    await new Promise(r => setTimeout(r, 100));
    
    aChecked = await page.evaluate(el => el.checked, radioA);
    bChecked = await page.evaluate(el => el.checked, radioB);
    console.log('After B click - A checked:', aChecked, 'B checked:', bChecked);
    
    server.close();
    await browser.close();
})();
