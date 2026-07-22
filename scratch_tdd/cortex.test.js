const query = require('./cortex_query');

global.fetch = jest.fn(() =>
  Promise.resolve({
    json: () => Promise.resolve({ paragraphs: ['mocked result'] }),
  })
);

beforeEach(() => {
  fetch.mockClear();
});

describe('cortex_query', () => {
    it('handles validate-design workflow', async () => {
        const result = await query('test', 1, 'validate-design');
        expect(result).toEqual(['mocked result']);
        expect(fetch).toHaveBeenCalledWith('http://localhost:8080/query', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: 'test', k: 1, document_class: 'DesignDocument' })
        });
    });

    it('handles technical-debate workflow', async () => {
        const result = await query('test', 2, 'technical-debate');
        expect(result).toEqual(['mocked result']);
        expect(fetch).toHaveBeenCalledWith('http://localhost:8080/query', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: 'test', k: 2, document_class: 'DebateDocument' })
        });
    });

    it('handles iterative-implement workflow', async () => {
        const result = await query('test', 3, 'iterative-implement');
        expect(result).toEqual(['mocked result']);
        expect(fetch).toHaveBeenCalledWith('http://localhost:8080/query', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: 'test', k: 3, document_class: 'ImplementationDocument' })
        });
    });

    it('rejects invalid workflow name', async () => {
        await expect(query('test', 1, 'invalid-workflow')).rejects.toThrow('Invalid workflow name');
    });

    it('rejects missing workflow name', async () => {
        await expect(query('test', 1)).rejects.toThrow('Invalid workflow name');
    });
});
