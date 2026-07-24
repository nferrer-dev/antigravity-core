import WebSocket from 'ws';
import fs from 'fs';

async function run() {
    const PORTS = [7800, 9000, 9001, 9002, 9003, 63798];
    let page = null;
    for (const port of PORTS) {
        try {
            const res = await fetch(`http://127.0.0.1:${port}/json`);
            const targets = await res.json();
            page = targets.find(t => t.type === 'page');
            if (page) break;
        } catch(e) {}
    }
    if(!page) return;
    
    const ws = new WebSocket(page.webSocketDebuggerUrl);
    ws.on('open', () => {
        ws.send(JSON.stringify({
            id: 1,
            method: 'Runtime.evaluate',
            params: {
                expression: `(async () => { 
                    const scroller = document.querySelector('.overflow-y-auto') || document.querySelector('[data-testid="conversation-history-list"]');
                    if (!scroller) return 'No scroller'; 
                    return scroller.outerHTML;
                })()`,
                awaitPromise: true,
                returnByValue: true
            }
        }));
    });
    ws.on('message', m => {
        const data = JSON.parse(m);
        if(data.id===1) {
            fs.writeFileSync('c:\\Projects\\antigravity-core\\scratch\\sidebar_dom.html', data.result.result.value);
            console.log("DOM written to sidebar_dom.html");
            process.exit(0);
        }
    });
}
run();
