const { spawn, exec } = require('child_process');
const util = require('util');
const net = require('net');

const execAsync = util.promisify(exec);

// --- Singleton Lock (Named Pipe) ---
// By binding to a named pipe, the OS automatically releases the lock
// if this watchdog process crashes or is killed, preventing a stale lock.
const LOCK_PIPE = '\\\\.\\pipe\\antigravity_watchdog_lock';
const lockServer = net.createServer();

lockServer.on('error', (err) => {
  if (err.code === 'EADDRINUSE') {
    console.log('[Watchdog] Another instance is already running. Exiting.');
    process.exit(0);
  } else {
    console.error('[Watchdog] Lock server error:', err);
  }
});

lockServer.listen(LOCK_PIPE, () => {
  console.log('[Watchdog] Lock acquired. Starting watchdog loop...');
  watch();
});

// --- State ---
let serverChild = null;

// --- Process Management ---
async function isAntigravityRunning() {
  try {
    // Run asynchronously with a 5-second timeout to prevent blocking the event loop
    const { stdout } = await execAsync('tasklist /FI "IMAGENAME eq Antigravity.exe" /FO CSV /NH', { timeout: 5000, encoding: 'utf8' });
    return stdout.includes('Antigravity.exe');
  } catch (e) {
    // If tasklist fails or times out, safely assume it's not running
    return false;
  }
}

function spawnServer() {
  if (serverChild) return; // Already running

  console.log('[Watchdog] Starting server.js...');

  const isWindows = process.platform === 'win32';
  const pythonPath = isWindows ? 'venv\\\\Scripts\\\\python.exe' : 'venv/bin/python';

  // Spawn as an attached child process (not detached)
  serverChild = spawn(pythonPath, ['-u', 'launcher.py', '--mode', 'local'], {
    cwd: __dirname,
    stdio: 'pipe', // Capture output
    env: { ...process.env, PYTHONUNBUFFERED: '1', PYTHONIOENCODING: 'utf-8' }
  });
  
  serverChild.stdout.on('data', (data) => console.log(data.toString()));
  serverChild.stderr.on('data', (data) => console.error(data.toString()));

  console.log(`[Watchdog] Server started with PID: ${serverChild.pid}`);

  serverChild.on('exit', (code, signal) => {
    console.log(`[Watchdog] Server exited (Code: ${code}, Signal: ${signal}).`);
    serverChild = null; // Clear reference so it can be restarted if needed
  });

  serverChild.on('error', (err) => {
    console.error(`[Watchdog] Failed to start server: ${err.message}`);
    serverChild = null;
  });
}

function killServer() {
  if (serverChild) {
    console.log(`[Watchdog] Shutting down server (PID: ${serverChild.pid})...`);
    serverChild.kill('SIGTERM'); // Graceful termination

    // Fallback kill if it doesn't shut down
    setTimeout(() => {
      if (serverChild) {
        console.log(`[Watchdog] Force killing server (PID: ${serverChild.pid})...`);
        serverChild.kill('SIGKILL');
      }
    }, 3000).unref();
  }
}

// --- Lifecycle Handlers (Zombie Prevention) ---
process.on('exit', () => {
  console.log('[Watchdog] Watchdog exiting, cleaning up children...');
  killServer();
});

// Ensure SIGINT/SIGTERM trigger a clean exit
process.on('SIGINT', () => process.exit(0));
process.on('SIGTERM', () => process.exit(0));

// --- Main Loop ---
async function watch() {
  while (true) {
    const agRunning = await isAntigravityRunning();

    if (agRunning) {
      if (!serverChild) {
        console.log('[Watchdog] Antigravity is running but server is down.');
        spawnServer();
      }
    } else {
      if (serverChild) {
        console.log('[Watchdog] Antigravity is closed. Shutting down server...');
        killServer();
      }
    }

    // Wait 15 seconds before checking again
    await new Promise((r) => setTimeout(r, 15000));
  }
}
