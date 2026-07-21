const fetch = require('node-fetch'); // actually built in for node 18+

async function run() {
    try {
        console.log("Sending first message to make it generate...");
        await fetch('http://localhost:3000/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'type_text', text: 'Please count to 10 slowly.' })
        });
        await fetch('http://localhost:3000/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'click_element', stableId: 'submit-btn' })
        });
        
        console.log("Waiting 2 seconds for generation to start...");
        await new Promise(r => setTimeout(r, 2000));
        
        console.log("Sending second message to queue it...");
        await fetch('http://localhost:3000/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'type_text', text: 'This should be queued' })
        });
        await fetch('http://localhost:3000/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'click_element', stableId: 'submit-btn' })
        });

        console.log("Done. Check pending_dump.html");
    } catch(e) {
        console.error(e);
    }
}
run();
