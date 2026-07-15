const http = require('http');
const fs = require('fs');

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
                ws.send(JSON.stringify({id, method: 'Runtime.evaluate', params: {expression: expr}}));
                return id;
            };

            // Trigger generation
            run(`
                const editor = document.querySelector('[contenteditable="true"]');
                editor.focus();
                document.execCommand("selectAll", false, null);
                document.execCommand("delete", false, null);
                document.execCommand("insertText", false, "Write an extremely long story about a magic square");
            `);
            
            setTimeout(() => {
                // We use the voice memo button if we can't find Send... wait, we need to submit.
                // You can submit by firing Enter keydown.
                run(`
                    const e = new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true});
                    document.querySelector('[contenteditable="true"]').dispatchEvent(e);
                `);
            }, 500);

            setTimeout(() => {
                const id = msgId++;
                ws.send(JSON.stringify({id, method: 'Page.captureScreenshot', params: {format: 'png'}}));
            }, 2500);
        });

        ws.on('message', msg => {
            const res = JSON.parse(msg);
            if (res.result && res.result.data) {
                fs.writeFileSync('C:/Users/nferr/.gemini/antigravity/brain/eee4402c-9228-44d1-ba6b-366d51379fa5/scratch/generating.png', res.result.data, 'base64');
                console.log('Saved generating.png');
                ws.close();
            }
        });
    });
});
