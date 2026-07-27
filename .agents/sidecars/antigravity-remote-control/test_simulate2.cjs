const WebSocket = require('ws'); 
async function getCDPWebSocketDebuggerUrl() {
    const res = await fetch('http://localhost:63798/json');
    const targets = await res.json();
    const page = targets.find(t => t.type === 'page');
    return page.webSocketDebuggerUrl;
}

(async () => {
    try {
        const wsUrl = await getCDPWebSocketDebuggerUrl();
        const ws = new WebSocket(wsUrl);
        
        ws.on('open', async () => {
            let id = 1;
            const send = (method, params) => {
                return new Promise(resolve => {
                    const currentId = id++;
                    const listener = (msg) => {
                        const data = JSON.parse(msg);
                        if (data.id === currentId) {
                            ws.removeListener('message', listener);
                            resolve(data.result);
                        }
                    };
                    ws.on('message', listener);
                    ws.send(JSON.stringify({ id: currentId, method, params }));
                });
            };

            await send('Runtime.evaluate', {
                expression: `
                    var ta = document.querySelector('textarea');
                    var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                    nativeInputValueSetter.call(ta, 'Pending Msg');
                    ta.dispatchEvent(new Event('input', { bubbles: true}));
                    document.querySelector('button[aria-label="Send Message"]').click();
                `
            });
            
            await new Promise(r => setTimeout(r, 100)); // wait for DOM update
            const res = await fetch('http://localhost:3000/snapshot'); 
            const data = await res.json(); 
            require('fs').writeFileSync('simulated_pending.html', data.html); 
            console.log("Success");
            process.exit(0);
        });
    } catch(e) {
        console.error(e);
        process.exit(1);
    }
})();
