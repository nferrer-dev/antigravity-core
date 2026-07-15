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
                results.push({
                    text: el.innerText.substring(0, 20).replace(/\\n/g, ' '),
                    id: el.id,
                    className: el.className,
                    dataset: Object.assign({}, el.dataset)
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
