import WebSocket from 'ws';

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
    if(!page) { console.log("no page"); return; }
    
    const ws = new WebSocket(page.webSocketDebuggerUrl);
    ws.on('open', () => {
        ws.send(JSON.stringify({
            id: 1,
            method: 'Runtime.evaluate',
            params: {
                expression: `(async () => { 
                    const buttons = Array.from(document.querySelectorAll('button'));
                    const loadMore = buttons.find(b => b.textContent && b.textContent.toLowerCase().includes('more'));
                    if (loadMore) {
                        return 'Found button: ' + loadMore.textContent;
                    }
                    
                    const texts = Array.from(document.querySelectorAll('*')).filter(el => el.children.length === 0 && el.textContent && el.textContent.toLowerCase().includes('more'));
                    return { texts: texts.map(t => t.textContent) };
                })()`,
                awaitPromise: true,
                returnByValue: true
            }
        }));
    });
    ws.on('message', (msg) => {
        const data = JSON.parse(msg);
        if(data.id === 1) {
            console.log(JSON.stringify(data.result.result.value, null, 2));
            process.exit(0);
        }
    });
}
run();
