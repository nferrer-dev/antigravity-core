const http = require('http');
const WebSocket = require('ws'); // server.js uses ws
const fs = require('fs');

http.get('http://localhost:9222/json/version', (res) => {
    let data = '';
    res.on('data', chunk => data += chunk);
    res.on('end', () => {
        const info = JSON.parse(data);
        const wsUrl = info.webSocketDebuggerUrl;
        
        const ws = new WebSocket(wsUrl);
        let id = 1;
        const callbacks = {};
        
        ws.on('message', (msg) => {
            const res = JSON.parse(msg);
            if (callbacks[res.id]) {
                callbacks[res.id](res.result || res.error);
                delete callbacks[res.id];
            }
        });
        
        function call(method, params = {}) {
            return new Promise((resolve) => {
                const reqId = id++;
                callbacks[reqId] = resolve;
                ws.send(JSON.stringify({ id: reqId, method, params }));
            });
        }
        
        ws.on('open', async () => {
            const targets = await call('Target.getTargets');
            const page = targets.targetInfos.find(t => t.type === 'page' && (t.url.includes('localhost') || t.url.includes('127.0.0.1') || t.url.includes('file://')));
            
            if (!page) {
                console.log('No page');
                process.exit(1);
            }
            
            const sessionRes = await call('Target.attachToTarget', { targetId: page.targetId, flatten: true });
            const sessionId = sessionRes.sessionId;
            
            function callSession(method, params) {
                return new Promise((resolve) => {
                    const reqId = id++;
                    callbacks[reqId] = resolve;
                    ws.send(JSON.stringify({ id: reqId, sessionId, method, params }));
                });
            }
            
            await callSession('Runtime.enable');
            
            const exp = `(async () => {
                const btn = document.querySelector('button[aria-label^="Select model"]');
                if (btn) btn.click();
                return !!btn;
            })()`;
            
            const clickRes = await callSession('Runtime.evaluate', { expression: exp, awaitPromise: true });
            console.log('Clicked?', clickRes);
            
            setTimeout(async () => {
                const docRes = await callSession('Runtime.evaluate', { expression: 'document.documentElement.outerHTML' });
                fs.writeFileSync('C:/Projects/antigravity-core/scratch/dump.html', docRes.result.value);
                console.log('Dumped to scratch/dump.html');
                process.exit(0);
            }, 1000);
        });
    });
});
