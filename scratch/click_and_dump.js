const puppeteer = require('puppeteer');

(async () => {
    try {
        const response = await fetch('http://localhost:9222/json/version');
        const data = await response.json();
        const browser = await puppeteer.connect({ browserWSEndpoint: data.webSocketDebuggerUrl });
        const pages = await browser.pages();
        const page = pages.find(p => p.url().includes('localhost') || p.url().includes('127.0.0.1') || p.url().includes('file://'));
        
        if (!page) {
            console.log('Page not found');
            process.exit(1);
        }

        await page.evaluate(() => {
            const btn = document.querySelector('button[aria-label^="Select model"]');
            if (btn) btn.click();
        });
        
        await new Promise(r => setTimeout(r, 1000));
        
        const html = await page.evaluate(() => document.body.innerHTML);
        const fs = require('fs');
        fs.writeFileSync('dump_after_click.html', html);
        console.log('Dumped');
        process.exit(0);
    } catch(e) {
        console.error(e);
        process.exit(1);
    }
})();
