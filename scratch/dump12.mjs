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
    
    const send = (method, params) => new Promise(resolve => {
        const id = Math.floor(Math.random() * 1000000);
        const listener = m => {
            const data = JSON.parse(m);
            if(data.id === id) {
                ws.removeListener('message', listener);
                resolve(data.result);
            }
        };
        ws.on('message', listener);
        ws.send(JSON.stringify({ id, method, params }));
    });

    ws.on('open', async () => {
        const getPills = () => send('Runtime.evaluate', {
            expression: `Array.from(document.querySelectorAll('span[data-testid^="convo-pill-"]')).map(el => el.textContent).filter(t => t.length > 2)`,
            returnByValue: true
        });

        const before = await getPills();
        console.log("First pill before:", before.result.value[0]);
        console.log("Last pill before:", before.result.value[before.result.value.length - 1]);
        
        // Find scroller position
        const rectRes = await send('Runtime.evaluate', {
            expression: `(() => { const el = document.querySelector('.overflow-y-auto'); const rect = el.getBoundingClientRect(); return {x: rect.x + rect.width/2, y: rect.y + rect.height/2}; })()`,
            returnByValue: true
        });
        
        const {x, y} = rectRes.result.value;
        
        // Dispatch scroll
        await send('Input.synthesizeScrollGesture', {
            x, y,
            xDistance: 0,
            yDistance: -1000,
            yOverscroll: 0,
            preventFling: false,
            speed: 800,
            repeatCount: 10,
            repeatDelayMs: 200,
            interactionMarkerName: 'scroll'
        });
        
        await new Promise(r => setTimeout(r, 2000));
        
        const after = await getPills();
        console.log("First pill after:", after.result.value[0]);
        console.log("Last pill after:", after.result.value[after.result.value.length - 1]);
        
        process.exit(0);
    });
}
run();
