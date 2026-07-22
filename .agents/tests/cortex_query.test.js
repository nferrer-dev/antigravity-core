const test = require('node:test');
const assert = require('node:assert');
const query = require('./cortex_query');

test('cortex_query parses JSON correctly', async () => {
    global.fetch = async () => ({
        json: async () => ({ paragraphs: ['para1', 'para2'] })
    });
    const result = await query('test query', 2);
    assert.deepStrictEqual(result, ['para1', 'para2']);
});
