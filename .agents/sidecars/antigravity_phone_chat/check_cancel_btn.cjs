const http = require('http');
http.get('http://127.0.0.1:63798/json', res => {
    let d = ''; res.on('data', c => d+=c); res.on('end', () => {
        const wsUrl = JSON.parse(d)[0].webSocketDebuggerUrl;
        const WebSocket = require('ws');
        const ws = new WebSocket(wsUrl);
        ws.on('open', () => {
            ws.send(JSON.stringify({id: 1, method: 'Runtime.evaluate', params: {
                expression: 'const btn = document.querySelector("button[aria-label=\'Cancel (Ctrl+D)\']"); btn ? {exists: true, offsetParent: btn.offsetParent !== null, display: getComputedStyle(btn).display} : null', 
                returnByValue: true
            }}));
        });
        ws.on('message', m => { console.log(m.toString()); ws.close(); });
    });
});
