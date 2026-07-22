const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

if (!process.argv.includes('--force')) {
    console.log(`
<BLAST_RADIUS>
  <TARGET>Cortex Database (~/.cortex/cortex.db)</TARGET>
  <REVERSIBILITY>Low</REVERSIBILITY>
  <WORST_CASE_IMPACT>High</WORST_CASE_IMPACT>
</BLAST_RADIUS>
`);
    console.log("Authorization required. Rerun with --force to mutate the database.");
    process.exit(1);
}

const args = process.argv.slice(2);
let directory = null;
let workflow = null;

for (const arg of args) {
    if (arg.startsWith('--workflow=')) {
        workflow = arg.split('=')[1];
    } else if (arg !== '--force') {
        directory = arg;
    }
}

if (!workflow || !directory) {
    console.error('Usage: node cortex_ingest.js <directory> --workflow=<workflow_name> [--force]');
    process.exit(1);
}

const savePyPath = path.join(process.env.USERPROFILE || process.env.HOME, '.cortex', 'save.py');
if (!fs.existsSync(savePyPath)) {
    console.error(`Error: save.py not found at ${savePyPath}`);
    process.exit(1);
}

console.log(`Scanning directory: ${directory}`);
const files = fs.readdirSync(directory);
let successCount = 0;

for (const file of files) {
    const fullPath = path.join(directory, file);
    if (fs.statSync(fullPath).isFile()) {
        console.log(`Ingesting ${file}...`);
        const content = fs.readFileSync(fullPath, 'utf8');
        try {
            const cmd = `python "${savePyPath}" --type reference --namespace "${workflow}"`;
            execSync(cmd, { 
                input: content, 
                stdio: ['pipe', 'inherit', 'inherit'],
                env: { ...process.env, PYTHONUTF8: '1' }
            });
            successCount++;
        } catch (err) {
            console.error(`Failed to ingest ${file}`);
        }
    }
}

console.log(`Successfully ingested ${successCount} files into Cortex namespace '${workflow}'.`);
