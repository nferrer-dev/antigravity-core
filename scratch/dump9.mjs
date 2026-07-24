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
                    const scroller = document.querySelector('.overflow-y-auto');
                    if (!scroller) return 'No scroller'; 
                    
                    const els = Array.from(scroller.querySelectorAll('*')).map(e => e.tagName + (e.className ? '.' + Array.from(e.classList).join('.') : '') + ' : ' + e.textContent);
                    return els.slice(0, 100);
                })()`,
                awaitPromise: true,
                returnByValue: true
            }
        }));
    });
    ws.on('message', m => {
        const data = JSON.parse(m);
        if(data.id===1) {
            console.log(JSON.stringify(data.result.result.value, null, 2));
            process.exit(0);
        }
    });
}
run();
