const express = require('express');
const { WebSocketServer } = require('ws');
const cookieParser = require('cookie-parser');
const http = require('http');

const app = express();
const server = http.createServer(app);
const wss = new WebSocketServer({ server });

function isLocalRequest(req) {
    const ip = req.ip || req.socket.remoteAddress || '';
    return ip === '127.0.0.1' || ip === '::1' || ip === '::ffff:127.0.0.1';
}

app.use(cookieParser('secret'));

// Simulated HTTP middleware
app.use((req, res, next) => {
    if (isLocalRequest(req)) {
        // Automatically grant a signed cookie to local users so they can use WebSockets securely
        if (!req.signedCookies['auth']) {
            res.cookie('auth', 'token', {
                httpOnly: true,
                signed: true,
                maxAge: 30 * 24 * 60 * 60 * 1000,
                // sameSite defaults to 'Lax' in modern browsers
            });
        }
        return next();
    }
    const token = req.signedCookies['auth'];
    if (token === 'token') return next();
    res.status(401).send('Unauthorized');
});

app.get('/', (req, res) => {
    res.send('<h1>Legit App</h1><script>new WebSocket("ws://127.0.0.1:3001").onopen = () => console.log("WS Connected");</script>');
});

wss.on('connection', (ws, req) => {
    const rawCookies = req.headers.cookie || '';
    const parsedCookies = {};
    rawCookies.split(';').forEach(c => {
        const [k, v] = c.trim().split('=');
        if (k && v) parsedCookies[k] = decodeURIComponent(v);
    });

    let isAuthenticated = false;
    const signedToken = parsedCookies['auth'];

    // isLocalRequest bypass removed from WebSockets!
    if (signedToken) {
        const token = cookieParser.signedCookie(signedToken, 'secret');
        if (token === 'token') isAuthenticated = true;
    }

    if (!isAuthenticated) {
        ws.send(JSON.stringify({ type: 'error', message: 'Unauthorized' }));
        ws.close();
        return;
    }

    console.log('Client connected (Authenticated) from', req.socket.remoteAddress);
    ws.send('Welcome authenticated user!');
    
    ws.on('message', (msg) => {
        console.log('Received:', msg.toString());
        ws.send('Echo: ' + msg.toString());
    });
});

server.listen(3001, () => console.log('Secure Server running on port 3001'));
