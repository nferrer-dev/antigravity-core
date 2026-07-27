import fs from 'fs';
import CDP from 'chrome-remote-interface';

async function test() {
    let client;
    try {
        const ports = [9000, 9001, 9002, 9003, 63798];
        for (const port of ports) {
            try {
                client = await CDP({ port });
                break;
            } catch(e) {}
        }
        
        if (!client) {
            console.log('Could not connect to CDP');
            return;
        }

        const { Runtime } = client;
        await Runtime.enable();
        
        const expression = `
        (() => {
            const articles = document.querySelectorAll('[role="article"]');
            const results = [];
            for (const el of articles) {
                const fiberKey = Object.keys(el).find(k => k.startsWith('__reactFiber$'));
                let foundIds = [];
                
                if (fiberKey) {
                    let fiber = el[fiberKey];
                    let depth = 0;
                    
                    // Helper to deeply search for IDs in an object (avoiding infinite loops)
                    function searchProps(obj, currentDepth, visited) {
                        if (!obj || typeof obj !== 'object' || currentDepth > 5) return;
                        if (visited.has(obj)) return;
                        visited.add(obj);
                        
                        for (const key in obj) {
                            try {
                                const val = obj[key];
                                if (typeof val === 'string' && (val.length === 36 || val.startsWith('msg-') || key.toLowerCase().includes('id'))) {
                                    foundIds.push({ key: key, value: val, depth: currentDepth });
                                } else if (typeof val === 'object') {
                                    searchProps(val, currentDepth + 1, visited);
                                }
                            } catch(e) {}
                        }
                    }

                    while (fiber && depth < 15) {
                        if (fiber.memoizedProps) {
                            searchProps(fiber.memoizedProps, 0, new Set());
                        }
                        if (fiber.pendingProps) {
                            searchProps(fiber.pendingProps, 0, new Set());
                        }
                        fiber = fiber.return;
                        depth++;
                    }
                }
                
                // deduplicate foundIds
                const uniqueIds = Array.from(new Set(foundIds.map(JSON.stringify))).map(JSON.parse);
                
                results.push({
                    text: el.innerText.substring(0, 20).replace(/\\n/g, ' '),
                    ids: uniqueIds
                });
            }
            return results;
        })();
        `;
        
        const res = await Runtime.evaluate({
            expression: expression,
            returnByValue: true
        });
        
        console.log(JSON.stringify(res.result.value.slice(0, 5), null, 2));
    } catch (err) {
        console.error(err);
    } finally {
        if (client) await client.close();
    }
}

test();
