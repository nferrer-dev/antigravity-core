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
    if(!page) return;
    
    const ws = new WebSocket(page.webSocketDebuggerUrl);
    ws.on('open', () => {
        ws.send(JSON.stringify({
            id: 1,
            method: 'Runtime.evaluate',
            params: {
                expression: `(async () => { 
                    const pills = document.querySelectorAll('span[data-testid^="convo-pill-"]');
                    if (pills.length === 0) return 'No pills'; 
                    pills[pills.length - 1].scrollIntoView();
                    return new Promise(r => setTimeout(() => r(document.querySelectorAll('span[data-testid^="convo-pill-"]').length), 2000)); 
                })()`,
                awaitPromise: true,
                returnByValue: true
            }
        }));
    });
    ws.on('message', m => {
        const data = JSON.parse(m);
        if(data.id===1) {
            console.log(data.result.result.value);
            process.exit(0);
        }
    });
}
run();
