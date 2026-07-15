import assert from 'node:assert';
import test from 'node:test';
import { handleSnapshotUpdate } from './server.js';

test('Push notification logic', async (t) => {
    await t.test('sendNotification is triggered exactly once when isGenerating transitions from true to false', () => {
        let sendNotificationCalledCount = 0;
        let sentSub = null;
        let sentPayload = null;
        
        const mockWebPush = {
            sendNotification: async (sub, payload) => {
                sendNotificationCalledCount++;
                sentSub = sub;
                sentPayload = payload;
                return Promise.resolve();
            }
        };

        const mockSubscriptions = [{ endpoint: 'https://mock.endpoint' }];
        
        const lastSnapshot = { isGenerating: true };
        const currentSnapshot = { isGenerating: false };

        handleSnapshotUpdate(lastSnapshot, currentSnapshot, mockSubscriptions, mockWebPush);

        assert.strictEqual(sendNotificationCalledCount, 1, 'sendNotification should be called exactly once');
        assert.deepStrictEqual(sentSub, mockSubscriptions[0], 'Should send to the correct subscription');
        assert.ok(sentPayload.includes('Generation complete!'), 'Payload should include the completion message');
    });

    await t.test('sendNotification is NOT triggered when isGenerating remains true', () => {
        let sendNotificationCalledCount = 0;
        const mockWebPush = {
            sendNotification: async () => { sendNotificationCalledCount++; return Promise.resolve(); }
        };
        const mockSubscriptions = [{ endpoint: 'https://mock.endpoint' }];
        
        const lastSnapshot = { isGenerating: true };
        const currentSnapshot = { isGenerating: true };

        handleSnapshotUpdate(lastSnapshot, currentSnapshot, mockSubscriptions, mockWebPush);

        assert.strictEqual(sendNotificationCalledCount, 0, 'sendNotification should not be called');
    });

    await t.test('Stale subscriptions (404/410) are removed from the array', async () => {
        const mockWebPush = {
            sendNotification: async (sub) => { 
                if (sub.endpoint === 'stale') {
                    const err = new Error('Gone');
                    err.statusCode = 410;
                    return Promise.reject(err);
                }
                return Promise.resolve(); 
            }
        };
        const mockSubscriptions = [{ endpoint: 'stale' }, { endpoint: 'good' }];
        
        const lastSnapshot = { isGenerating: true };
        const currentSnapshot = { isGenerating: false };

        await handleSnapshotUpdate(lastSnapshot, currentSnapshot, mockSubscriptions, mockWebPush);

        assert.strictEqual(mockSubscriptions.length, 1, 'Stale subscription should be removed');
        assert.strictEqual(mockSubscriptions[0].endpoint, 'good', 'Good subscription should remain');
    });

    await t.test('sendNotification is NOT triggered when isGenerating remains false', () => {
        let sendNotificationCalledCount = 0;
        const mockWebPush = {
            sendNotification: async () => { sendNotificationCalledCount++; return Promise.resolve(); }
        };
        const mockSubscriptions = [{ endpoint: 'https://mock.endpoint' }];
        
        const lastSnapshot = { isGenerating: false };
        const currentSnapshot = { isGenerating: false };

        handleSnapshotUpdate(lastSnapshot, currentSnapshot, mockSubscriptions, mockWebPush);

        assert.strictEqual(sendNotificationCalledCount, 0, 'sendNotification should not be called');
    });
});
