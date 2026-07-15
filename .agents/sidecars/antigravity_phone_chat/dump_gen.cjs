const http = require('http');
const fs = require('fs');

http.get('http://127.0.0.1:63798/json', res => {
    let d = '';
    res.on('data', c => d += c);
    res.on('end', async () => {
        const pages = JSON.parse(d);
        const wsUrl = pages[0].webSocketDebuggerUrl;
        const WebSocket = require('ws');
        const ws = new WebSocket(wsUrl);

        ws.on('open', () => {
            let msgId = 1;
            
            const run = (expr) => {
                const id = msgId++;
                ws.send(JSON.stringify({id, method: 'Runtime.evaluate', params: {expression: expr, returnByValue: true}}));
                return id;
            };

            const script = `
                const submit = document.querySelector('svg.lucide-arrow-right')?.closest('button') || document.querySelector("button[aria-label='Send']");
                if (submit) submit.click();
            `;
            run(script);

            setTimeout(() => {
                run('document.body.innerHTML');
            }, 2500);
        });

        ws.on('message', msg => {
            const res = JSON.parse(msg);
            if (res.result && res.result.result && typeof res.result.result.value === 'string' && res.result.result.value.includes('<div')) {
                fs.writeFileSync('dom_generating.html', res.result.result.value);
                console.log('Saved dom_generating.html');
                ws.close();
            }
        });
    });
});
