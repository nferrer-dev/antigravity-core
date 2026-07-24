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
                    const pill = document.querySelector('span[data-testid^="convo-pill-"]'); 
                    if (!pill) return 'no pill'; 
                    let p = pill; 
                    let res = []; 
                    while(p && p.tagName !== 'BODY') { 
                        res.push(p.tagName + '#' + p.id + '.' + Array.from(p.classList).join('.')); 
                        p = p.parentElement; 
                    } 
                    
                    const scroller1 = document.querySelector('.overflow-y-auto');
                    const scroller2 = document.querySelector('[data-testid="conversation-history-list"]');
                    return {
                        hierarchy: res,
                        scroller1: scroller1 ? scroller1.tagName + '#' + scroller1.id + '.' + Array.from(scroller1.classList).join('.') : null,
                        scroller2: scroller2 ? scroller2.tagName + '#' + scroller2.id + '.' + Array.from(scroller2.classList).join('.') : null,
                    };
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
