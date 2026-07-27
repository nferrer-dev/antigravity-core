const { WebSocketServer } = require('ws');
const net = require('net');

async function runPoC() {
    const wss = new WebSocketServer({ port: 8081 });
    
    wss.on('connection', (ws) => {
        // No ping/pong implemented, exactly like server.js
        ws.on('close', () => {
            console.log('Server saw connection close');
        });
    });

    console.log('Server listening on 8081');
    
    // Simulate mobile client abrupt disconnects
    // By connecting via raw TCP and then destroying the socket without a proper close handshake.
    
    for (let i = 0; i < 5; i++) {
        const client = new net.Socket();
        client.connect(8081, '127.0.0.1', () => {
            // Send standard HTTP Upgrade request to establish WebSocket
            client.write(
                "GET / HTTP/1.1\r\n" +
                "Host: 127.0.0.1:8081\r\n" +
                "Upgrade: websocket\r\n" +
                "Connection: Upgrade\r\n" +
                "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n" +
                "Sec-WebSocket-Version: 13\r\n" +
                "\r\n"
            );
            
            setTimeout(() => {
                // Abruptly destroy the TCP connection without sending a WS close frame or FIN packet properly
                // This simulates a mobile client dropping off the network or battery dying
                client.destroy();
                console.log(`Simulated abrupt disconnect for client ${i+1}`);
            }, 100);
        });
    }

    // Wait a bit to see if wss.clients cleans up
    setTimeout(() => {
        console.log(`Active clients in wss.clients: ${wss.clients.size}`);
        if (wss.clients.size > 0) {
            console.log("LEAK CONFIRMED: Ghost connections remain in wss.clients");
        } else {
            console.log("NO LEAK: TCP stack handled the disconnect");
        }
        process.exit(0);
    }, 2000);
}

runPoC();
