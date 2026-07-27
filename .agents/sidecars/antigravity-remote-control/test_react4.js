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
                let key = null;
                let container = null;
                
                if (fiberKey) {
                    let fiber = el[fiberKey];
                    let depth = 0;
                    while (fiber && depth < 10) {
                        if (fiber.key != null) {
                            key = fiber.key;
                            let rawProps = fiber.memoizedProps;
                            if (rawProps && rawProps.container) {
                                container = {
                                    cascadeId: rawProps.container.cascadeId,
                                    // Let's grab some metadata if we can
                                    type: rawProps.container.type
                                };
                            }
                            break;
                        }
                        fiber = fiber.return;
                        depth++;
                    }
                }
                
                results.push({
                    text: el.innerText.substring(0, 20).replace(/\\n/g, ' '),
                    reactKey: key,
                    container: container
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
