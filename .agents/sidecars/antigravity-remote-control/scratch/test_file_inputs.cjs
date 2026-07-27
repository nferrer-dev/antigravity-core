const CDP = require('chrome-remote-interface');
(async function() {
    try {
        const client = await CDP({ port: 9000 });
        const { Runtime } = client;
        let res = await Runtime.evaluate({ expression: `document.querySelectorAll('input[type="file"]').length` });
        console.log('File inputs count:', res.result.value);
        
        let res2 = await Runtime.evaluate({ expression: `
            Array.from(document.querySelectorAll('input[type="file"]')).map(el => {
                let current = el;
                let path = [];
                while (current) {
                    path.push(current.className || current.tagName);
                    current = current.parentElement;
                }
                return path.join(' < ');
            }).join('\\n---INPUT---\\n');
        ` });
        console.log(res2.result.value);
        await client.close();
    } catch (e) {
        console.error(e);
    }
})();
