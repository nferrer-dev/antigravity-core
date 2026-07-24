import WebSocket from 'ws';

async function run() {
    const PORTS = [7800, 9000, 9001, 9002, 9003, 63798];
    let page = null;
    for (const port of PORTS) {
        try {
            const res = await fetch(`http://127.0.0.1:${port}/json`);
            const targets = await res.json();
            page = targets.find(t => t.type === 'page');
            if (page) break;
        } catch(e) {}
    }
    if(!page) return;
    
    const ws = new WebSocket(page.webSocketDebuggerUrl);
    ws.on('open', () => {
        ws.send(JSON.stringify({
            id: 1,
            method: 'Runtime.evaluate',
            params: {
                expression: `(async () => {
                    const list = document.querySelector('.overflow-y-auto');
                    if (!list) return [];
                    
                    const chats = [];
                    let currentSection = 'Global';
                    let currentGroup = null;
                    
                    for (const node of list.children) {
                        const h2 = node.querySelector('h2');
                        if (h2) {
                            currentSection = h2.innerText.trim();
                            currentGroup = null;
                            continue;
                        }
                        
                        const groupHeader = node.querySelector('.text-sm.font-medium.truncate');
                        if (groupHeader && currentSection.toLowerCase() === 'projects') {
                            currentGroup = groupHeader.innerText.trim();
                            continue;
                        }
                        
                        const pills = node.querySelectorAll('[data-testid^="convo-pill-"]');
                        for (const p of pills) {
                            const titleEl = p.querySelector('span.truncate');
                            if (!titleEl) continue;
                            
                            let isPinned = false;
                            let pillWorkspace = 'Global';
                            
                            if (currentSection.toLowerCase().includes('pinned')) {
                                isPinned = true;
                            } else if (currentSection.toLowerCase().includes('project')) {
                                pillWorkspace = currentGroup || 'Unknown Project';
                            } else {
                                pillWorkspace = 'Global';
                            }
                            
                            chats.push({
                                title: titleEl.innerText.trim(),
                                workspace: pillWorkspace,
                                section: currentSection
                            });
                        }
                    }
                    return chats;
                })()`,
                awaitPromise: true,
                returnByValue: true
            }
        }));
    });
    ws.on('message', m => {
        const data = JSON.parse(m);
        if(data.id===1) {
            const chats = data.result.result.value;
            const global = chats.filter(c => c.workspace === 'Global');
            console.log(`Total chats: ${chats.length}`);
            console.log(`Global chats: ${global.length}`);
            console.log("Global titles:");
            global.forEach(c => console.log(c.title));
            process.exit(0);
        }
    });
}
run();
