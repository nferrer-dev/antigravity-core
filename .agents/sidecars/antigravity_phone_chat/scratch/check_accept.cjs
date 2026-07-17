const { WebSocket } = require('ws');
const http = require('http');

http.get('http://127.0.0.1:9000/json', (res) => {
    let data = '';
    res.on('data', chunk => data += chunk);
    res.on('end', () => {
        const targets = JSON.parse(data);
        const page = targets.find(t => t.type === 'page');
        const ws = new WebSocket(page.webSocketDebuggerUrl);
        ws.on('open', () => {
            let id = 1;
            ws.send(JSON.stringify({
                id: id++, 
                method: 'Runtime.evaluate', 
                params: {
                    expression: `Array.from(document.querySelectorAll('button')).filter(b => (b.getAttribute('aria-label')||'').toLowerCase().includes('revert') || (b.getAttribute('aria-label')||'').toLowerCase().includes('undo') || b.getAttribute('data-testid') === 'revert-button').map(b => b.outerHTML)`,
                    returnByValue: true
                }
            }));
            ws.on('message', msg => {
                const res = JSON.parse(msg);
                if (res.id === 1) {
                    console.log('Buttons:', res.result.result.value);
                    process.exit(0);
                }
            });
        });
    });
});
