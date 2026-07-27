const { WebSocketServer, WebSocket } = require('ws');
const net = require('net');

async function runPoC() {
    // 1. Start actual WS server
    const wss = new WebSocketServer({ port: 8081 });
    wss.on('connection', (ws) => {
        ws.on('close', () => console.log('WS connection closed properly'));
    });

    // 2. Start TCP Proxy that simulates silent drops
    const proxy = net.createServer((clientSocket) => {
        const serverSocket = new net.Socket();
        serverSocket.connect(8081, '127.0.0.1', () => {
            // Forward traffic both ways initially
            clientSocket.pipe(serverSocket);
            serverSocket.pipe(clientSocket);
            
            // After 100ms, simulate a network drop (like mobile phone losing service).
            // We just destroy the client socket (so the local client process exits),
            // BUT we explicitly leave the serverSocket open to simulate the server not receiving a TCP FIN/RST packet.
            setTimeout(() => {
                clientSocket.unpipe(serverSocket);
                serverSocket.unpipe(clientSocket);
                clientSocket.destroy(); 
                console.log('Simulated network blackhole: client disconnected, but server connection remains zombie.');
            }, 100);
        });
    });
    proxy.listen(8082, '127.0.0.1');

    console.log('Servers started');

    // 3. Client connects through proxy
    for (let i = 0; i < 5; i++) {
        const ws = new WebSocket('ws://127.0.0.1:8082');
    }

    // 4. Verify leak
    setTimeout(() => {
        console.log(`Active clients in wss.clients: ${wss.clients.size}`);
        if (wss.clients.size === 5) {
            console.log("LEAK CONFIRMED: 5 Ghost connections remain in wss.clients because the TCP connection didn't signal close and there is no ping/pong.");
            process.exit(1);
        } else {
            console.log("NO LEAK");
            process.exit(0);
        }
    }, 1500);
}

runPoC();
