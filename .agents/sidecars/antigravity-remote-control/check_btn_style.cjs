const http = require('http');

http.get('http://127.0.0.1:63798/json', res => {
    let d = ''; res.on('data', c => d+=c); res.on('end', () => {
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

            const evalId = run(`
                (() => {
                    const btn = document.querySelector('button[aria-label="Cancel (Ctrl+D)"]');
                    if (!btn) return 'not found';
                    const rect = btn.getBoundingClientRect();
                    return {
                        width: rect.width,
                        height: rect.height,
                        display: getComputedStyle(btn).display,
                        visibility: getComputedStyle(btn).visibility,
                        opacity: getComputedStyle(btn).opacity,
                        parentDisplay: getComputedStyle(btn.parentElement).display,
                        parentRectWidth: btn.parentElement.getBoundingClientRect().width
                    };
                })()
            `);

            ws.on('message', msg => {
                const res = JSON.parse(msg);
                if (res.id === evalId && res.result && res.result.result) {
                    console.log('Cancel btn style:', res.result.result.value);
                    ws.close();
                }
            });
        });
    });
});
