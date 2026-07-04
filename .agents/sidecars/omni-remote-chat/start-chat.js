const { spawn, execSync } = require('child_process');
const os = require('os');

const isWin = os.platform() === 'win32';
const npx = isWin ? 'npx.cmd' : 'npx';
const cdpPort = process.env.AGY_DEBUG_PORT || '7800';

const child = spawn(npx, [
  'omni-antigravity-remote-chat',
  '--port', '37189',
  '--cdp-port', cdpPort,
  '--bind', '127.0.0.1'
], { stdio: 'inherit' });

child.on('error', (err) => {
  console.error('Failed to start subprocess:', err);
  process.exit(1);
});
child.on('exit', (code) => process.exit(code));

function cleanup() {
  if (isWin) {
    try { execSync(`taskkill /pid ${child.pid} /T /F`); } catch (e) {}
  } else {
    try { execSync(`pkill -P ${child.pid}`); } catch (e) {}
    child.kill('SIGTERM');
  }
}

process.on('SIGINT', cleanup);
process.on('SIGTERM', cleanup);
