const http = require('http');
http.get('http://localhost:39201/app-state', (res) => {
    let data = '';
    res.on('data', chunk => data += chunk);
    res.on('end', () => {
        const state = JSON.parse(data);
        console.log(JSON.stringify({
            runningTasksText: state.runningTasksText,
            runningTasksList: state.runningTasksList
        }, null, 2));
    });
}).on('error', console.error);
