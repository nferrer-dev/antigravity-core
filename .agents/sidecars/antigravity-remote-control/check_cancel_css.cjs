const http = require('http');
http.get('http://127.0.0.1:63798/json', res => {
    let d = ''; res.on('data', c => d+=c); res.on('end', () => {
        const wsUrl = JSON.parse(d)[0].webSocketDebuggerUrl;
        const WebSocket = require('ws');
        const ws = new WebSocket(wsUrl);
        ws.on('open', () => {
            ws.send(JSON.stringify({id: 1, method: 'Runtime.evaluate', params: {
                expression: '(() => { const b = document.querySelector("button[aria-label=\'Cancel (Ctrl+D)\']"); return b ? {exists: true, opacity: getComputedStyle(b).opacity, visibility: getComputedStyle(b).visibility, pointerEvents: getComputedStyle(b).pointerEvents, width: getComputedStyle(b).width, height: getComputedStyle(b).height, position: getComputedStyle(b).position, zIndex: getComputedStyle(b).zIndex, class: b.className, parentClass: b.parentElement.className} : null; })()', 
                returnByValue: true
            }}));
        });
        ws.on('message', m => { console.log(m.toString()); ws.close(); });
    });
});
