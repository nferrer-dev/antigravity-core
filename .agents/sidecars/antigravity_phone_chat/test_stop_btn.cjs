const http = require('http');

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
            
            // Function to run an expression
            const run = (expr) => {
                const id = msgId++;
                ws.send(JSON.stringify({id, method: 'Runtime.evaluate', params: {expression: expr, returnByValue: true}}));
                return id;
            };

            // 1. Send a message to start generating
            const script = `
                const editor = document.querySelector('[contenteditable="true"]');
                editor.focus();
                document.execCommand("insertText", false, "Write a long story");
                setTimeout(() => {
                    document.querySelector("svg.lucide-arrow-right").closest("button").click();
                }, 500);
            `;
            run(script);

            // 2. Poll for stop button status
            let checks = 0;
            const interval = setInterval(() => {
                checks++;
                if (checks > 10) {
                    clearInterval(interval);
                    ws.close();
                    return;
                }
                run(`
                    (() => {
                        const btn = document.querySelector('button svg.lucide-square')?.closest('button');
                        if (!btn) return "NOT_FOUND";
                        return "FOUND. offsetParent: " + (btn.offsetParent ? btn.offsetParent.tagName : "NULL");
                    })();
                `);
            }, 1000);
        });

        ws.on('message', msg => {
            const res = JSON.parse(msg);
            if (res.result && res.result.result) {
                console.log('Result:', res.result.result.value);
            }
        });
    });
});
