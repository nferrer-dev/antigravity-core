const http = require('http');
http.get('http://localhost:39201/app-state', (res) => {
    let data = '';
    res.on('data', chunk => data += chunk);
    res.on('end', () => console.log('STATUS:', res.statusCode, 'DATA:', data));
});
