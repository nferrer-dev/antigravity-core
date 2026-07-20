const puppeteer = require('puppeteer');

(async () => {
    const browser = await puppeteer.launch({ args: ['--no-sandbox', '--disable-setuid-sandbox'] });
    const page = await browser.newPage();
    
    page.on('console', msg => console.log('PAGE:', msg.text()));
    page.on('pageerror', err => console.log('PAGE ERROR:', err.message));
    
    const express = require('express');
    const app = express();
    app.use(express.static('public'));
    const server = app.listen(3015);
    
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
                            <vscode-radio data-stable-id="opt-a" data-ag-id="ag-1" name="q1">Option A</vscode-radio>
                            <vscode-radio data-stable-id="opt-b" data-ag-id="ag-2" name="q1">Option B</vscode-radio>
                        </div>
                    </div>
                </body>
            </html>
        `);
    });

    await page.goto('http://localhost:3015/test');
    
    await page.evaluate(() => {
        window.fetchWithAuth = async (url) => {
            console.log('FETCH CALLED', url);
            return { ok: true, json: async () => ({}) };
        };
    });

    const radioA = (await page.$$('vscode-radio'))[0];
    const radioB = (await page.$$('vscode-radio'))[1];
    
    await page.evaluate(el => el.click(), radioA);
    await new Promise(r => setTimeout(r, 100));
    
    let html = await page.evaluate(() => document.body.innerHTML);
    console.log('HTML after A:', html);
    
    server.close();
    await browser.close();
})();
