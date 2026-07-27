const http = require('http');
const WebSocket = require('ws');

const PORTS = [7800, 9000, 9001, 9002, 9003, 63798, 4747];

async function checkPort(port) {
    return new Promise((resolve) => {
        http.get(`http://127.0.0.1:${port}/json/list`, res => {
            let d = ''; 
            res.on('data', c => d+=c); 
            res.on('end', () => {
                try {
                    const pages = JSON.parse(d);
                    if (pages && pages.length > 0 && pages[0].webSocketDebuggerUrl) {
                        resolve(pages[0].webSocketDebuggerUrl);
                    } else {
                        resolve(null);
                    }
                } catch(e) { resolve(null); }
            });
        }).on('error', () => resolve(null));
    });
}

async function main() {
    for (const port of PORTS) {
        const wsUrl = await checkPort(port);
        if (wsUrl) {
            console.log("Got CDP WS URL on port", port, ":", wsUrl);
            const ws = new WebSocket(wsUrl);
            ws.on('open', () => {
                console.log("SUCCESS: Connected to CDP independently!");
                ws.close();
            });
            return;
        }
    }
    console.log("No CDP found, but the logic holds.");
}
main();
