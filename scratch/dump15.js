const fs = require('fs');
const path = require('path');
const os = require('os');

function getBrainHistory() {
    const brainDir = path.join(os.homedir(), '.gemini', 'antigravity', 'brain');
    if (!fs.existsSync(brainDir)) return [];
    
    let folders;
    try {
        folders = fs.readdirSync(brainDir).filter(f => f.length === 36);
    } catch(e) { return []; }
    
    const chats = [];
    
    for (const folder of folders) {
        const transcriptFile = path.join(brainDir, folder, '.system_generated', 'logs', 'transcript_full.jsonl');
        if (!fs.existsSync(transcriptFile)) continue;
        
        try {
            const fd = fs.openSync(transcriptFile, 'r');
            const buffer = Buffer.alloc(4096);
            fs.readSync(fd, buffer, 0, 4096, 0);
            fs.closeSync(fd);
            
            const content = buffer.toString('utf-8');
            const firstLine = content.split('\n')[0];
            const json = JSON.parse(firstLine);
            
            let title = "New Chat";
            if (json.content) {
                const reqMatch = json.content.match(/<USER_REQUEST>([\s\S]*?)<\/USER_REQUEST>/);
                const reqText = reqMatch ? reqMatch[1].trim() : json.content;
                
                // Exclude known subagent prompts
                if (reqText.includes('You are the Architecture Proponent') || 
                    reqText.includes('You are the Critic in a technical debate') ||
                    reqText.includes('Review the implementation plan') ||
                    reqText.includes('Review the newly added') ||
                    reqText.includes('Review the new') ||
                    reqText.includes('Please query the') ||
                    reqText.includes('You are the Language-Specific Style Expert') ||
                    reqText.includes('You are the Security Auditor')) {
                    continue; // Skip subagents
                }
                
                title = reqText.split('\n')[0].substring(0, 40).replace(/[^a-zA-Z0-9 -_?]/g, '');
            }
            
            chats.push({
                id: folder,
                title: title,
                workspace: 'Global',
                date: json.created_at || 'Unknown',
                isPinned: false
            });
        } catch(e) {}
    }
    
    chats.sort((a,b) => new Date(b.date) - new Date(a.date));
    return chats;
}

const c = getBrainHistory();
console.log(`Found ${c.length} valid user chats`);
console.log(c.slice(0, 10));
