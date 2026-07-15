const cheerio = require('cheerio');
fetch('http://127.0.0.1:4747/snapshot', {headers: {Cookie: 'ag_auth_token=ag_default_token'}})
    .then(r => r.json())
    .then(j => {
        const $ = cheerio.load(j.html);
        console.log($('[id="antigravity.agentSidePanelInputBox"]').html());
    });
