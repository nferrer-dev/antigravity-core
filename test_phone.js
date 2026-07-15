const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  page.on('console', msg => console.log('BROWSER:', msg.text()));

  await page.goto('http://127.0.0.1:3000/');
  
  // Wait for the chat to load
  await page.waitForTimeout(2000);
  
  // Find all thumbs up buttons
  const goodBtns = await page.$$('button[aria-label="Good response"]');
  console.log('Found', goodBtns.length, 'thumbs up buttons');
  
  if (goodBtns.length > 0) {
    // Click the last one
    await goodBtns[goodBtns.length - 1].click();
    console.log('Clicked the last thumbs up button');
    
    // Check if it has active-thumb class
    let hasClass = await goodBtns[goodBtns.length - 1].evaluate(b => b.classList.contains('active-thumb'));
    console.log('Has active-thumb class?', hasClass);
    
    // Send a message
    await page.fill('textarea', 'Test from playwright');
    await page.keyboard.press('Enter');
    console.log('Sent message');
    
    // Wait for snapshot to reload a few times
    await page.waitForTimeout(3000);
    
    // Check if the same button still has active-thumb class
    // We need to re-query the DOM
    const newGoodBtns = await page.$$('button[aria-label="Good response"]');
    console.log('Now found', newGoodBtns.length, 'thumbs up buttons');
    
    if (newGoodBtns.length >= goodBtns.length) {
       hasClass = await newGoodBtns[goodBtns.length - 1].evaluate(b => b.classList.contains('active-thumb'));
       console.log('Previous button still has active-thumb class?', hasClass);
       
       const cdpStyles = await page.$eval('#cdp-styles', el => el.textContent).catch(() => 'NOT FOUND');
       console.log('Is CSS still present?', cdpStyles.includes('button.active-thumb'));
    }
  }

  await browser.close();
})();
