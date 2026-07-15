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

            run(`
                const editor = document.querySelector('[contenteditable="true"]');
                editor.focus();
                document.execCommand('insertText', false, 'test');
            `);

            setTimeout(() => {
                const evalId = run(`
                    (() => {
                        const send = document.querySelector('button[aria-label="Send"]') || document.querySelector('svg.lucide-arrow-right')?.closest('button');
                        const voice = document.querySelector('button[aria-label="Record voice memo"]');
                        const cancel = document.querySelector('button[aria-label="Cancel (Ctrl+D)"]');
                        return 'Send: ' + !!send + ', Voice: ' + !!voice + ', Cancel: ' + !!cancel;
                    })()
                `);
                ws.on('message', msg => {
                    const res = JSON.parse(msg);
                    if (res.id === evalId && res.result && res.result.result) {
                        console.log('Buttons when text is present:', res.result.result.value);
                        
                        // Clean up
                        run(`
                            const editor = document.querySelector('[contenteditable="true"]');
                            editor.focus();
                            document.execCommand("selectAll", false, null);
                            document.execCommand("delete", false, null);
                        `);
                        setTimeout(() => ws.close(), 100);
                    }
                });
            }, 500);
        });
    });
});
