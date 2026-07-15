const puppeteer = require('puppeteer-core');
(async () => {
    try {
        const browser = await puppeteer.connect({ browserURL: 'http://127.0.0.1:9222' });
        const pages = await browser.pages();
        const page = pages.find(p => p.url().includes('localhost') || p.url().includes('127.0.0.1'));
        if (!page) { console.log('No page'); process.exit(1); }
        const queuedHtml = await page.evaluate(() => {
            const el = Array.from(document.querySelectorAll('div')).find(el => el.innerText && el.innerText.includes('Queued'));
            if (el) return el.outerHTML;
            return 'Not found';
        });
        console.log(queuedHtml);
        browser.disconnect();
    } catch (e) { console.log(e); }
})();
