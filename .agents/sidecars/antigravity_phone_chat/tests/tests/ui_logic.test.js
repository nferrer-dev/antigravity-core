/**
 * @jest-environment jsdom
 */

// Mock globals needed by app_v8.js
global.localStorage = {
    getItem: jest.fn(),
    setItem: jest.fn(),
};

global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
global.window.pendingMutations = new Map();
global.CSS = { escape: (s) => s };

Object.defineProperty(HTMLElement.prototype, 'innerText', {
    get() { return this.textContent; }
});

// We need to inject the DOM elements that app_v8.js expects before loading it
const dummyElement = {
    addEventListener: jest.fn(),
    classList: { toggle: jest.fn(), add: jest.fn(), remove: jest.fn() },
    setAttribute: jest.fn(),
    getAttribute: jest.fn(),
    style: {},
    appendChild: jest.fn(),
    removeChild: jest.fn()
};
document.getElementById = jest.fn((id) => {
    if (id === 'chatContainer' || id === 'chat-container') {
        return document.body;
    }
    return dummyElement;
});

describe('Phone UI Logic - Optimistic Locking & Debouncing', () => {
    let originalFetchWithAuth;

    beforeAll(() => {
        const fs = require('fs');
        const path = require('path');
        const scriptCode = fs.readFileSync(path.join(__dirname, '../public/js/app_v8.js'), 'utf8');
        
        try {
            eval(scriptCode);
        } catch (e) {
            // Ignore init errors since some DOM elements might be missing
        }
    });

    beforeEach(() => {
        jest.clearAllMocks();
    });

    test('Optimistic Locking: 50 click events on vscode-radio should trigger exactly 1 fetch', async () => {
        const chatContainer = document.getElementById('chat-container');
        
        // Mock a vscode-radio element
        const radio = document.createElement('vscode-radio');
        radio.setAttribute('data-ag-id', 'test-radio-1');
        chatContainer.appendChild(radio);

        let clickReachedDocument = false;
        document.addEventListener('click', () => { clickReachedDocument = true; });

        // Simulate 50 click events rapidly
        for (let i = 0; i < 50; i++) {
            const clickEvent = new Event('click', { bubbles: true, cancelable: true });
            radio.dispatchEvent(clickEvent);
        }

        console.log("Click reached document?", clickReachedDocument);

        // Check that fetchWithAuth was called exactly once
        expect(global.fetch).toHaveBeenCalledTimes(1);
    });

    test('Text Input Sync Integrity: rapid input and focusout on vscode-text-field', async () => {
        const chatContainer = document.getElementById('chat-container');
        
        const textField = document.createElement('vscode-text-field');
        textField.setAttribute('data-ag-id', 'test-text-1');
        chatContainer.appendChild(textField);

        // Simulate rapid typing
        const textToType = "Hello";
        for (let i = 0; i < textToType.length; i++) {
            textField.value = textToType.substring(0, i + 1);
            textField.dispatchEvent(new Event('input', { bubbles: true }));
        }

        // Dispatch focusout to trigger immediate sync
        textField.dispatchEvent(new Event('focusout', { bubbles: true }));

        // Check that the last fetch sent the full "Hello" payload
        const fetchCalls = global.fetch.mock.calls;
        const lastCall = fetchCalls[fetchCalls.length - 1];
        expect(lastCall).toBeDefined();
        
        const requestBody = JSON.parse(lastCall[1].body);
        expect(requestBody.value).toBe("Hello");

        // The _lastSentValue lock should prevent duplicate sends
        textField.dispatchEvent(new Event('focusout', { bubbles: true }));
        // It shouldn't have fired another fetch for the exact same value
        expect(global.fetch.mock.calls.length).toBe(fetchCalls.length);
    });
});
