const express = require('express');
const app = express();
const path = require('path');

app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'secure_evil.html'));
});

app.listen(4001, () => console.log('Evil attacker server running on port 4001'));
