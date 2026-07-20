import puppeteer from 'puppeteer';
import { spawn } from 'child_process';
import { jest } from '@jest/globals';

jest.setTimeout(30000);

let serverProcess;
let browser;
let page;
const PORT = 3001;

beforeAll(async () => {
    serverProcess = spawn('node', ['server.js'], {
        env: { ...process.env, PORT: PORT }
    });

    await new Promise(resolve => setTimeout(resolve, 10000));

    browser = await puppeteer.launch({
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
});

afterAll(async () => {
    if (browser) await browser.close();
    if (serverProcess) {
        serverProcess.kill();
    }
});

beforeEach(async () => {
    page = await browser.newPage();
    page.on('dialog', async dialog => {
        console.log('DIALOG:', dialog.message());
        await dialog.dismiss();
    });
    const client = await page.target().createCDPSession();
    await client.send('Network.enable');
    await client.send('Network.emulateNetworkConditions', {
        offline: false,
        latency: 200,
        downloadThroughput: 500 * 1024 / 8,
        uploadThroughput: 500 * 1024 / 8
    });
    await client.send('Emulation.setCPUThrottlingRate', { rate: 4 });

    console.log('Navigating to server');
    await page.goto(`http://localhost:${PORT}/`, { waitUntil: 'domcontentloaded' });
    console.log('Navigation complete');
});

afterEach(async () => {
    await page.close();
});

test('Test 1 (Double Tap): Rapidly click a radio option 50 times in 100ms. Assert fetchWithAuth is only called ONCE', async () => {
    let fetchCount = 0;
    
    page.on('console', msg => console.log('PAGE:', msg.text()));
    
    await page.setRequestInterception(true);
    page.on('request', async request => {
        if (request.url().includes('/send')) {
            console.log('SEND REQUEST BODY:', request.postData());
            fetchCount++;
            // Stall the request to simulate network latency, keeping the optimistic lock active
            setTimeout(() => {
                request.continue();
            }, 2000);
        } else {
            request.continue();
        }
    });

    await page.evaluate(() => {
        window.alert = (msg) => console.log('ALERT:', msg);
        const div = document.createElement('div');
        div.innerHTML = `<vscode-radio data-ag-id="test-radio" name="test-group">Radio</vscode-radio>`;
        document.getElementById('chatContainer').appendChild(div);
    });

    console.log('getting handle');
    const radioHandle = await page.$('vscode-radio');
    console.log('got handle', !!radioHandle);
    for (let i = 0; i < 50; i++) {
        await radioHandle.click();
        await new Promise(r => setTimeout(r, 2));
    }
    console.log('finished clicking');

    await new Promise(r => setTimeout(r, 1000));

    console.log('checking assertions');
    expect(fetchCount).toBe(1);
}, 30000);

test('Test 2 (Tactile Feedback): Measure the exact millisecond time between a touchstart dispatch and the classList.add(\'selected\') mutation. Assert it is < 50ms', async () => {
    await page.evaluate(() => {
        const div = document.createElement('div');
        div.innerHTML = `<vscode-radio data-ag-id="test-radio2" name="test-group" id="tactile">Radio</vscode-radio>`;
        document.getElementById('chatContainer').appendChild(div);
        window._test2StartTime = performance.now();
    });

    const radioHandle = await page.$('#tactile');
    await radioHandle.evaluate(el => el.scrollIntoView());
    const box = await radioHandle.boundingBox();
    const x = box.x + box.width / 2;
    const y = box.y + box.height / 2;
    
    const resultPromise = page.evaluate(() => {
        return new Promise((resolve) => {
            const el = document.getElementById('tactile');
            if (el.classList.contains('selected') || el.classList.contains('instant-active')) {
                return resolve(0);
            }
            window._test2StartTime = performance.now();
            const observer = new MutationObserver((mutations) => {
                for (let mut of mutations) {
                    if (mut.type === 'attributes' && mut.attributeName === 'class') {
                        if (el.classList.contains('selected') || el.classList.contains('instant-active')) {
                            observer.disconnect();
                            resolve(performance.now() - window._test2StartTime);
                        }
                    }
                }
            });
            observer.observe(el, { attributes: true });
            
            setTimeout(() => {
                observer.disconnect();
                resolve(9999);
            }, 1000);
        });
    });

    await page.touchscreen.touchStart(x, y);
    const result = await resultPromise;
    expect(result).toBeLessThan(50);
}, 30000);

test('Test 3: Race condition between type_text and click_element', async () => {
    let requests = [];
    
    // Clear previous handlers if any, but since it's a new page we're good
    await page.setRequestInterception(true);
    page.on('request', async request => {
        if (request.url().includes('/send')) {
            try {
                const body = JSON.parse(request.postData());
                requests.push(body.action);
                // Delay to exacerbate race conditions
                setTimeout(() => request.continue(), 100);
            } catch (e) {
                request.continue();
            }
        } else {
            request.continue();
        }
    });

    await page.evaluate(() => {
        const div = document.createElement('div');
        div.innerHTML = `
            <vscode-text-field data-ag-id="test-input" id="test-input">Input</vscode-text-field>
            <vscode-button data-ag-id="test-submit" id="test-submit">Submit</vscode-button>
        `;
        document.getElementById('chatContainer').appendChild(div);
    });

    page.on('console', msg => console.log('PAGE:', msg.text()));

    await page.evaluate(() => {
        console.log('Test evaluate started');
        const input = document.getElementById('test-input');
        input.value = 'hello world';
        input.dispatchEvent(new Event('input', { bubbles: true }));
        
        const submit = document.getElementById('test-submit');
        submit.click();
        console.log('Submit clicked');
    });

    await new Promise(r => setTimeout(r, 3000));

    console.log('Final requests:', requests);
    expect(requests).toEqual(['type_text', 'click_element']);
}, 30000);
