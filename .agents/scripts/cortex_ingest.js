const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

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

for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg.startsWith('--workflow=')) {
        workflow = arg.slice('--workflow='.length);
    } else if (arg === '--workflow' && i + 1 < args.length) {
        workflow = args[++i];
    } else if (arg.startsWith('--file=')) {
        directory = arg.slice('--file='.length);
    } else if (arg === '--file' && i + 1 < args.length) {
        directory = args[++i];
    } else if (arg !== '--force') {
        directory = arg;
    }
}

if (!workflow || !directory) {
    console.error('Usage: node cortex_ingest.js <directory> --workflow=<workflow_name> [--force]');
    process.exit(1);
}

if (!/^[a-zA-Z0-9_-]{1,64}$/.test(workflow)) {
    console.error(`Invalid --workflow namespace: ${workflow}`);
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
        
        // Chunk into ~1000 character slices at paragraph boundaries
        const paragraphs = content.split(/\n\s*\n/);
        let chunks = [];
        let currentChunk = "";
        
        for (const p of paragraphs) {
            if (currentChunk.length + p.length > 1000 && currentChunk.length > 0) {
                chunks.push(currentChunk.trim());
                currentChunk = "";
            }
            currentChunk += p + "\n\n";
        }
        if (currentChunk.trim().length > 0) {
            chunks.push(currentChunk.trim());
        }

        console.log(`  -> Sliced into ${chunks.length} chunks`);
        
        try {
            for (let i = 0; i < chunks.length; i++) {
                const chunkContent = chunks[i];
                // Use importance 1.0 (Permanent Memory) and category "textbook" (Semantic Isolation)
                execFileSync(
                    'python',
                    [
                        savePyPath,
                        '--type',
                        'reference',
                        '--namespace',
                        workflow,
                        '--importance',
                        '1.0',
                        '--category',
                        'textbook',
                    ],
                    {
                        input: chunkContent,
                        stdio: ['pipe', 'inherit', 'inherit'],
                        env: { ...process.env, PYTHONUTF8: '1' },
                    }
                );
            }
            successCount++;
        } catch (err) {
            console.error(`Failed to ingest ${file}: ${err.message}`);
        }
    }
}

console.log(`Successfully ingested ${successCount} files into Cortex namespace '${workflow}'.`);
