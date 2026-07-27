const fs = require('fs');
const file = '.agents/sidecars/antigravity_phone_chat/public/js/app_v8.js';
let content = fs.readFileSync(file, 'utf8');
const target = 'function connectWebSocket() {';
const replacement = 'async function connectWebSocket() {' + '\n' +
    '    try {' + '\n' +
    '            return;' + '\n' +
    '        } else if (res.status === 401 || res.status === 403) {' + '\n' +
    '            return;' + '\n' +
    '        }' + '\n' +
    '    } catch(e) {' + '\n' +
    '}';
content = content.replace(target, replacement);
fs.writeFileSync(file, content);
console.log('Patched app_v8.js');