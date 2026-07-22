const test = require('node:test');
const assert = require('node:assert');
const { execSync } = require('node:child_process');

test('cortex_ingest outputs exact BLAST_RADIUS XML', () => {
    try {
        const output = execSync('node ./cortex_ingest.js', { encoding: 'utf-8' });
        assert.match(output, /<BLAST_RADIUS>[\s\S]*<\/BLAST_RADIUS>/);
        assert.match(output, /<TARGET>.*<\/TARGET>/);
        assert.match(output, /<REVERSIBILITY>.*<\/REVERSIBILITY>/);
        assert.match(output, /<WORST_CASE_IMPACT>.*<\/WORST_CASE_IMPACT>/);
    } catch (e) {
        if (e.stdout) {
            assert.match(e.stdout, /<BLAST_RADIUS>[\s\S]*<\/BLAST_RADIUS>/);
            assert.match(e.stdout, /<TARGET>.*<\/TARGET>/);
            assert.match(e.stdout, /<REVERSIBILITY>.*<\/REVERSIBILITY>/);
            assert.match(e.stdout, /<WORST_CASE_IMPACT>.*<\/WORST_CASE_IMPACT>/);
        } else {
            throw e;
        }
    }
});
