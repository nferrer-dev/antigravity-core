/**
 * @jest-environment jsdom
 */
import { jest } from '@jest/globals';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

describe('Phone UI Logic - Native Rendering', () => {
    let uiCode;

    beforeAll(() => {
        uiCode = fs.readFileSync(path.join(__dirname, '../public/js/app_v8.js'), 'utf8');
    });

    test('updateDOMPreservingScroll should be replaced with native rendering', () => {
        expect(uiCode).not.toMatch(/function updateDOMPreservingScroll/);
    });
    
    test('Should not use HTTP image injection via base64 for remote sync', () => {
        expect(uiCode).not.toMatch(/img\.src\s*=\s*reader\.result/);
    });
});
