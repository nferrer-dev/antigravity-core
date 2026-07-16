const CDP = require('chrome-remote-interface');
const fs = require('fs');

(async function() {
    try {
        const client = await CDP({ port: 9000 });
        const { Runtime } = client;
        
        const script = `
            const editor = document.querySelector('[contenteditable="true"]');
            let parent = editor;
            for(let i=0; i<5; i++) {
                if(parent.parentElement) parent = parent.parentElement;
            }
            parent.outerHTML;
        `;
        const result = await Runtime.evaluate({ expression: script });
        const html = result.result.value || '';
        fs.writeFileSync('scratch/dump_compose.html', html);
        console.log('Dumped compose area');
        await client.close();
    } catch (e) {
        console.error(e);
    }
})();
