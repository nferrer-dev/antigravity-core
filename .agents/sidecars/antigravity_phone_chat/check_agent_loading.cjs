const fs = require('fs');
const htmlGen = fs.readFileSync('dom_generating.html', 'utf8');
const htmlIdle = fs.readFileSync('C:/Users/nferr/.gemini/antigravity/brain/eee4402c-9228-44d1-ba6b-366d51379fa5/scratch/dom3.html', 'utf8');
const { JSDOM } = require('jsdom');
const domGen = new JSDOM(htmlGen).window.document;
const domIdle = new JSDOM(htmlIdle).window.document;

console.log('Generating:', domGen.querySelectorAll('[data-testid="agent-loading"]').length);
console.log('Idle:', domIdle.querySelectorAll('[data-testid="agent-loading"]').length);
