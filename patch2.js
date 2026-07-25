const fs = require('fs');
const file = '.agents/sidecars/antigravity_phone_chat/server.js';
let content = fs.readFileSync(file, 'utf8');

const target = \// Main
async function main() {
    try {
        await initCDP();
    } catch (err) {
        console.warn(\\\??  Initial CDP discovery failed: \\\\\\);
        console.log('?? Start Antigravity with --remote-debugging-port=9000 to connect.');
    }

    try {
        const { server, wss, app, hasSSL } = await createServer();

        // Start background polling (it will now handle reconnections)
        startPolling(wss);\;

const replacement = \// Main
async function main() {
    const isSafeMode = (process.env.APP_PASSWORD || 'antigravity') === 'antigravity' || (process.env.SESSION_SECRET === 'antigravity_secret_key_1337');
    if (!isSafeMode) {
        try {
            await initCDP();
        } catch (err) {
            console.warn(\\\??  Initial CDP discovery failed: \\\\\\);
            console.log('?? Start Antigravity with --remote-debugging-port=9000 to connect.');
        }
    }

    try {
        const { server, wss, app, hasSSL } = await createServer();

        if (wss) {
            // Start background polling (it will now handle reconnections)
            startPolling(wss);
        }\;

// normalize rn to n for both target and content to match
let nTarget = target.replace(/\r\n/g, '\n');
let nContent = content.replace(/\r\n/g, '\n');
nContent = nContent.replace(nTarget, replacement);
fs.writeFileSync(file, nContent);
console.log('Patched main successfully.');

