const puppeteer = require('puppeteer');

(async () => {
    const browser = await puppeteer.launch({ headless: 'new' });
    const page = await browser.newPage();
    
    // Capture console output from the browser
    page.on('console', msg => console.log('PAGE LOG:', msg.text()));

    console.log('Victim first visits http://127.0.0.1:3001 (Legit App) to get their cookie...');
    await page.goto('http://127.0.0.1:3001', { waitUntil: 'networkidle0' });
    await new Promise(r => setTimeout(r, 1000));
    
    console.log('Victim is visiting http://localhost:4001 (Cross-Site Attacker Site)...');
    await page.goto('http://localhost:4001', { waitUntil: 'networkidle0' });
    
    await new Promise(r => setTimeout(r, 2000));
    await browser.close();
})();
