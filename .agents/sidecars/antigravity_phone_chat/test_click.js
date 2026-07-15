const id = "cc75ac78-6bdc-4d79-ae37-4307bc4c4e87";
fetch('http://localhost:3000/remote-click', { 
    method: 'POST', 
    headers: { 'Content-Type': 'application/json' }, 
    body: JSON.stringify({ 
        id, 
        selector: 'button[aria-label="Good response"]', 
        index: 0, 
        textContent: '' 
    }) 
})
.then(r => r.json())
.then(console.log)
.catch(console.error);
