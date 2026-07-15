const fs = require('fs');
const CDP = require('chrome-remote-interface');

async function test() {
    let client;
    try {
        // Try the known ports from server.js
        const ports = [9000, 9001, 9002, 9003, 63798];
        for (const port of ports) {
            try {
                client = await CDP({ port });
                console.log('Connected on port ' + port);
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
                // Find react fiber key
                const fiberKey = Object.keys(el).find(k => k.startsWith('__reactFiber$'));
                const propsKey = Object.keys(el).find(k => k.startsWith('__reactProps$'));
                let key = 'unknown';
                let id = 'unknown';
                if (fiberKey) {
                    const fiber = el[fiberKey];
                    key = fiber.key;
                    id = fiber.memoizedProps?.id || fiber.pendingProps?.id;
                }
                
                let pkey = 'unknown';
                let pid = 'unknown';
                if (propsKey) {
                    const props = el[propsKey];
                    pkey = props.key;
                    pid = props.id || props['data-message-id'];
                }

                results.push({
                    text: el.innerText.substring(0, 20),
                    reactKey: key,
                    reactId: id,
                    propsKey: pkey,
                    propsId: pid,
                    fiberKeyStr: fiberKey,
                    propsKeyStr: propsKey,
                    attributes: Array.from(el.attributes).map(a => a.name + '=' + a.value).join(', ')
                });
            }
            return results;
        })();
        `;
        
        const res = await Runtime.evaluate({
            expression: expression,
            returnByValue: true
        });
        
        console.log(JSON.stringify(res, null, 2));
    } catch (err) {
        console.error(err);
    } finally {
        if (client) {
            await client.close();
        }
    }
}

test();
