const test = require('node:test');
const assert = require('node:assert');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const SCRIPT = path.join(__dirname, '..', 'scripts', 'cortex_ingest.js');

test('cortex_ingest outputs exact BLAST_RADIUS XML and exits non-zero without --force', () => {
    try {
        execFileSync(process.execPath, [SCRIPT], { encoding: 'utf-8' });
        assert.fail('Expected non-zero exit code when --force is omitted');
    } catch (e) {
        assert.notStrictEqual(e.status, 0);
        assert.match(e.stdout || '', /<BLAST_RADIUS>[\s\S]*<\/BLAST_RADIUS>/);
        assert.match(e.stdout || '', /<TARGET>.*<\/TARGET>/);
        assert.match(e.stdout || '', /<REVERSIBILITY>.*<\/REVERSIBILITY>/);
        assert.match(e.stdout || '', /<WORST_CASE_IMPACT>.*<\/WORST_CASE_IMPACT>/);
    }
});

test('cortex_ingest uses execFileSync and rejects CWE-78 shell metacharacters in --workflow', () => {
    const src = fs.readFileSync(SCRIPT, 'utf-8');
    assert.match(src, /execFileSync/);
    assert.doesNotMatch(src, /\bexecSync\s*\(/);
    try {
        execFileSync(
            process.execPath,
            [SCRIPT, '--force', '--workflow', 'bad;echo_pwned', '--file', SCRIPT],
            { encoding: 'utf-8' }
        );
        assert.fail('Expected non-zero exit code on invalid --workflow namespace');
    } catch (e) {
        assert.notStrictEqual(e.status, 0);
        assert.match((e.stderr || '') + (e.stdout || ''), /Invalid --workflow/i);
    }
});

