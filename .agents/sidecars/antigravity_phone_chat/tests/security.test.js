import { jest } from '@jest/globals';
import { Readable } from 'stream';

describe('Security Mitigations', () => {
    describe('SSRF Origin Whitelist & Streaming Limit (Frontend Logic)', () => {
        // This is the function we will inject into the browser
        async function fetchCSS(href) {
            try {
                // SSRF Mitigation
                const url = new URL(href, window.location.origin);
                if (url.origin !== window.location.origin) {
                    return '';
                }

                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 1000);

                const response = await window.fetch(url.href, { signal: controller.signal });
                if (!response.ok) {
                    clearTimeout(timeoutId);
                    return '';
                }

                // Streaming limit
                const reader = response.body.getReader();
                const decoder = new TextDecoder('utf-8');
                let accumulatedBytes = 0;
                const MAX_BYTES = 1024 * 1024; // 1MB
                let text = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    accumulatedBytes += value.length;
                    if (accumulatedBytes > MAX_BYTES) {
                        controller.abort();
                        break;
                    }
                    text += decoder.decode(value, { stream: true });
                }
                text += decoder.decode();
                clearTimeout(timeoutId);
                return text;
            } catch (e) {
                return '';
            }
        }

        beforeEach(() => {
            global.window = {
                location: { origin: 'http://localhost:3000' }
            };
        });

        it('should block requests to external origins', async () => {
            global.window.fetch = jest.fn();
            const result = await fetchCSS('http://evil.com/style.css');
            expect(result).toBe('');
            expect(global.window.fetch).not.toHaveBeenCalled();
        });

        it('should allow requests to the same origin', async () => {
            const mockReader = {
                read: jest.fn()
                    .mockResolvedValueOnce({ done: false, value: new Uint8Array([97, 98, 99]) }) // 'abc'
                    .mockResolvedValueOnce({ done: true })
            };
            global.window.fetch = jest.fn().mockResolvedValue({
                ok: true,
                body: { getReader: () => mockReader }
            });

            const result = await fetchCSS('/style.css');
            expect(result).toBe('abc');
            expect(global.window.fetch).toHaveBeenCalledWith('http://localhost:3000/style.css', expect.any(Object));
        });

        it('should abort if payload exceeds 1MB', async () => {
            const mockReader = {
                read: jest.fn()
                    .mockResolvedValueOnce({ done: false, value: new Uint8Array(1024 * 1024 + 10) }) // > 1MB
            };
            const mockAbort = jest.fn();
            global.AbortController = jest.fn().mockImplementation(() => ({
                abort: mockAbort,
                signal: {}
            }));

            global.window.fetch = jest.fn().mockResolvedValue({
                ok: true,
                body: { getReader: () => mockReader }
            });

            const result = await fetchCSS('/massive.css');
            expect(result).toBe('');
            expect(mockAbort).toHaveBeenCalled();
        });
    });

    describe('Tailscale Fallback Logic (Backend)', () => {
        // Extracted backend logic
        function setupTailscaleRenewal(env, setIntervalMock) {
            if (env.TAILSCALE_AVAILABLE === 'true' && env.TAILSCALE_DOMAIN) {
                setIntervalMock(() => {
                    // Logic to renew certs...
                }, 7 * 24 * 60 * 60 * 1000);
            }
        }

        it('should setup interval if TAILSCALE_AVAILABLE is true and domain is present', () => {
            const setIntervalMock = jest.fn();
            setupTailscaleRenewal({ TAILSCALE_AVAILABLE: 'true', TAILSCALE_DOMAIN: 'my-domain.ts.net' }, setIntervalMock);
            expect(setIntervalMock).toHaveBeenCalledWith(expect.any(Function), 604800000); // 7 days
        });

        it('should not setup interval if TAILSCALE_AVAILABLE is false', () => {
            const setIntervalMock = jest.fn();
            setupTailscaleRenewal({ TAILSCALE_AVAILABLE: 'false', TAILSCALE_DOMAIN: 'my-domain.ts.net' }, setIntervalMock);
            expect(setIntervalMock).not.toHaveBeenCalled();
        });
    });
});
