const http = require('http');
http.get('http://127.0.0.1:63798/json', res => {
    let d = ''; res.on('data', c => d+=c); res.on('end', () => {
        const wsUrl = JSON.parse(d)[0].webSocketDebuggerUrl;
        const WebSocket = require('ws');
        const ws = new WebSocket(wsUrl);
        ws.on('open', () => {
            ws.send(JSON.stringify({id: 1, method: 'Runtime.evaluate', params: {
                expression: '(() => { const b = document.querySelector("button[aria-label=\'Cancel (Ctrl+D)\']"); if (!b) return null; let cur = b; let display = "visible"; while(cur) { const s = getComputedStyle(cur); if (s.display === "none" || s.opacity === "0" || s.visibility === "hidden" || s.width === "0px" || s.height === "0px") { display = "hidden by " + cur.className + " (" + s.display + ", " + s.width + ", " + s.opacity + ")"; break; } cur = cur.parentElement; } return display; })()', 
                returnByValue: true
            }}));
        });
        ws.on('message', m => { console.log(m.toString()); ws.close(); });
    });
});
