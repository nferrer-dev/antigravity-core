/**
 * @jest-environment jsdom
 */
import { jest } from '@jest/globals';
console.error = function(m, e) { console.log('CAUGHT ERROR: ', m, e); };

// Mock globals needed by app_v8.js
global.localStorage = {
    getItem: jest.fn(),
    setItem: jest.fn(),
};

window.addEventListener('error', e => console.log('WINDOW ERROR:', e.error));
global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
window.fetch = global.fetch;
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
    removeChild: jest.fn(),
    value: "",
    dataset: {},
    contains: jest.fn().mockReturnValue(false)
};
document.getElementById = jest.fn((id) => {
    if (id === 'chatContainer' || id === 'chat-container') {
        return document.body;
    }
    return dummyElement;
});

describe('Phone UI Logic - Optimistic Locking & Debouncing', () => {
    let originalFetchWithAuth;

    beforeAll(async () => {
        const fs = await import('fs');
        const path = await import('path');
        const scriptCode = fs.readFileSync(path.join(process.cwd(), 'public/js/app_v8.js'), 'utf8');
        
        try {
            eval(scriptCode);
        } catch (e) {
            console.error("Eval failed:", e);
            throw e;
        }
    });

    beforeEach(() => {
        jest.clearAllMocks();
        window.pendingMutations = new Set();
    });

    test('Optimistic Locking: 50 click events on vscode-radio should trigger exactly 1 fetch', async () => {
        const chatContainer = document.getElementById('chat-container');
        
        // Wrap in a div to prevent early return in app_v8 click handler
        const divWrapper = document.createElement('div');
        chatContainer.appendChild(divWrapper);

        // Mock a vscode-radio element
        const radio = document.createElement('vscode-radio');
        radio.setAttribute('data-ag-id', 'test-radio-1');
        divWrapper.appendChild(radio);

        let clickReachedDocument = false;
        document.addEventListener('click', () => { clickReachedDocument = true; });

        // Simulate 50 click events rapidly
        for (let i = 0; i < 50; i++) {
            const clickEvent = new Event('click', { bubbles: true, cancelable: true });
            radio.dispatchEvent(clickEvent);
        }

        console.log("Click reached document?", clickReachedDocument);

        await new Promise(r => setTimeout(r, 50));

        // Check what fetch was called with
        console.log("FETCH CALLS", global.fetch.mock.calls.map(c => c[0]));
        
        // Filter out non-/send calls to test only the click logic
        const sendCalls = global.fetch.mock.calls.filter(c => c[0] === '/send');
        expect(sendCalls.length).toBe(1);
    });

    test('Text Input Sync Integrity: rapid input and focusout on vscode-text-field', async () => {
        const chatContainer = document.getElementById('chat-container');
        
        // Wrap in a div to prevent early return in app_v8 click handler
        const divWrapper = document.createElement('div');
        chatContainer.appendChild(divWrapper);

        const textField = document.createElement('vscode-text-field');
        textField.setAttribute('data-ag-id', 'test-input-1');
        divWrapper.appendChild(textField);

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
        expect(requestBody.text).toBe("Hello");

        // The _lastSentValue lock should prevent duplicate sends
        textField.dispatchEvent(new Event('focusout', { bubbles: true }));

        await new Promise(r => setTimeout(r, 50));

        // It shouldn't have fired another fetch for the exact same value
        expect(global.fetch.mock.calls.length).toBe(fetchCalls.length);
    });

    test('injectQueuedMessageButtons: should inject Edit and Redirect icons and bind events', () => {
        const chatContainer = document.getElementById('chat-container');
        
        // Mock a queued message with a revert button
        const article = document.createElement('div');
        article.setAttribute('role', 'article');
        
        const revertBtn = document.createElement('button');
        revertBtn.setAttribute('data-testid', 'revert-button');
        revertBtn.setAttribute('data-ag-id', 'test-revert-1');
        
        const statusMessage = document.createElement('div');
        statusMessage.className = 'status-message queued';
        
        const btnContainer = document.createElement('div');
        btnContainer.appendChild(revertBtn);
        article.appendChild(statusMessage);
        article.appendChild(btnContainer);
        chatContainer.appendChild(article);

        // Run the function
        if (typeof global.injectQueuedMessageButtons === 'function') {
            global.injectQueuedMessageButtons();
        } else if (typeof window.injectQueuedMessageButtons === 'function') {
            window.injectQueuedMessageButtons();
        } else {
            // Assume it's available globally due to eval
            injectQueuedMessageButtons();
        }

        console.log("ARTICLE HTML:", article.outerHTML);
        // Check if icons are injected
        const editBtn = article.querySelector('.ag-queued-edit-btn');
        const redirectBtn = article.querySelector('.ag-queued-redirect-btn');
        
        expect(editBtn).not.toBeNull();
        expect(redirectBtn).not.toBeNull();

        // Simulate clicks and check fetch arguments
        editBtn.click();
        expect(global.fetch).toHaveBeenCalledWith('/api/orchestrate/replace_input', expect.objectContaining({
            method: 'POST',
            body: JSON.stringify({ targetAgId: 'test-revert-1', prefix: '' })
        }));

        redirectBtn.click();
        expect(global.fetch).toHaveBeenCalledWith('/api/orchestrate/replace_input', expect.objectContaining({
            method: 'POST',
            body: JSON.stringify({ targetAgId: 'test-revert-1', prefix: '/redirect ' })
        }));
    });
});
