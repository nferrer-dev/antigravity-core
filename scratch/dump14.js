const fs = require('fs');
const path = require('path');
const os = require('os');

const brainDir = path.join(os.homedir(), '.gemini', 'antigravity', 'brain');
const folders = fs.readdirSync(brainDir).filter(f => fs.statSync(path.join(brainDir, f)).isDirectory());

const chats = [];

for (const folder of folders) {
    if (folder.length !== 36) continue; // UUID
    const transcriptFile = path.join(brainDir, folder, '.system_generated', 'logs', 'transcript.jsonl');
    if (!fs.existsSync(transcriptFile)) continue;
    
    try {
        const fd = fs.openSync(transcriptFile, 'r');
        const buffer = Buffer.alloc(2048);
        fs.readSync(fd, buffer, 0, 2048, 0);
        fs.closeSync(fd);
        
        const content = buffer.toString('utf-8');
        const firstLine = content.split('\n')[0];
        const json = JSON.parse(firstLine);
        
        let title = "New Chat";
        if (json.content) {
            const reqMatch = json.content.match(/<USER_REQUEST>([\s\S]*?)<\/USER_REQUEST>/);
            if (reqMatch) {
                title = reqMatch[1].trim().split('\n')[0].substring(0, 50);
            } else {
                title = json.content.substring(0, 50);
            }
        }
        
        chats.push({
            id: folder,
            title: title.replace(/[^a-zA-Z0-9 -_]/g, ''),
            workspace: 'Global', // Assuming global for now, could check workspaceUris if we parse the second line?
            date: json.created_at || 'Unknown'
        });
    } catch(e) {}
}

chats.sort((a,b) => new Date(b.date) - new Date(a.date));
console.log(`Found ${chats.length} chats`);
console.log(chats.slice(0, 10));
