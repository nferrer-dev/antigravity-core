const { spawn, execSync } = require('child_process');
const path = require('path');

function isServerRunning() {
    try {
        const result = execSync('tasklist /FI "IMAGENAME eq node.exe" /FO CSV /NH', { encoding: 'utf8' });
        // It returns a list of node.exe processes, but we can't easily tell which one is server.js
        // A better way is to try to connect to port 3000
        return false;
    } catch (e) {
        return false;
    }
}

async function checkServer() {
    try {
        const fetch = require('node-fetch');
        const res = await fetch('http://localhost:3000/health');
        return res.ok;
    } catch(e) {
        return false;
    }
}

async function watch() {
    console.log("[Watchdog] Starting...");
    while (true) {
        const running = await checkServer();
        if (!running) {
            console.log("[Watchdog] Server is down. Starting server.js...");
            const child = spawn('node', ['server.js'], {
                cwd: __dirname,
                stdio: 'inherit',
                detached: true
            });
            child.unref();
            console.log("[Watchdog] Server started with PID:", child.pid);
        } else {
            console.log("[Watchdog] Server is running.");
        }
        
        // Wait 30 seconds before checking again
        await new Promise(r => setTimeout(r, 30000));
    }
}

watch();
