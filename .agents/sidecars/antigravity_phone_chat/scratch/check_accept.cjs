const { WebSocket } = require('ws');
const http = require('http');

http.get('http://127.0.0.1:9222/json', (res) => {
    let data = '';
    res.on('data', chunk => data += chunk);
    res.on('end', () => {
        const targets = JSON.parse(data);
        const page = targets.find(t => t.type === 'page');
        const ws = new WebSocket(page.webSocketDebuggerUrl);
        ws.on('open', () => {
            let id = 1;
            ws.send(JSON.stringify({id: id++, method: 'DOM.getDocument', params: {depth: -1}}));
            ws.on('message', msg => {
                const res = JSON.parse(msg);
                if(res.method === 'DOM.setChildNodes' || res.method === 'DOM.documentUpdated') return;
                if (res.id === 1) {
                    ws.send(JSON.stringify({id: id++, method: 'DOM.querySelector', params: {nodeId: res.result.root.nodeId, selector: 'input[type="file"]'}}));
                } else if (res.id === 2) {
                    ws.send(JSON.stringify({id: id++, method: 'DOM.getAttributes', params: {nodeId: res.result.nodeId}}));
                } else if (res.id === 3) {
                    console.log('Attributes:', res.result.attributes);
                    process.exit(0);
                }
            });
        });
    });
});
