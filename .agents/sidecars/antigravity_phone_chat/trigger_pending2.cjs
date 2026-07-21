const fetch = require('node-fetch');

async function run() {
    try {
        console.log("Sending long task...");
        await fetch('http://localhost:3000/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'type_text', text: 'Write a very long 10 paragraph essay about Rome.' })
        });
        await fetch('http://localhost:3000/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'click_element', stableId: 'submit-btn' })
        });
        
        console.log("Waiting 3 seconds for generation to start...");
        await new Promise(r => setTimeout(r, 3000));
        
        console.log("Sending second message to queue it...");
        await fetch('http://localhost:3000/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'type_text', text: 'This message should be queued because the bot is typing the essay' })
        });
        await fetch('http://localhost:3000/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'click_element', stableId: 'submit-btn' })
        });
        
        console.log("Waiting 2 seconds to let snapshot capture it...");
        await new Promise(r => setTimeout(r, 2000));
        
        console.log("Done. Check pending_dump.html");
    } catch(e) {
        console.error(e);
    }
}
run();
