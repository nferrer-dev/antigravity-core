#!/usr/bin/env node
import 'dotenv/config';
import express from 'express';
import multer from 'multer';
import webpush from 'web-push';
import compression from 'compression';
import cookieParser from 'cookie-parser';
import { WebSocketServer } from 'ws';
import http from 'http';
import https from 'https';
import fs from 'fs';
import os from 'os';
import WebSocket from 'ws';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { inspectUI } from './ui_inspector.js';
import { execSync } from 'child_process';

const SUBSCRIPTIONS_FILE = './pushSubscriptions.json';

export const pushSubscriptions = [];
try {
    if (fs.existsSync(SUBSCRIPTIONS_FILE)) {
        const data = fs.readFileSync(SUBSCRIPTIONS_FILE, 'utf8');
        pushSubscriptions.push(...JSON.parse(data));
        console.log(`Loaded ${pushSubscriptions.length} push subscriptions from disk.`);
    }
} catch(e) {
    console.error('Error loading push subscriptions:', e);
}

let pushTimeout = null;

export function handleSnapshotUpdate(lastSnapshot, currentSnapshot, subscriptions = pushSubscriptions, webPushClient = webpush) {
    if (currentSnapshot.isGenerating && pushTimeout) {
        clearTimeout(pushTimeout);
        pushTimeout = null;
    }

    if (lastSnapshot && lastSnapshot.isGenerating && !currentSnapshot.isGenerating) {
        if (pushTimeout) clearTimeout(pushTimeout);
        
        pushTimeout = setTimeout(() => {
            pushTimeout = null;
            Promise.all(subscriptions.map(sub => 
                webPushClient.sendNotification(sub, JSON.stringify({
                    title: 'Antigravity',
                    body: 'Generation complete!'
                })).catch(e => {
                    if (e.statusCode === 404 || e.statusCode === 410) {
                        const idx = subscriptions.indexOf(sub);
                        if (idx > -1) subscriptions.splice(idx, 1);
                    } else {
                        console.error('Push error:', e);
                    }
                })
            ));
        }, 2000);
    }
    return Promise.resolve();
}


const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const PORTS = [7800, 9000, 9001, 9002, 9003, 63798];
const POLL_INTERVAL = 1000; // 1 second
const SERVER_PORT = process.env.PORT || 3000;
const APP_PASSWORD = process.env.APP_PASSWORD || 'antigravity';
const AUTH_COOKIE_NAME = 'ag_auth_token';

// Security warning for default credentials
if (APP_PASSWORD === 'antigravity') {
    console.warn('\n\x1b[33m%s\x1b[0m', '⚠️  SECURITY WARNING: Using default APP_PASSWORD ("antigravity").');
    console.warn('\x1b[33m%s\x1b[0m', '   Set a strong APP_PASSWORD in your .env file for production use.\n');
}

// Note: hashString is defined later, so we'll initialize the token inside createServer or use a simple string for now.
let AUTH_TOKEN = 'ag_default_token';


// Shared CDP connection
let cdpConnection = null;
let lastSnapshot = null;
let lastSnapshotHash = null;

// Kill any existing process on the server port (prevents EADDRINUSE)
function killPortProcess(port) {
    try {
        if (process.platform === 'win32') {
            // Windows: Find PID using netstat and kill it
            const result = execSync(`netstat -ano | findstr :${port} | findstr LISTENING`, { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] });
            const lines = result.trim().split('\n');
            const pids = new Set();
            for (const line of lines) {
                const parts = line.trim().split(/\s+/);
                const pid = parts[parts.length - 1];
                if (pid && pid !== '0') pids.add(pid);
            }
            for (const pid of pids) {
                try {
                    execSync(`taskkill /PID ${pid} /F`, { stdio: 'pipe' });
                    console.log(`⚠️  Killed existing process on port ${port} (PID: ${pid})`);
                } catch (e) { /* Process may have already exited */ }
            }
        } else {
            // Linux/macOS: Use lsof and kill
            const result = execSync(`lsof -ti:${port}`, { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] });
            const pids = result.trim().split('\n').filter(p => p);
            for (const pid of pids) {
                try {
                    execSync(`kill -9 ${pid}`, { stdio: 'pipe' });
                    console.log(`⚠️  Killed existing process on port ${port} (PID: ${pid})`);
                } catch (e) { /* Process may have already exited */ }
            }
        }
        // Small delay to let the port be released
        return new Promise(resolve => setTimeout(resolve, 500));
    } catch (e) {
        // No process found on port - this is fine
        return Promise.resolve();
    }
}

// Get local IP address for mobile access
// Prefers real network IPs (192.168.x.x, 10.x.x.x) over virtual adapters (172.x.x.x from WSL/Docker)
function getLocalIP() {
    const interfaces = os.networkInterfaces();
    const candidates = [];

    for (const name of Object.keys(interfaces)) {
        for (const iface of interfaces[name]) {
            // Skip internal and non-IPv4 addresses
            if (iface.family === 'IPv4' && !iface.internal) {
                candidates.push({
                    address: iface.address,
                    name: name,
                    // Prioritize common home/office network ranges
                    priority: iface.address.startsWith('192.168.') ? 1 :
                        iface.address.startsWith('10.') ? 2 :
                            iface.address.startsWith('172.') ? 3 : 4
                });
            }
        }
    }

    // Sort by priority and return the best one
    candidates.sort((a, b) => a.priority - b.priority);
    return candidates.length > 0 ? candidates[0].address : 'localhost';
}

// Helper: HTTP GET JSON
function getJson(url) {
    return new Promise((resolve, reject) => {
        http.get(url, (res) => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                try { resolve(JSON.parse(data)); } catch (e) { reject(e); }
            });
        }).on('error', reject);
    });
}

// Find Antigravity CDP endpoint
// Find Antigravity CDP endpoint
async function discoverCDP() {
    const errors = [];
    for (const port of PORTS) {
        try {
            const list = await getJson(`http://127.0.0.1:${port}/json/list`);

            // Priority 1: Standard Workbench (The main window)
            const workbench = list.find(t => t.url?.includes('workbench.html') || (t.title && t.title.includes('workbench')));
            if (workbench && workbench.webSocketDebuggerUrl) {
                console.log('Found Workbench target:', workbench.title);
                return { port, url: workbench.webSocketDebuggerUrl };
            }

            // Priority 2: Jetski/Launchpad (Fallback)
            const jetski = list.find(t => t.url?.includes('jetski') || t.title === 'Launchpad');
            if (jetski && jetski.webSocketDebuggerUrl) {
                console.log('Found Jetski/Launchpad target:', jetski.title);
                return { port, url: jetski.webSocketDebuggerUrl };
            }

            // Priority 3: Antigravity Web Chat
            const chat = list.find(t => t.url?.includes('/c/') || (t.type === 'page' && t.url?.includes('127.0.0.1')));
            if (chat && chat.webSocketDebuggerUrl) {
                console.log('Found Web Chat target:', chat.title);
                return { port, url: chat.webSocketDebuggerUrl };
            }
        } catch (e) {
            errors.push(`${port}: ${e.message}`);
        }
    }
    const errorSummary = errors.length ? `Errors: ${errors.join(', ')}` : 'No ports responding';
    throw new Error(`CDP not found. ${errorSummary}`);
}

// Connect to CDP
async function connectCDP(url) {
    const ws = new WebSocket(url);
    await new Promise((resolve, reject) => {
        ws.on('open', resolve);
        ws.on('error', reject);
    });

    let idCounter = 1;
    const pendingCalls = new Map(); // Track pending calls by ID
    const contexts = [];
    const CDP_CALL_TIMEOUT = 30000; // 30 seconds timeout

    // Single centralized message handler (fixes MaxListenersExceeded warning)
    ws.on('message', (msg) => {
        try {
            const data = JSON.parse(msg);

            // Handle CDP method responses
            if (data.id !== undefined && pendingCalls.has(data.id)) {
                const { resolve, reject, timeoutId } = pendingCalls.get(data.id);
                clearTimeout(timeoutId);
                pendingCalls.delete(data.id);

                if (data.error) reject(data.error);
                else resolve(data.result);
            }

            // Handle execution context events
            if (data.method === 'Runtime.executionContextCreated') {
                contexts.push(data.params.context);
            } else if (data.method === 'Runtime.executionContextDestroyed') {
                const id = data.params.executionContextId;
                const idx = contexts.findIndex(c => c.id === id);
                if (idx !== -1) contexts.splice(idx, 1);
            } else if (data.method === 'Runtime.executionContextsCleared') {
                contexts.length = 0;
            } else if (data.method === 'Runtime.consoleAPICalled') {
                const args = data.params.args;
                if (args && args.length > 0 && args[0].value && typeof args[0].value === 'string' && args[0].value.startsWith('AG_CLIPBOARD_HOOK:')) {
                    const text = args[0].value.substring(18);
                    if (global.onRemoteClipboardWrite) global.onRemoteClipboardWrite(text);
                }
            }
        } catch (e) { }
    });

    const call = (method, params) => new Promise((resolve, reject) => {
        const id = idCounter++;

        // Setup timeout to prevent memory leaks from never-resolved calls
        const timeoutId = setTimeout(() => {
            if (pendingCalls.has(id)) {
                pendingCalls.delete(id);
                reject(new Error(`CDP call ${method} timed out after ${CDP_CALL_TIMEOUT}ms`));
            }
        }, CDP_CALL_TIMEOUT);

        pendingCalls.set(id, { resolve, reject, timeoutId });
        ws.send(JSON.stringify({ id, method, params }));
    });

    await call("Runtime.enable", {});
    await new Promise(r => setTimeout(r, 1000));

    return { ws, call, contexts };
}

// Capture chat snapshot
async function captureSnapshot(cdp) {
    const CAPTURE_SCRIPT = `(async () => {
        const cascade = document.querySelector('[data-testid="conversation-view"]');
        if (!cascade) {
            // Check if we are on an empty new chat screen
            const hasInput = document.querySelector('[aria-label="Message input"]');
            if (hasInput) {
                return {
                    html: '<div class="w-full flex h-full min-h-0 flex-col items-center justify-center relative overflow-y-auto" data-testid="conversation-view"></div>',
                    css: '',
                    isGenerating: false,
                    stats: { nodes: 1, htmlSize: 100, cssSize: 0 }
                };
            }

            // If the chat container is missing (e.g. user is on a background task tab), attempt to click back to the chat!
            const chatTab = Array.from(document.querySelectorAll('a, button, [role="button"]')).find(e => e.innerText && e.innerText.trim().length > 0 && e.closest('.bg-sidebar-secondary'));
            if (chatTab) chatTab.click();
            
            // Debug info
            const body = document.body;
            const childIds = Array.from(body.children).map(c => c.id).filter(id => id).join(', ');
            return { error: 'chat container not found', debug: { hasBody: !!body, availableIds: childIds } };
        }
        
        const cascadeStyles = window.getComputedStyle(cascade);
        
        // Deep React Fiber Identity Extraction for messages
        try {
            const convId = window.location.pathname.split('/').pop();
            const articles = cascade.querySelectorAll('[role="article"]');
            for (const el of articles) {
                const fiberKey = Object.keys(el).find(k => k.startsWith('__reactFiber$'));
                if (!fiberKey) continue;
                
                let fiber = el[fiberKey];
                let depth = 0;
                let foundId = null;
                
                // Helper to deeply search for IDs
                function searchProps(obj, currentDepth, visited) {
                    if (!obj || typeof obj !== 'object' || currentDepth > 5) return null;
                    if (visited.has(obj)) return null;
                    visited.add(obj);

                    for (const key in obj) {
                        try {
                            const val = obj[key];
                            // Match UUIDs (length 36) or message IDs
                            if (typeof val === 'string' && val.length === 36 && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(val)) {
                                // Skip the conversation ID which we know is a UUID but shared across all messages
                                if (val === convId) continue;
                                return val;
                            } else if (typeof val === 'object') {
                                const res = searchProps(val, currentDepth + 1, visited);
                                if (res) return res;
                            }
                        } catch(e) {}
                    }
                    return null;
                }

                while (fiber && depth < 15) {
                    if (fiber.memoizedProps) {
                        foundId = searchProps(fiber.memoizedProps, 0, new Set());
                        if (foundId) break;
                    }
                    if (fiber.pendingProps) {
                        foundId = searchProps(fiber.pendingProps, 0, new Set());
                        if (foundId) break;
                    }
                    fiber = fiber.return;
                    depth++;
                }
                
                if (foundId) {
                    el.setAttribute('data-message-id', foundId);
                }
            }
        } catch (e) {}

        // Find the main scrollable container
        const scrollContainer = cascade.querySelector('.overflow-y-auto, [data-scroll-area]') || cascade;

        // CRITICAL: If the Desktop App is currently loading older messages, it often replaces the entire chat 
        // container with a spinner temporarily. If we capture this transient state, the Mobile App will render
        // an empty chat, causing scrollHeight to collapse, which completely ruins the user's scroll position
        // when the messages finally load a second later.
        // We detect this by checking if the scrollContainer has less than 200px of content (a real chat is much taller).
        if (scrollContainer.scrollHeight < 200) {
            return { error: 'transient loading state detected, skipping snapshot' };
        }

        const scrollInfo = {
            scrollTop: scrollContainer.scrollTop,
            scrollHeight: scrollContainer.scrollHeight,
            clientHeight: scrollContainer.clientHeight,
            scrollPercent: scrollContainer.scrollTop / (scrollContainer.scrollHeight - scrollContainer.clientHeight) || 0
        };
        
        // Mark fixed/absolute elements in the original DOM before cloning
        // This is the only way to reliably catch CSS-class-based positioning
        const candidates = cascade.querySelectorAll('*');
        let nodeCounter = 0;
        candidates.forEach(el => {
            try {
                // Universally tag every single element with a deterministic ID
                // This allows the phone to trigger clicks on ANY element (even divs acting as buttons)
                el.setAttribute('data-ag-id', 'ag-n-' + (++nodeCounter));

                if (el.tagName === 'INPUT' && (el.type === 'radio' || el.type === 'checkbox')) {
                    let semanticId = '';
                    if (el.name) semanticId += 'name-' + el.name;
                    if (el.value) semanticId += (semanticId ? '-' : '') + 'val-' + el.value;
                    if (el.id) semanticId += (semanticId ? '-' : '') + 'id-' + el.id;
                    
                    if (semanticId) {
                        el.setAttribute('data-stable-id', 'ag-stable-' + semanticId);
                    } else {
                        const parentArticle = el.closest('[role="article"]');
                        const articleId = parentArticle ? parentArticle.getAttribute('data-message-id') : null;
                        if (articleId) {
                            const root = parentArticle;
                            const inputs = Array.from(root.querySelectorAll('input[type="' + el.type + '"]'));
                            const index = inputs.indexOf(el);
                            el.setAttribute('data-stable-id', 'ag-stable-' + articleId + '-' + el.type + '-' + index);
                        }
                    }
                }

                const pos = window.getComputedStyle(el).position;
                if (pos === 'fixed' || pos === 'absolute') {
                    el.setAttribute('data-ag-rem', 'true');
                }
            } catch(e) {}
        });

        // Clone cascade to modify it without affecting the original
        const clone = cascade.cloneNode(true);
        
        // Clean up markers from the original DOM immediately after cloning
        candidates.forEach(el => el.removeAttribute('data-ag-rem'));
        
        // Aggressively remove the entire interaction/input/review area
        try {
            // 1. Identify common interaction wrappers by class combinations
            const interactionSelectors = [
                '.relative.flex.flex-col.gap-8',
                '.flex.grow.flex-col.justify-start.gap-8',
                'div[class*="interaction-area"]',
                '.p-1.bg-gray-500\\/10',
                '.outline-solid.justify-between',
                '[contenteditable="true"]',
                '[data-lexical-editor]',
                'form',
                // New aggressive selectors for recent Antigravity versions
                '.mx-8.mb-8',
                '.mx-4.mb-4',
                '.fixed.bottom-0',
                '.absolute.bottom-0',
                '#InputBox',
                '[class*="bg-gradient-to-"]'
            ];

            interactionSelectors.forEach(selector => {
                clone.querySelectorAll(selector).forEach(el => {
                    try {
                        // Protect elements that contain interactive buttons the user might need
                        const text = (el.innerText || '').toLowerCase();
                        const isActionArea = text.includes('allow') || text.includes('deny') || 
                                           text.includes('review') || text.includes('run') ||
                                           text.includes('confirm');
                        
                        // BUT: If it's specifically an input-related element, we DON'T protect it
                        const isEditor = el.getAttribute('contenteditable') === 'true' || 
                                       el.hasAttribute('data-lexical-editor') ||
                                       text.includes('ask anything') ||
                                       text.includes('to mention');
                        if (!isEditor && isActionArea && selector !== '[contenteditable="true"]' && selector !== '#InputBox') {
                            return; // Protect action bars
                        }

                        // For the editor or its container, remove it
                        // Go up to find the main floating box if it's a deep selector
                        let targetToRemove = el;
                        if (isEditor || selector.includes('bottom-0') || selector.includes('InputBox')) {
                             // Find the common container for the input box (usually has margins or padding)
                             let parent = el.parentElement;
                             for (let i = 0; i < 4; i++) {
                                 if (!parent || parent === clone) break;
                                 const pCls = (parent.className || '').toString();
                                 if (pCls.includes('mx-') || pCls.includes('mb-') || pCls.includes('bg-')) {
                                     targetToRemove = parent;
                                 }
                                 parent = parent.parentElement;
                             }
                        }
                        
                        if (targetToRemove && targetToRemove !== clone) {
                            targetToRemove.remove();
                        } else {
                            el.remove();
                        }
                    } catch(e) {}
                });
            });

            // 2. Text-based cleanup for stray status bars and redundant desktop inputs
            const allElements = clone.querySelectorAll('*');
            allElements.forEach(el => {
                try {
                    const text = (el.innerText || '').toLowerCase();
                    const placeholder = (el.getAttribute('placeholder') || '').toLowerCase();
                    const isInputPlaceholder = text.includes('ask anything') || 
                                              text.includes('to mention') || 
                                              placeholder.includes('ask anything');
                    
                    // IF it's the main chat box (contains placeholder text), remove its container
                    if (isInputPlaceholder) {
                        // Find the container (usually a few levels up)
                        let container = el;
                        for (let i = 0; i < 5; i++) {
                            if (!container.parentElement || container.parentElement === clone) break;
                            const cls = (container.className || '').toString();
                            if (cls.includes('flex-col') || cls.includes('input') || cls.includes('area')) {
                                container.remove();
                                return;
                            }
                            container = container.parentElement;
                        }
                        el.remove();
                        return;
                    }
                } catch(e) {}
            });

            // 3. NUCLEAR: If any editor or redundant UI remains, remove its entire branch
            const redundantElements = clone.querySelectorAll('[contenteditable="true"], [data-lexical-editor], [role="textbox"], form, .mx-8.mb-8, .mx-4.mb-4');
            redundantElements.forEach(el => {
                try {
                    let branch = el;
                    // Go up to find the highest container that is still within the clone
                    // This ensures we remove the entire "box" (with chips, submit btn, etc)
                    while (branch.parentElement && branch.parentElement !== clone) {
                        const p = branch.parentElement;
                        const pCls = (p.className || '').toString().toLowerCase();
                        // Stop going up if we hit a main message/conversation wrapper
                        if (pCls.includes('message') || pCls.includes('bubble') || pCls.includes('conversation')) break;
                        branch = p;
                    }
                    if (branch && branch !== clone) branch.remove();
                    else el.remove();
                } catch(e) {}
            });

            // 4. Force hide any fixed/absolute elements (desktop overlays)
            // These were marked in the original before cloning to ensure accurate computed styles
            clone.querySelectorAll('[data-ag-rem]').forEach(el => {
                try {
                    const text = (el.innerText || '').toLowerCase();
                    // Exclude Action Bars we want to keep
                    if (text.includes('allow') || text.includes('deny') || text.includes('review')) {
                        el.removeAttribute('data-ag-rem');
                        return;
                    }
                    el.remove();
                } catch(e) {}
            });
        } catch (globalErr) { }

        // Convert local images to base64
        const images = clone.querySelectorAll('img');
        const promises = Array.from(images).map(async (img) => {
            const rawSrc = img.getAttribute('src');
            if (rawSrc && (rawSrc.startsWith('/') || rawSrc.startsWith('vscode-file:')) && !rawSrc.startsWith('data:')) {
                try {
                    const res = await fetch(rawSrc);
                    const blob = await res.blob();
                    await new Promise(r => {
                        const reader = new FileReader();
                        reader.onloadend = () => { img.src = reader.result; r(); };
                        reader.onerror = () => r();
                        reader.readAsDataURL(blob);
                    });
                } catch(e) {}
            }
        });
        await Promise.all(promises);

        // Fix inline file references and text tokens: Antigravity nests <div> elements inside
        // <span> and <p> tags (e.g. file-type icons). Browsers auto-close <p> and
        // <span> when they encounter a <div>, causing unwanted line breaks.
        // Solution: Convert any <div> inside an inline parent to a <span>.
        try {
            const inlineTags = new Set(['SPAN', 'P', 'A', 'LABEL', 'EM', 'STRONG', 'CODE']);
            const allDivs = Array.from(clone.querySelectorAll('div'));
            for (const div of allDivs) {
                try {
                    if (!div.parentNode) continue;
                    const parent = div.parentElement;
                    if (!parent) continue;
                    
                    const parentIsInline = inlineTags.has(parent.tagName) || 
                        (parent.className && typeof parent.className === 'string' && (parent.className.includes('inline-flex') || parent.className.includes('inline-block') || parent.className.includes('inline'))) ||
                        (window.getComputedStyle && window.getComputedStyle(parent).display.includes('inline'));
                        
                    if (parentIsInline) {
                        const span = document.createElement('span');
                        // MOVE children instead of copying (prevents orphaning nested divs)
                        while (div.firstChild) {
                            span.appendChild(div.firstChild);
                        }
                        if (div.className) span.className = div.className;
                        if (div.getAttribute('style')) span.setAttribute('style', div.getAttribute('style'));
                        span.style.display = 'inline'; // Default to inline to preserve native text spacing. inline-flex collapses trailing spaces!
                        span.style.alignItems = 'center';
                        span.style.verticalAlign = 'middle';
                        div.replaceWith(span);
                    }
                } catch(e) {}
            }
        } catch(e) {}
        
        const html = clone.outerHTML;
        
        const rules = [];
        for (const sheet of document.styleSheets) {
            try {
                for (const rule of sheet.cssRules) {
                    // Strip :hover pseudo-classes to prevent double-tap issues on mobile devices
                    if (rule.cssText.includes(':hover')) {
                        rules.push(rule.cssText.replace(/:hover/g, '.ag-hover-disabled'));
                    } else {
                        rules.push(rule.cssText);
                    }
                }
            } catch (e) { }
        }
        const allCSS = rules.join(' ') + 
            ' button[aria-label="Good response"], button[aria-label="Bad response"] { opacity: 1 !important; transition: all 0.2s ease-in-out !important; }' +
            ' button.active-thumb, button.active-thumb svg { color: #3b82f6 !important; fill: currentColor !important; transition: all 0.2s ease-in-out !important; }' +
            ' .conversation-button-group { display: none !important; }' +
            ' div[class*="bg-sidebar"] { display: none !important; width: 0 !important; }' +
            ' div[style*=" width: 256px;"] { display: none !important; width: 0 !important; }' +
            ' :root { --sidebar-width: 0px !important; --aux-pane-width: 0px !important; }';
        
        return {
            html: html,
            css: allCSS,
            backgroundColor: cascadeStyles.backgroundColor,
            color: cascadeStyles.color,
            fontFamily: cascadeStyles.fontFamily,
            scrollInfo: scrollInfo,
            isGenerating: (function() {
                const els = document.querySelectorAll('[data-testid="agent-loading"]');
                for (let el of els) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        return true;
                    }
                }
                return false;
            })(),
            stats: {
                nodes: clone.getElementsByTagName('*').length,
                htmlSize: html.length,
                cssSize: allCSS.length
            }
        };
    })()`;

    for (const ctx of cdp.contexts) {
        try {
            // console.log(`Trying context ${ctx.id} (${ctx.name || ctx.origin})...`);
            const result = await cdp.call("Runtime.evaluate", {
                expression: CAPTURE_SCRIPT,
                returnByValue: true,
                awaitPromise: true,
                /* contextId: ctx.id */
            });

            if (result.exceptionDetails) {
                console.log(`Context ${ctx.id} exception:`, JSON.stringify(result.exceptionDetails));
                continue;
            }

            if (result.result && result.result.value) {
                const val = result.result.value;
                if (val.error) {
                    console.log(`Context ${ctx.id} script error:`, val.error);
                    if (val.debug) console.log(`   Debug info:`, JSON.stringify(val.debug));
                } else {
                    return val;
                }
            }
        } catch (e) {
            console.log(`Context ${ctx.id} connection error:`, e.message);
        }
    }

    return null;
}

// Inject message into Antigravity
async function injectMessage(cdp, text) {
    // Use JSON.stringify for robust escaping (handles ", \, newlines, backticks, unicode, etc.)
    const safeText = JSON.stringify(text);

    const EXPRESSION = `(async () => {
        const textToInsert = ${safeText};
        const isModalOpen = document.querySelectorAll('[role="dialog"], [role="alertdialog"], [aria-modal="true"]').length > 0;
        
        let radioClicked = false;
        if (isModalOpen && /^\\d+$/.test(textToInsert.trim())) {
            const index = parseInt(textToInsert.trim(), 10) - 1;
            const radios = Array.from(document.querySelectorAll('[role="dialog"] input[type="radio"], [aria-modal="true"] input[type="radio"]'));
            if (radios[index]) {
                const radio = radios[index];
                const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'checked')?.set;
                if (nativeInputValueSetter) {
                    nativeInputValueSetter.call(radio, true);
                } else {
                    radio.checked = true;
                }
                radio.dispatchEvent(new Event('input', { bubbles: true }));
                radio.dispatchEvent(new Event('change', { bubbles: true }));
                radio.click();
                radioClicked = true;
            }
        }
        
        if (!radioClicked) {
            let editors = [];
            
            if (isModalOpen) {
                // Target the write-in input/textarea in the modal. Catch inputs without explicit type attribute
                editors = [...document.querySelectorAll('[role="dialog"] input:not([type="radio"]):not([type="checkbox"]), [role="dialog"] textarea, [aria-modal="true"] input:not([type="radio"]):not([type="checkbox"]), [aria-modal="true"] textarea, [role="dialog"] [contenteditable="true"]')]
                    .filter(el => el.offsetParent !== null);
            }
            
            if (editors.length === 0) {
                // Fallback to main chat inputs
                editors = [...document.querySelectorAll('textarea, input:not([type="radio"]):not([type="checkbox"]), [data-testid="conversation-view"] [contenteditable="true"], #root [contenteditable="true"], .overflow-y-auto [contenteditable="true"]')]
                    .filter(el => el.offsetParent !== null);
            }

            const editor = editors.at(-1);
            if (!editor) return { ok:false, error:"editor_not_found" };

            editor.focus();

            if (editor.tagName === 'INPUT' || editor.tagName === 'TEXTAREA') {
                editor.value = textToInsert;
                editor.dispatchEvent(new Event("input", { bubbles: true }));
                editor.dispatchEvent(new Event("change", { bubbles: true }));
            } else {
                document.execCommand?.("selectAll", false, null);
                document.execCommand?.("delete", false, null);

                let inserted = false;
                try { inserted = !!document.execCommand?.("insertText", false, textToInsert); } catch {}
                if (!inserted) {
                    editor.textContent = textToInsert;
                    editor.dispatchEvent(new InputEvent("beforeinput", { bubbles:true, inputType:"insertText", data: textToInsert }));
                    editor.dispatchEvent(new InputEvent("input", { bubbles:true, inputType:"insertText", data: textToInsert }));
                }
            }
        }

        // Wait for React to re-render the Submit button (give it up to 150ms)
        await new Promise(r => setTimeout(r, 150));

        let submit = null;
        if (isModalOpen) {
            // Find "Submit" button in modal
            const modalBtns = Array.from(document.querySelectorAll('[role="dialog"] button, [aria-modal="true"] button'));
            submit = modalBtns.find(b => {
                const txt = (b.innerText || '').trim().toLowerCase();
                return txt === 'submit' || txt === 'send' || txt === 'proceed' || txt === 'confirm' || !!b.querySelector('svg.lucide-send, svg.lucide-arrow-right');
            });
        }

        if (!submit) {
            submit = document.querySelector('[data-tooltip-id="input-send-button-tooltip"]') 
                  || document.querySelector('[data-tooltip-id="send-button-tooltip"]')
                  || document.querySelector('button[aria-label="Send Message"]')
                  || document.querySelector('button[aria-label="Send"]')
                  || document.querySelector("svg.lucide-arrow-right")?.closest("button")
                  || document.querySelector("svg.lucide-arrow-up")?.closest("button")
                  || document.querySelector("svg.lucide-send")?.closest("button");
        }

        if (submit && !submit.disabled) {
            submit.click();
            return { ok:true, method:"click_submit", isModal: isModalOpen, radioClicked };
        }

        // Submit button not found or disabled - tell the backend to use CDP to press Enter
        return { ok:true, method:"needs_cdp_enter", submit_button_found: !!submit, submit_disabled: submit ? submit.disabled : null, isModal: isModalOpen, radioClicked };
    })()`;

    for (const ctx of cdp.contexts) {
        try {
            const result = await cdp.call("Runtime.evaluate", {
                expression: EXPRESSION,
                returnByValue: true,
                awaitPromise: true,
                /* contextId: ctx.id */
            });

            if (result.result && result.result.value) {
                const val = result.result.value;
                if (val.method === "needs_cdp_enter") {
                    // Dispatch a real browser Enter key event
                    await cdp.call("Input.dispatchKeyEvent", { type: "keyDown", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13, text: "\r" });
                    await cdp.call("Input.dispatchKeyEvent", { type: "keyUp", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 });
                    val.method = "cdp_enter";
                }
                return val;
            }
        } catch (e) { }
    }

    return { ok: false, reason: "no_context" };
}

// Set functionality mode (Fast vs Planning)
async function setMode(cdp, mode) {
    if (!['Fast', 'Planning'].includes(mode)) return { error: 'Invalid mode' };

    const EXP = `(async () => {
        try {
            // STRATEGY: Find the element that IS the current mode indicator.
            // It will have text 'Fast' or 'Planning'.
            // It might not be a <button>, could be a <div> with cursor-pointer.
            
            // 1. Get all elements with text 'Fast' or 'Planning'
            const allEls = Array.from(document.querySelectorAll('*'));
            const candidates = allEls.filter(el => {
                // Must have single text node child to avoid parents
                if (el.children.length > 0) return false;
                const txt = el.textContent.trim();
                return txt === 'Fast' || txt === 'Planning';
            });

            // 2. Find the one that looks interactive (cursor-pointer)
            // Traverse up from text node to find clickable container
            let modeBtn = null;
            
            for (const el of candidates) {
                let current = el;
                // Go up max 4 levels
                for (let i = 0; i < 4; i++) {
                    if (!current) break;
                    const style = window.getComputedStyle(current);
                    if (style.cursor === 'pointer' || current.tagName === 'BUTTON') {
                        modeBtn = current;
                        break;
                    }
                    current = current.parentElement;
                }
                if (modeBtn) break;
            }

            if (!modeBtn) return { error: 'Mode indicator/button not found' };

            // Check if already set
            if (modeBtn.innerText.includes('${mode}')) return { success: true, alreadySet: true };

            // 3. Click to open menu
            modeBtn.click();
            await new Promise(r => setTimeout(r, 600));

            // 4. Find the dialog
            let visibleDialog = Array.from(document.querySelectorAll('[role="dialog"]'))
                                    .find(d => d.offsetHeight > 0 && d.innerText.includes('${mode}'));
            
            // Fallback: Just look for any new visible container if role=dialog is missing
            if (!visibleDialog) {
                // Maybe it's not role=dialog? Look for a popover-like div
                 visibleDialog = Array.from(document.querySelectorAll('div'))
                    .find(d => {
                        const style = window.getComputedStyle(d);
                        return d.offsetHeight > 0 && 
                               (style.position === 'absolute' || style.position === 'fixed') && 
                               d.innerText.includes('${mode}') &&
                               !d.innerText.includes('Files With Changes'); // Anti-context menu
                    });
            }

            if (!visibleDialog) return { error: 'Dropdown not opened or options not visible' };

            // 5. Click the option
            const allDialogEls = Array.from(visibleDialog.querySelectorAll('*'));
            const target = allDialogEls.find(el => 
                el.children.length === 0 && el.textContent.trim() === '${mode}'
            );

            if (target) {
                target.click();
                await new Promise(r => setTimeout(r, 200));
                return { success: true };
            }
            
            return { error: 'Mode option text not found in dialog. Dialog text: ' + visibleDialog.innerText.substring(0, 50) };

        } catch(err) {
            return { error: 'JS Error: ' + err.toString() };
        }
    })()`;

    for (const ctx of cdp.contexts) {
        try {
            const res = await cdp.call("Runtime.evaluate", {
                expression: EXP,
                returnByValue: true,
                awaitPromise: true,
                /* contextId: ctx.id */
            });
            if (res.result?.value) return res.result.value;
        } catch (e) { }
    }
    return { error: 'Context failed' };
}

// Stop Generation
async function stopGeneration(cdp) {
    try {
        console.log('[Stop] Clicking Stop button in DOM to abort generation...');
        const result = await cdp.call('Runtime.evaluate', {
            expression: `
                (function() {
                    // Try to find the Stop Task button or any button with a square SVG that indicates 'Stop'
                    const stopBtns = Array.from(document.querySelectorAll('button'));
                    let clicked = false;
                    for (const btn of stopBtns) {
                        // Check if it's a stop task button by its tooltip ID or if it has a square SVG path
                        const tooltipId = btn.getAttribute('data-tooltip-id');
                        const hasSquareSvg = btn.querySelector('svg path[d^="M330-330H630V-630H330v300Z"]') || btn.querySelector('svg.lucide-square');
                        
                        if ((tooltipId && tooltipId.startsWith('stop-task-')) || hasSquareSvg) {
                            btn.click();
                            clicked = true;
                        }
                    }
                    
                    // If no explicit stop button, look for the 'Cancel (Ctrl+D)' button ONLY if there's an active generation
                    if (!clicked) {
                        const isGenerating = !!document.querySelector('[data-testid="agent-loading"]');
                        if (isGenerating) {
                            const cancelBtn = document.querySelector('button[aria-label="Cancel (Ctrl+D)"]');
                            if (cancelBtn) {
                                cancelBtn.click();
                                clicked = true;
                            }
                        }
                    }
                    
                    return clicked;
                })()
            `,
            returnByValue: true
        });
        
        console.log('[Stop] Stop button clicked:', result.result.value);
        return { success: result.result.value };
    } catch (e) {
        console.error('[Stop] Failed to click stop button:', e);
        return { success: false, error: e.toString() };
    }
}


// Click Element (Remote)
async function clickElement(cdp, { id, selector, index, textContent }) {
    const safeText = JSON.stringify(textContent || '');

    const EXP = `(async () => {
        try {
            // Priority: Search inside the exact same chat container that the snapshot uses for perfect index alignment
            const root = document.querySelector('[data-testid="conversation-view"]') || document.getElementById('conversation') || document.getElementById('chat') || document.getElementById('cascade') || document;
            let target = null;
            let elements = [];
            
            if ('${id}' !== 'undefined' && '${id}') {
                target = root.querySelector('[data-ag-id="${id}"]');
            }
            
            if (!target) {
                // Fallback: Find all elements matching the selector
                try {
                    elements = Array.from(root.querySelectorAll('${selector}'));
                } catch(e) {}
                
                const filterText = ${safeText};
                if (filterText && elements.length > 0) {
                    elements = elements.filter(el => {
                        const txt = (el.innerText || el.textContent || el.getAttribute('aria-label') || el.getAttribute('title') || '').trim();
                        const firstLine = txt.split('\\n')[0].trim();
                        return firstLine === filterText || txt.includes(filterText);
                    });
                    
                    elements = elements.filter(el => {
                        return !elements.some(other => other !== el && el.contains(other));
                    });
                }
    
                target = elements[${index}];
            }

            if (target) {
                // Focus element
                if (target.focus) target.focus();
                
                // Ensure it's in the viewport before taking coordinates
                if (target.scrollIntoView) {
                    target.scrollIntoView({ behavior: 'instant', block: 'center', inline: 'center' });
                }

                // Get rect to perform hardware click
                const rect = target.getBoundingClientRect();
                return { 
                    success: true, 
                    found: elements.length, 
                    indexUsed: ${index}, 
                    idUsed: '${id}',
                    rect: {
                        x: rect.left + (rect.width / 2),
                        y: rect.top + (rect.height / 2)
                    }
                };
            }
            return { error: 'Element not found' };
        } catch(e) {
            return { error: e.message || e.toString(), stack: e.stack };
        }
    })();`;

    try {
        const res = await cdp.call("Runtime.evaluate", {
            expression: EXP,
            returnByValue: true,
            awaitPromise: true
        });
        
        if (res.result && res.result.value && res.result.value.success && res.result.value.rect) {
            const { x, y } = res.result.value.rect;
            const centerX = Math.round(x);
            const centerY = Math.round(y);
            
            // Trigger hover state first
            await cdp.call('Input.dispatchMouseEvent', {
                type: 'mouseMoved',
                x: centerX,
                y: centerY
            });
            await new Promise(r => setTimeout(r, 100));

            // Perform true hardware click via CDP (isTrusted=true)
            await cdp.call('Input.dispatchMouseEvent', {
                type: 'mousePressed',
                button: 'left',
                x: centerX,
                y: centerY,
                clickCount: 1
            });
            await new Promise(r => setTimeout(r, 50));
            await cdp.call('Input.dispatchMouseEvent', {
                type: 'mouseReleased',
                button: 'left',
                x: centerX,
                y: centerY,
                clickCount: 1
            });
            
            return res.result.value;
        }
        
        return res.result?.value || { error: 'Evaluate failed' };
    } catch (e) {
        console.error("CDP ERROR in clickElement:", e);
        return { error: JSON.stringify(e) };
    }
}

// Remote scroll - sync phone scroll to desktop
async function remoteScroll(cdp, { scrollTop, scrollPercent }) {
    // Try to scroll the chat container in Antigravity
    const EXPRESSION = `(async () => {
        try {
            // Find the main scrollable chat container
            const scrollables = [...document.querySelectorAll('[data-testid="conversation-view"] [class*="scroll"], #root [class*="scroll"], .overflow-y-auto [class*="scroll"], [data-testid="conversation-view"] [style*="overflow"], #root [style*="overflow"], .overflow-y-auto [style*="overflow"]')]
                .filter(el => el.scrollHeight > el.clientHeight);
            
            // Also check for the main chat area
            const chatArea = document.querySelector('[data-testid="conversation-view"] .overflow-y-auto, #root .overflow-y-auto, .overflow-y-auto .overflow-y-auto, [data-testid="conversation-view"] [data-scroll-area], #root [data-scroll-area], .overflow-y-auto [data-scroll-area]');
            if (chatArea) scrollables.unshift(chatArea);
            
            if (scrollables.length === 0) {
                // Fallback: scroll the main container element
                const cascade = document.querySelector('[data-testid="conversation-view"]') || document.getElementById('root');
                if (cascade && cascade.scrollHeight > cascade.clientHeight) {
                    scrollables.push(cascade);
                }
            }
            
            if (scrollables.length === 0) return { error: 'No scrollable element found' };
            
            const target = scrollables[0];
            
            // Use percentage-based scrolling for better sync
            if (${scrollPercent} !== undefined) {
                const maxScroll = target.scrollHeight - target.clientHeight;
                target.scrollTop = maxScroll * ${scrollPercent};
                if (${scrollPercent} <= 0.01 || target.scrollTop < 50) {
                    const loadBtn = document.querySelector('[aria-label^="Load older messages"]');
                    if (loadBtn) loadBtn.click();
                }
            } else {
                target.scrollTop = ${scrollTop || 0};
            }
            target.dispatchEvent(new Event('scroll', {bubbles: true}));
            
            return { success: true, scrolled: target.scrollTop };
        } catch(e) {
            return { error: e.toString() };
        }
    })()`;

    for (const ctx of cdp.contexts) {
        try {
            const res = await cdp.call("Runtime.evaluate", {
                expression: EXPRESSION,
                returnByValue: true,
                awaitPromise: true,
                /* contextId: ctx.id */
            });
            if (res.result?.value?.success) return res.result.value;
        } catch (e) { }
    }
    return { error: 'Scroll failed in all contexts' };
}

// Set AI Model
async function setModel(cdp, modelName) {
    const EXP = `(async () => {
        try {
            const KNOWN_KEYWORDS = ["Gemini", "Claude", "GPT", "Model"];
            
            // 1. Strict Exact Match (The model button is in the top header and has aria-label="Select model...")
            let modelBtn = document.querySelector('button[aria-label^="Select model"]');
            
            // 2. Fallback: Any button with a dialog popup that contains model keywords
            if (!modelBtn) {
                const buttons = Array.from(document.querySelectorAll('button[aria-haspopup="dialog"], button[aria-haspopup="listbox"], button[aria-haspopup="menu"]'));
                modelBtn = buttons.find(btn => {
                    const txt = btn.innerText || btn.textContent || '';
                    return KNOWN_KEYWORDS.some(k => txt.includes(k));
                });
            }
            
            // 3. Fallback: Any button in the top 150px of the screen that contains model keywords
            if (!modelBtn) {
                const topButtons = Array.from(document.querySelectorAll('button')).filter(btn => {
                    const rect = btn.getBoundingClientRect();
                    return rect.top >= 0 && rect.top < 150 && rect.width > 0 && rect.height > 0;
                });
                modelBtn = topButtons.find(btn => {
                    const txt = btn.innerText || btn.textContent || '';
                    return KNOWN_KEYWORDS.some(k => txt.includes(k));
                });
            }

            if (!modelBtn) return { error: 'Model selector button not found' };
            
            // CRITICAL SAFETY CHECK: Never click a link or something in a navigation sidebar
            if (modelBtn.closest('a') || modelBtn.closest('nav') || modelBtn.closest('aside')) {
                return { error: 'Found model button inside a link or sidebar, rejected to prevent unwanted navigation.' };
            }

            // Click execution with MouseEvent fallback
            const executeClick = (targetEl) => {
                const events = ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'];
                events.forEach(type => {
                    targetEl.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
                });
            };

            // Click to open menu
            executeClick(modelBtn);
            
            // Poll for up to 2 seconds for the dropdown
            let visibleDialog = null;
            const baseName = '${modelName}'.split(' ')[0];
            
            for (let i = 0; i < 10; i++) {
                await new Promise(r => setTimeout(r, 200));
                
                const allDivs = Array.from(document.querySelectorAll('[role="dialog"], [role="listbox"], [role="menu"], [data-radix-popper-content-wrapper], div'));
                const candidates = allDivs.filter(d => {
                    if (d.offsetHeight === 0) return false;
                    const style = window.getComputedStyle(d);
                    const isPositioned = style.position === 'absolute' || style.position === 'fixed';
                    const isRadix = d.hasAttribute('data-radix-popper-content-wrapper') || 
                                    d.getAttribute('role') === 'dialog' || 
                                    d.getAttribute('role') === 'menu' || 
                                    d.getAttribute('role') === 'listbox';
                    
                    if (!isPositioned && !isRadix) return false;
                    
                    // Ignore large containers (like sidebar or main app)
                    if (d.offsetWidth > window.innerWidth * 0.6) return false;
                    if (d.offsetHeight >= window.innerHeight * 0.95) return false;
                    
                    return d.innerText?.includes(baseName) && !d.innerText?.includes('Files With Changes');
                });
                      if (candidates.length > 0) {
                    candidates.sort((a, b) => (parseInt(window.getComputedStyle(b).zIndex) || 0) - (parseInt(window.getComputedStyle(a).zIndex) || 0));
                    visibleDialog = candidates[0];
                    break;
                }
            }

            if (!visibleDialog) return { error: 'Model list not opened' };

            const allDialogEls = Array.from(visibleDialog.querySelectorAll('*'));
            const validEls = allDialogEls.filter(el => el.children.length === 0 && el.textContent?.trim().length > 0);
            
            // A. Exact Match (Best)
            let target = validEls.find(el => el.textContent.trim() === '${modelName}');
            
            // B. Page contains Model
            if (!target) {
                target = validEls.find(el => el.textContent.includes('${modelName}'));
            }

            // C. Closest partial match
            if (!target) {
                const partialMatches = validEls.filter(el => '${modelName}'.includes(el.textContent.trim()));
                if (partialMatches.length > 0) {
                    partialMatches.sort((a, b) => b.textContent.trim().length - a.textContent.trim().length);
                    target = partialMatches[0];
                }
            }

            if (target) {
                target.scrollIntoView({block: 'center'});
                executeClick(target);
                await new Promise(r => setTimeout(r, 200));
                return { success: true };
            }

            return { error: 'Model "${modelName}" not found in list. Visible: ' + visibleDialog.innerText.substring(0, 100) };
        } catch(err) {
            return { error: 'JS Error: ' + err.toString() };
        }
    })()`;

    for (const ctx of cdp.contexts) {
        try {
            const res = await cdp.call("Runtime.evaluate", {
                expression: EXP,
                returnByValue: true,
                awaitPromise: true,
                /* contextId: ctx.id */
            });
            if (res.result?.value) return res.result.value;
        } catch (e) { }
    }
    return { error: 'Context failed' };
}

// Start New Chat - Click the + button at the TOP of the chat window (NOT the context/media + button)
async function startNewChat(cdp, workspace = null) {
    const EXP = `(async () => {
        try {
            if (${JSON.stringify(workspace)}) {
                const ws = ${JSON.stringify(workspace)};
                const btns = Array.from(document.querySelectorAll('[aria-label="New Conversation in Project"]'));
                const foundBtn = btns.find(btn => {
                    const group = btn.closest('.group\\\\/section') || btn.closest('div');
                    if (group && group.firstElementChild) {
                        return group.firstElementChild.textContent.includes(ws);
                    }
                    return false;
                });
                
                if (foundBtn) {
                    foundBtn.click();
                    return { success: true, method: 'workspace-specific' };
                }
            }

            // Unscoped or fallback
            const exactBtn = document.querySelector('[aria-label="New Conversation"]');
            if (exactBtn) {
                exactBtn.click();
                return { success: true, method: 'aria_label_new' };
            }

            // Fallback: Use previous heuristics
            const allButtons = Array.from(document.querySelectorAll('button, [role="button"], a'));
            
            // Find all buttons with plus icons
            const plusButtons = allButtons.filter(btn => {
                if (btn.offsetParent === null) return false; // Skip hidden
                const hasPlusIcon = btn.querySelector('svg.lucide-plus') || 
                                   btn.querySelector('svg.lucide-square-plus') ||
                                   btn.querySelector('svg[class*="plus"]');
                return hasPlusIcon;
            });
            
            // Filter only top buttons (toolbar area)
            const topPlusButtons = plusButtons.filter(btn => {
                const rect = btn.getBoundingClientRect();
                return rect.top < 200;
            });

            if (topPlusButtons.length > 0) {
                 topPlusButtons.sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
                 topPlusButtons[0].click();
                 return { success: true, method: 'filtered_top_plus', count: topPlusButtons.length };
            }
            
            // Fallback: aria-label
             const newChatBtn = allButtons.find(btn => {
                const ariaLabel = btn.getAttribute('aria-label')?.toLowerCase() || '';
                const title = btn.getAttribute('title')?.toLowerCase() || '';
                return (ariaLabel.includes('new') || title.includes('new')) && btn.offsetParent !== null;
            });
            
            if (newChatBtn) {
                newChatBtn.click();
                return { success: true, method: 'aria_label_new' };
            }
            
            return { error: 'New chat button not found' };
        } catch(e) {
            return { error: e.toString() };
        }
    })()`;

    for (const ctx of cdp.contexts) {
        try {
            const res = await cdp.call("Runtime.evaluate", {
                expression: EXP,
                returnByValue: true,
                awaitPromise: true,
                /* contextId: ctx.id */
            });
            if (res.result?.value?.success) return res.result.value;
        } catch (e) { }
    }
    return { error: 'Context failed' };
}
let globalHistoryCache = [];

// Get Chat History - Scrape directly from sidebar convo pills
async function getChatHistory(cdp) {
    const EXP = `(async () => {
        try {
            const chats = [];
            const seenTitles = new Set();
            
            const elements = Array.from(document.querySelectorAll('h2, div.text-sm.font-medium.truncate.m-0, span[data-testid^="convo-pill-"]'));
            let currentSection = '';
            let currentGroup = 'Projects';
            let pillsCount = 0;
            const logLines = [];
            
            for (const el of elements) {
                if (el.tagName === 'H2') {
                    currentSection = el.textContent?.trim() || '';
                    currentGroup = ''; // Reset group on new H2 section
                } else if (el.tagName === 'DIV') {
                    currentGroup = el.textContent?.trim() || '';
                } else if (el.tagName === 'SPAN') {
                    pillsCount++;
                    let text = el.textContent?.trim() || '';
                    if (text.length < 3) continue;
                    
                    const testId = el.getAttribute('data-testid') || text;
                    if (seenTitles.has(testId)) continue;
                    
                    if (text === 'New Chat' || 
                        /(You are the|Review the|Please review|Please query|Your objective|Created At:|Call the MCP|I have drafted|Just reply|Review the plan|Review the implementation|You are a JS Style|Review the modifications)/i.test(text) ||
                        text.length < 5) {
                        continue;
                    }
                    
                    seenTitles.add(testId);
                    
                    let pillWorkspace = 'Global';
                    let isPinned = false;
                    
                    if (currentSection.toLowerCase().includes('pinned')) {
                        isPinned = true;
                    } else if (currentSection.toLowerCase().includes('project')) {
                        pillWorkspace = currentGroup || 'Unknown Project';
                    }
                    
                    // Extract just the project folder name if it's an absolute path
                    if (pillWorkspace.includes('\\\\') || pillWorkspace.includes('/')) {
                        const parts = pillWorkspace.replace(/\\\\/g, '/').split('/');
                        pillWorkspace = parts[parts.length - 1];
                    }
                    
                    logLines.push({ originalText: el.textContent, parsedTitle: text, section: currentSection, group: currentGroup, workspace: pillWorkspace, isPinned, id: testId });
                    chats.push({ title: text, workspace: pillWorkspace, date: 'Recent', isPinned, id: testId });
                    if (chats.length >= 200) break;
                }
            }
            
            console.log("CHATS PARSED:", JSON.stringify(chats, null, 2));
            
            const debugInfo = {
                pillsFound: pillsCount,
                elementsFound: elements.length,
                logLines: logLines
            };

            return { success: true, chats: chats, debug: debugInfo };
        } catch(e) {
            return { error: e.toString(), chats: [] };

        }
    })()`;

    let lastError = null;
    for (const ctx of cdp.contexts) {
        try {
            const res = await cdp.call("Runtime.evaluate", {
                expression: EXP,
                returnByValue: true,
                awaitPromise: true,
                /* contextId: ctx.id */
            });
            if (res.result?.value?.success) {
                const scrapedChats = res.result.value.chats || [];
                const merged = [...scrapedChats];
                

                
                globalHistoryCache.forEach(cached => {
                    if (!merged.find(m => m.id === cached.id)) {
                        merged.push(cached);
                    }
                });
                
                merged.sort((a, b) => {
                    if (a.date === 'Recent' && b.date !== 'Recent') return -1;
                    if (b.date === 'Recent' && a.date !== 'Recent') return 1;
                    if (a.date === 'Older' && b.date !== 'Older') return 1;
                    if (b.date === 'Older' && a.date !== 'Older') return -1;
                    
                    const timeA = new Date(a.date).getTime() || 0;
                    const timeB = new Date(b.date).getTime() || 0;
                    return timeB - timeA;
                });
                
                globalHistoryCache = merged;
                return { success: true, chats: globalHistoryCache, debug: res.result.value.debug };
            }
            // If result.value is null/undefined but no error thrown, check exceptionDetails
            if (res.result?.exceptionDetails) {
                lastError = res.result.exceptionDetails.exception?.description || 'Unknown CDP exception';
            }
        } catch (e) {
            lastError = e.toString();
        }
    }
    return { error: lastError || 'Context failed', chats: globalHistoryCache };
}

async function loadMoreHistory(cdp) {
    const EXP = `(async () => {
        try {
            const scroller = document.querySelector('.overflow-y-auto') || document.querySelector('[data-testid="conversation-history-list"]');
            if (!scroller) return { error: 'No scroller found' };
            
            scroller.scrollTop += scroller.clientHeight * 0.8;
            return { success: true };
        } catch(e) {
            return { error: e.toString() };
        }
    })()`;
    
    for (const ctx of cdp.contexts) {
        try {
            const res = await cdp.call("Runtime.evaluate", {
                expression: EXP,
                returnByValue: true,
                awaitPromise: true,
            });
            if (res.result?.value?.success) return res.result.value;
        } catch (e) {
            console.error('Failed to run loadMoreHistory evaluation in context:', e);
        }
    }
    return { error: 'Failed to scroll history' };
}

async function selectChat(cdp, chatTitle) {
    const safeChatTitle = JSON.stringify(chatTitle);

    const EXP = `(async () => {
        try {
            const targetTitle = ${safeChatTitle};
            let debugInfo = [];
            const log = (msg) => debugInfo.push(msg);
            log('Starting selectChat for: ' + targetTitle);

            // 1. Check if drawer is already open by looking for pills
            let pills = Array.from(document.querySelectorAll('span[data-testid^="convo-pill-"]'));
            
            if (pills.length === 0) {
                const drawerBtn = document.querySelector('button[aria-label="History"], [data-testid="history-drawer-toggle"]');
                if (drawerBtn) {
                    drawerBtn.click();
                    log('Clicked history button');
                    await new Promise(r => setTimeout(r, 600));
                } else {
                    log('History button not found, assuming drawer is open or missing');
                }
            }

            // Use document body instead of trying to find a fixed panel
            const searchContext = document.body;

            // 3. Scored fuzzy matching
            let candidates = Array.from(searchContext.querySelectorAll('span, p, div'))
                .filter(el => {
                    const text = el.textContent?.trim() || '';
                    return text.length >= 3 && el.children.length === 0 && el.offsetParent !== null;
                })
                .map(el => {
                    const text = el.textContent.trim();
                    const targetLower = targetTitle.toLowerCase();
                    const textLower = text.toLowerCase();

                    let score = 0;
                    if (text === targetTitle) score += 100;
                    else if (textLower === targetLower) score += 90;
                    else if (text.includes(targetTitle)) score += 60;
                    else if (textLower.includes(targetLower)) score += 50;
                    else if (targetLower.includes(textLower)) score += 40;
                    else if (textLower.startsWith(targetLower.substring(0, Math.min(20, targetLower.length)))) score += 30;

                    // Penalty for tiny labels/tags
                    if (text.length < 5) score -= 10;

                    // Bonus for deeper nodes (usually more specific)
                    let depth = 0;
                    let p = el;
                    while (p) { depth++; p = p.parentElement; }
                    score += depth;

                    return { el, text, score };
                })
                .filter(c => c.score >= 30)
                .sort((a, b) => b.score - a.score);

            if (candidates.length === 0) return { error: 'Chat title not found in panel', title: targetTitle, debug: debugInfo };

            log('Found ' + candidates.length + ' candidates. Best match: "' + candidates[0].text + '" (Score: ' + candidates[0].score + ')');

            // 4. Click execution with MouseEvent fallback
            const executeClick = (targetEl) => {
                let clickable = targetEl;
                let foundClickable = false;

                for (let i = 0; i < 5; i++) {
                    if (!clickable) break;
                    const style = window.getComputedStyle(clickable);
                    if (style.cursor === 'pointer' || clickable.tagName === 'BUTTON' || clickable.onclick) {
                        foundClickable = true;
                        break;
                    }
                    if (clickable.parentElement) clickable = clickable.parentElement;
                }

                const finalTarget = foundClickable ? clickable : targetEl;
                finalTarget.click();

                try {
                    const rect = finalTarget.getBoundingClientRect();
                    const centerX = rect.left + (rect.width / 2);
                    const centerY = rect.top + (rect.height / 2);
                    const events = ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'];
                    events.forEach(type => {
                        finalTarget.dispatchEvent(new MouseEvent(type, {
                            view: window,
                            bubbles: true,
                            cancelable: true,
                            clientX: centerX,
                            clientY: centerY,
                            button: 0
                        }));
                    });
                } catch (e) {
                    log('MouseEvent fallback failed: ' + e.message);
                }
            };

            executeClick(candidates[0].el);
            log('Executed click on candidate 0');

            // 5. Wait a moment to ensure click processed
            await new Promise(r => setTimeout(r, 1000));

            // Ensure drawer closes by hitting Escape
            document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true }));
            document.dispatchEvent(new KeyboardEvent('keyup', { key: 'Escape', code: 'Escape', bubbles: true }));

            return { success: true, method: 'heuristic_click', bestMatch: candidates[0].text, retried: false, debug: debugInfo };
        } catch (e) {
            return { error: 'JS Exception: ' + e.toString() };
        }
    })()`;

    for (const ctx of cdp.contexts) {
        try {
            const res = await cdp.call("Runtime.evaluate", {
                expression: EXP,
                returnByValue: true,
                awaitPromise: true,
                /* contextId: ctx.id */
            });
            if (res.result?.value) return res.result.value;
        } catch (e) { }
    }
    return { error: 'Context failed' };
}

// Close History Panel (Escape)
async function closeHistory(cdp) {
    const EXP = `(async () => {
        try {
            const closeBtn = document.querySelector('button[aria-label="Close"]');
            if (closeBtn) {
                closeBtn.click();
                return { success: true };
            }
            const drawerBtn = document.querySelector('button[aria-label="History"], [data-testid="history-drawer-toggle"]');
            if (drawerBtn && (drawerBtn.getAttribute('aria-expanded') === 'true' || drawerBtn.getAttribute('data-state') === 'open')) {
                drawerBtn.click();
                return { success: true };
            }
            document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true }));
            document.dispatchEvent(new KeyboardEvent('keyup',   { key: 'Escape', code: 'Escape', bubbles: true }));
            return { success: true };
        } catch(e) {
            return { error: e.toString() };
        }
    })()`;

    for (const ctx of cdp.contexts) {
        try {
            const res = await cdp.call("Runtime.evaluate", {
                expression: EXP,
                returnByValue: true,
                awaitPromise: true,
                /* contextId: ctx.id */
            });
            if (res.result?.value?.success) return res.result.value;
        } catch (e) { }
    }
    return { error: 'Failed to close history panel' };
}

// Check if a chat is currently open (has cascade element)
async function hasChatOpen(cdp) {
    const EXP = `(() => {
    const chatContainer = document.querySelector('[data-testid="conversation-view"]') || document.getElementById('root');
    const hasMessages = chatContainer && chatContainer.querySelectorAll('[class*="message"], [data-message], [role="article"]').length > 0;
    return {
        hasChat: !!chatContainer,
        hasMessages: hasMessages,
        editorFound: !!document.querySelector('[contenteditable="true"]')
    };
})()`;

    for (const ctx of cdp.contexts) {
        try {
            const res = await cdp.call("Runtime.evaluate", {
                expression: EXP,
                returnByValue: true,
                /* contextId: ctx.id */
            });
            if (res.result?.value) return res.result.value;
        } catch (e) { }
    }
    return { hasChat: false, hasMessages: false, editorFound: false };
}

// Get App State (Mode & Model)
async function getAppState(cdp) {
    const EXP = `(async () => {
    try {
        const state = { mode: 'Unknown', model: 'Unknown' };

        // 1. Get Mode (Fast/Planning)
        // Strategy: Find the clickable mode button which contains either "Fast" or "Planning"
        // It's usually a button or div with cursor:pointer containing the mode text
        const allEls = Array.from(document.querySelectorAll('*'));

        // Find elements that are likely mode buttons
        for (const el of allEls) {
            if (el.children.length > 0) continue;
            const text = (el.innerText || '').trim();
            if (text !== 'Fast' && text !== 'Planning') continue;

            // Check if this or a parent is clickable (the actual mode selector)
            let current = el;
            for (let i = 0; i < 5; i++) {
                if (!current) break;
                const style = window.getComputedStyle(current);
                if (style.cursor === 'pointer' || current.tagName === 'BUTTON') {
                    state.mode = text;
                    break;
                }
                current = current.parentElement;
            }
            if (state.mode !== 'Unknown') break;
        }

        // Fallback: Just look for visible text
        if (state.mode === 'Unknown') {
            const textNodes = allEls.filter(el => el.children.length === 0 && el.innerText);
            if (textNodes.some(el => el.innerText.trim() === 'Planning')) state.mode = 'Planning';
            else if (textNodes.some(el => el.innerText.trim() === 'Fast')) state.mode = 'Fast';
        }

        // 2. Get Model
        // Strategy: Look for leaf text nodes containing a known model keyword
        const KNOWN_MODELS = ["Gemini", "Claude", "GPT"];
        const textNodes2 = allEls.filter(el => el.children.length === 0 && el.innerText);
        
        // First try: find inside a clickable parent (button, cursor:pointer)
        let modelEl = textNodes2.find(el => {
            const txt = el.innerText.trim();
            if (!KNOWN_MODELS.some(k => txt.includes(k))) return false;
            // Must be in a clickable context (header/toolbar, not chat content)
            let parent = el;
            for (let i = 0; i < 8; i++) {
                if (!parent) break;
                if (parent.tagName === 'BUTTON' || window.getComputedStyle(parent).cursor === 'pointer') return true;
                parent = parent.parentElement;
            }
            return false;
        });
        
        // Fallback: any leaf node with a known model name
        if (!modelEl) {
            modelEl = textNodes2.find(el => {
                const txt = el.innerText.trim();
                return KNOWN_MODELS.some(k => txt.includes(k)) && txt.length < 60;
            });
        }

        if (modelEl) {
            state.model = modelEl.innerText.trim();
        }

        // 3. Get Running Tasks
        // Strategy: Look for an element containing text like "1 task running" or "N tasks running"
        const taskRegex = /^\\d+ .*running$/i;
        const taskEl = textNodes2.find(el => {
            return taskRegex.test(el.innerText.trim());
        });
        
        let runningTasksList = [];
        if (taskEl) {
            state.runningTasksText = taskEl.innerText.trim();
            try {
                // Find the nearest common container for the tasks list. Usually it's a sibling of the button containing this text.
                // The structure is typically: <button>1 task running</button> <div> ... <span>task name</span> ... </div>
                const btn = taskEl.closest('button');
                if (btn && btn.nextElementSibling) {
                    const taskItems = btn.nextElementSibling.querySelectorAll('span.font-mono, span.truncate');
                    taskItems.forEach(item => {
                        const t = item.innerText.trim();
                        if (t && !runningTasksList.includes(t)) runningTasksList.push(t);
                    });
                }
            } catch(e) {}
        } else {
            state.runningTasksText = null;
        }
        state.runningTasksList = runningTasksList;

        return state;
    } catch (e) { return { error: e.toString() }; }
})()`;

    for (const ctx of cdp.contexts) {
        try {
            const res = await cdp.call("Runtime.evaluate", {
                expression: EXP,
                returnByValue: true,
                awaitPromise: true,
                /* contextId: ctx.id */
            });
            if (res.result?.value) return res.result.value;
        } catch (e) { }
    }
    return { error: 'Context failed' };
}

// Simple hash function
function hashString(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        const char = str.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash;
    }
    return hash.toString(36);
}

// Check if a request is from the same Wi-Fi (internal network)
function isLocalRequest(req) {
    // 1. Check for proxy headers (Cloudflare, ngrok, etc.)
    // If these exist, the request is coming via an external tunnel/proxy
    if (req.headers['x-forwarded-for'] || req.headers['x-forwarded-host'] || req.headers['x-real-ip']) {
        return false;
    }

    // 2. Check the remote IP address
    const ip = req.ip || req.socket.remoteAddress || '';

    // Standard local/private IPv4 and IPv6 ranges
    return ip === '127.0.0.1' ||
        ip === '::1' ||
        ip === '::ffff:127.0.0.1' ||
        ip.startsWith('192.168.') ||
        ip.startsWith('10.') ||
        ip.startsWith('172.16.') || ip.startsWith('172.17.') ||
        ip.startsWith('172.18.') || ip.startsWith('172.19.') ||
        ip.startsWith('172.2') || ip.startsWith('172.3') ||
        ip.startsWith('::ffff:192.168.') ||
        ip.startsWith('::ffff:10.');
}

// Initialize CDP connection
async function initCDP() {
    console.log('🔍 Discovering Antigravity CDP endpoint...');
    const cdpInfo = await discoverCDP();
    console.log(`✅ Found Antigravity on port ${cdpInfo.port} `);

    console.log('🔌 Connecting to CDP...');
    cdpConnection = await connectCDP(cdpInfo.url);
    console.log(`✅ Connected! Found ${cdpConnection.contexts.length} execution contexts\n`);
}

// Background polling
async function startPolling(wss) {
    let lastErrorLog = 0;
    let isConnecting = false;

    const poll = async () => {
        let currentInterval = 1000; // Default idle interval

        if (!cdpConnection || (cdpConnection.ws && cdpConnection.ws.readyState !== WebSocket.OPEN)) {
            if (!isConnecting) {
                console.log('🔍 Looking for Antigravity CDP connection...');
                isConnecting = true;
            }
            if (cdpConnection) {
                // Was connected, now lost
                console.log('🔄 CDP connection lost. Attempting to reconnect...');
                cdpConnection = null;
            }
            try {
                await initCDP();
                if (cdpConnection) {
                    console.log('⚡ CDP Connection established from polling loop');
                    isConnecting = false;
                    
                    // Immediately capture the first snapshot to ensure state is fresh
                    const snapshot = await captureSnapshot(cdpConnection);
                    if (snapshot && !snapshot.error && snapshot.html) {
                        lastSnapshotHash = crypto.createHash('md5').update(snapshot.html).digest('hex');
                    }
                    
                    // Broadcast CDP connected so clients know to immediately refresh their state
                    wss.clients.forEach(client => {
                        if (client.readyState === WebSocket.OPEN) {
                            client.send(JSON.stringify({ type: 'cdp_connected' }));
                        }
                    });
                }
            } catch (err) {
                // Not found yet, just wait for next cycle
            }
            setTimeout(poll, 2000); // Try again in 2 seconds if not found
            return;
        }

        try {
            const snapshot = await captureSnapshot(cdpConnection);
            if (snapshot && !snapshot.error) {
                if (snapshot.isGenerating) {
                    currentInterval = 150; // Fast stream mode (~7 FPS)
                }

                const hash = hashString(snapshot.html);

                // Only update if content changed or generation state changed
                if (hash !== lastSnapshotHash || (lastSnapshot && snapshot.isGenerating !== lastSnapshot.isGenerating)) {
                    handleSnapshotUpdate(lastSnapshot, snapshot);
                    lastSnapshot = snapshot;
                    lastSnapshotHash = hash;
                    try { fs.writeFileSync(join(__dirname, 'latest_snapshot.html'), snapshot.html, 'utf8'); } catch(e){}

                    // Broadcast to all connected clients
                    wss.clients.forEach(client => {
                        if (client.readyState === WebSocket.OPEN) {
                            client.send(JSON.stringify({
                                type: 'snapshot_update',
                                timestamp: new Date().toISOString()
                            }));
                        }
                    });

                    // Don't log every 150ms to prevent spam
                    if (currentInterval !== 150 || Math.random() < 0.1) {
                        console.log(`📸 Snapshot updated(hash: ${hash})`);
                    }
                }
            } else {
                // Snapshot is null or has error
                const now = Date.now();
                if (!lastErrorLog || now - lastErrorLog > 10000) {
                    const errorMsg = snapshot?.error || 'No valid snapshot captured (check contexts)';
                    console.warn(`⚠️  Snapshot capture issue: ${errorMsg} `);
                    if (errorMsg.includes('container not found')) {
                        console.log('   (Tip: Ensure an active chat is open in Antigravity)');
                    }
                    if (cdpConnection.contexts.length === 0) {
                        console.log('   (Tip: No active execution contexts found. Try interacting with the Antigravity window)');
                    }
                    lastErrorLog = now;
                }
            }
        } catch (err) {
            console.error('Poll error:', err.message);
        }

        setTimeout(poll, currentInterval);
    };

    poll();
}

// Create Express app
async function createServer() {
    const app = express();

    // Initialize voice memos directory and cleanup interval
    const voiceMemosDir = join(__dirname, 'scratch', 'voice_memos');
    if (!fs.existsSync(voiceMemosDir)) {
        fs.mkdirSync(voiceMemosDir, { recursive: true });
    }
    setInterval(() => {
        try {
            if (!fs.existsSync(voiceMemosDir)) return;
            const files = fs.readdirSync(voiceMemosDir);
            const now = Date.now();
            for (const file of files) {
                const filePath = join(voiceMemosDir, file);
                const stats = fs.statSync(filePath);
                if (now - stats.mtimeMs > 24 * 60 * 60 * 1000) {
                    fs.unlinkSync(filePath);
                }
            }
        } catch (e) {
            console.error('Error cleaning up voice memos:', e);
        }
    }, 60 * 60 * 1000);

    // Check for SSL certificates
    const keyPath = join(__dirname, 'certs', 'server.key');
    const certPath = join(__dirname, 'certs', 'server.cert');
    const hasSSL = fs.existsSync(keyPath) && fs.existsSync(certPath);

    let server;
    let httpsServer = null;

    if (hasSSL) {
        const sslOptions = {
            key: fs.readFileSync(keyPath),
            cert: fs.readFileSync(certPath)
        };
        httpsServer = https.createServer(sslOptions, app);
        server = httpsServer;
    } else {
        server = http.createServer(app);
    }

    // Ensure we ask CDP to send us console events so we can catch clipboard hooks!
async function ensureConsoleEnabled() {
    if (cdpConnection) {
        try {
            await cdpConnection.call('Runtime.enable', {});
        } catch(e) {}
    }
}
setInterval(ensureConsoleEnabled, 5000);

const wss = new WebSocketServer({ server });



    // Initialize Auth Token using a unique salt from environment
    const authSalt = process.env.AUTH_SALT || 'antigravity_default_salt_99';
    AUTH_TOKEN = hashString(APP_PASSWORD + authSalt);

    app.use(compression());
    app.use(express.json());

    if (process.env.PUBLIC_KEY && process.env.PRIVATE_KEY) {
        webpush.setVapidDetails(
            'mailto:admin@example.com',
            process.env.PUBLIC_KEY,
            process.env.PRIVATE_KEY
        );
    }

    // Use a secure session secret from .env if available
    const sessionSecret = process.env.SESSION_SECRET || 'antigravity_secret_key_1337';

    if (sessionSecret === 'antigravity_secret_key_1337') {
        console.warn('\n\x1b[33m%s\x1b[0m', '⚠️  SECURITY WARNING: Using default SESSION_SECRET ("antigravity_secret_key_1337").');
        console.warn('\x1b[33m%s\x1b[0m', '   Set a strong SESSION_SECRET in your .env file for production use.\n');
    }
    app.use(cookieParser(sessionSecret));

    // Ngrok Bypass Middleware
    app.use((req, res, next) => {
        // Tell ngrok to skip the "visit" warning for API requests
        res.setHeader('ngrok-skip-browser-warning', 'true');
        next();
    });

    // Request Logger
    app.use((req, res, next) => {
        console.log(`[REQUEST] ${req.method} ${req.url} - Auth: ${!!req.signedCookies[AUTH_COOKIE_NAME]} - Local: ${isLocalRequest(req)}`);
        next();
    });

    // Auth Middleware
    app.use((req, res, next) => {
        const publicPaths = ['/login', '/login.html', '/favicon.ico'];
        if (publicPaths.includes(req.path) || req.path.startsWith('/css/')) {
            return next();
        }

        // Exempt local Wi-Fi devices from authentication
        if (isLocalRequest(req)) {
            return next();
        }

        // Magic Link / QR Code Auto-Login
        if (req.query.key === APP_PASSWORD) {
            res.cookie(AUTH_COOKIE_NAME, AUTH_TOKEN, {
                httpOnly: true,
                signed: true,
                maxAge: 30 * 24 * 60 * 60 * 1000 // 30 days
            });
            // Remove the key from the URL by redirecting to the base path
            return res.redirect('/');
        }

        const token = req.signedCookies[AUTH_COOKIE_NAME];
        if (token === AUTH_TOKEN) {
            return next();
        }

        // If it's an API request, return 401, otherwise redirect to login
        if (req.xhr || req.headers.accept?.includes('json') || req.path.startsWith('/snapshot') || req.path.startsWith('/send')) {
            res.status(401).json({ error: 'Unauthorized' });
        } else {
            res.redirect('/login.html');
        }
    });
    app.get('/', (req, res, next) => {
        if (!req.query.v) {
            return res.redirect('/?v=' + Date.now());
        }
        next();
    });

    app.use(express.static(join(__dirname, 'public'), {
        setHeaders: (res, path) => {
            res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate');
            res.setHeader('Pragma', 'no-cache');
            res.setHeader('Expires', '0');
            res.setHeader('Surrogate-Control', 'no-store');
        }
    }));

    // Login endpoint
    app.post('/login', (req, res) => {
        const { password } = req.body;
        if (password === APP_PASSWORD) {
            res.cookie(AUTH_COOKIE_NAME, AUTH_TOKEN, {
                httpOnly: true,
                signed: true,
                maxAge: 30 * 24 * 60 * 60 * 1000 // 30 days
            });
            res.json({ success: true });
        } else {
            res.status(401).json({ success: false, error: 'Invalid password' });
        }
    });

    // Logout endpoint
    app.post('/logout', (req, res) => {
        res.clearCookie(AUTH_COOKIE_NAME);
        res.json({ success: true });
    });

    // Web Push Endpoints
    app.get('/vapidPublicKey', (req, res) => {
        res.send(process.env.PUBLIC_KEY);
    });
app.post('/subscribe', (req, res) => {
        const subscription = req.body;
        // Basic deduplication
        const exists = pushSubscriptions.some(sub => sub.endpoint === subscription.endpoint);
        if (!exists) {
            pushSubscriptions.push(subscription);
            try {
                fs.writeFileSync(SUBSCRIPTIONS_FILE, JSON.stringify(pushSubscriptions));
            } catch(e) {
                console.error('Failed to save subscriptions:', e);
            }
            console.log('✅ New Web Push subscription registered.');
        }
        res.status(201).json({});
    });

    app.get('/test-push', async (req, res) => {
        console.log(`[TEST-PUSH] Triggering push to ${pushSubscriptions.length} subs...`);
        let successes = 0;
        let errors = [];
        for (const sub of pushSubscriptions) {
            try {
                await webpush.sendNotification(sub, JSON.stringify({
                    title: 'Test Notification',
                    body: 'This is a test from the server!'
                }));
                successes++;
            } catch(e) {
                console.error('Test push error:', e);
                errors.push(e.message);
            }
        }
        res.json({ successes, errors });
    });

    // File upload endpoint
    const storage = multer.diskStorage({
        destination: os.tmpdir(),
        filename: (req, file, cb) => {
            const uniqueSuffix = Date.now() + '-' + Math.round(Math.random() * 1E9);
            cb(null, uniqueSuffix + '-' + file.originalname);
        }
    });

    const upload = multer({ 
        storage: storage,
        limits: { fileSize: 50 * 1024 * 1024 } // 50MB limit
    });
    app.post('/upload-attachment', upload.array('files', 10), async (req, res) => {
        try {
            if (!cdpConnection) return res.status(503).json({ error: 'CDP not connected' });
            
            const filePaths = req.files.map(f => f.path);
            console.log('[Upload] Received files:', req.files.map(f => f.originalname));
            
            if (filePaths.length === 0) return res.status(400).json({ error: 'No files uploaded' });

            // Instead of intercepting the file chooser, directly set the files
            const doc = await cdpConnection.call('DOM.getDocument', { depth: -1 });
            const node = await cdpConnection.call('DOM.querySelector', { 
                nodeId: doc.root.nodeId, 
                selector: 'input[type="file"]' 
            });

            if (node && node.nodeId) {
                // Set the file input files directly
                await cdpConnection.call('DOM.setFileInputFiles', {
                    files: filePaths,
                    nodeId: node.nodeId
                });
                
                // Copy voice memos to persistent scratch directory
                try {
                    for (const f of req.files) {
                        if (f.originalname.endsWith('.webm') || f.originalname.endsWith('.mp4')) {
                            const dest = join(__dirname, 'scratch', 'voice_memos', f.originalname);
                            fs.copyFileSync(f.path, dest);
                        }
                    }
                } catch(e) {
                    console.error('Error copying voice memo:', e);
                }

                res.json({ success: true, filenames: req.files.map(f => f.originalname) });
            } else {
                console.warn('[Upload] Could not find file input element to upload to');
                res.status(404).json({ error: 'File input not found in DOM' });
                // Cleanup immediately on failure
                filePaths.forEach(p => fs.unlink(p, () => {}));
                return;
            }

            // Cleanup temp files after 1 minute to allow Chrome to read them asynchronously
            setTimeout(() => {
                filePaths.forEach(p => {
                    fs.unlink(p, (err) => {
                        if (err) console.error('[Cleanup] Error unlinking temp file:', err);
                    });
                });
            }, 60000);
        } catch (e) {
            console.error('[Upload] Error:', e);
            res.status(500).json({ error: e.message });
            // Cleanup on error
            if (req.files) {
                req.files.forEach(f => fs.unlink(f.path, () => {}));
            }
        }
    });

    app.post('/remove-attachment', express.json(), async (req, res) => {
        try {
            if (!cdpConnection) return res.status(503).json({ error: 'CDP not connected' });
            const { filename } = req.body;
            if (!filename) return res.status(400).json({ error: 'Filename is required' });

            const EXPRESSION = `(() => {
                let clicked = 0;
                
                // Find all potential remove buttons
                const btns = document.querySelectorAll('.group.relative.inline-flex button');
                
                // Filter buttons to only click the one associated with our filename
                for (const btn of btns) {
                    const container = btn.closest('.group') || btn.parentElement?.parentElement;
                    if (container && container.textContent && container.textContent.includes('${filename}')) {
                        btn.click();
                        clicked++;
                        break;
                    }
                }
                
                // Fallback: If we couldn't find a specific chip (e.g. for images which don't render filename text), 
                // just clear all attachments so the UI state doesn't get permanently stuck.
                if (clicked === 0 && btns.length > 0) {
                    btns.forEach(b => { b.click(); clicked++; });
                }
                
                const input = document.querySelector('input[type="file"]');
                if (input) {
                    input.value = "";
                    input.dispatchEvent(new Event("change", { bubbles: true }));
                    input.dispatchEvent(new Event("input", { bubbles: true }));
                }
                return { clicked, inputFound: !!input, success: true };
            })()`;

            let success = false;
            for (const ctx of cdpConnection.contexts) {
                try {
                    const result = await cdpConnection.call('Runtime.evaluate', {
                        expression: EXPRESSION,
                        returnByValue: true
                    });
                    if (result && result.result && result.result.value && result.result.value.success) {
                        console.log('[Remove Attachment] UI Cleanup result:', result.result.value);
                        success = true;
                        break;
                    }
                } catch (e) {}
            }

            if (success) {
                res.json({ success: true });
            } else {
                res.status(404).json({ error: 'Could not remove attachment' });
            }
        } catch (e) {
            console.error('[Remove Attachment] Error:', e);
            res.status(500).json({ error: e.message });
        }
    });


    let hasDumped = false;
        // Get current snapshot
    app.get('/snapshot', (req, res) => {
        if (!lastSnapshot) {
            return res.status(503).json({ error: 'No snapshot available yet' });
        }
        
        console.log(`[GET /snapshot] Serving snapshot. isGenerating: ${lastSnapshot.isGenerating}`);
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.json(lastSnapshot);
    });

    // Health check endpoint
    app.get('/health', (req, res) => {
        res.json({
            status: 'ok',
            cdpConnected: cdpConnection?.ws?.readyState === 1, // WebSocket.OPEN = 1
            uptime: process.uptime(),
            timestamp: new Date().toISOString(),
            https: hasSSL
        });
    });

    // SSL status endpoint
    app.get('/ssl-status', (req, res) => {
        const keyPath = join(__dirname, 'certs', 'server.key');
        const certPath = join(__dirname, 'certs', 'server.cert');
        const certsExist = fs.existsSync(keyPath) && fs.existsSync(certPath);
        res.json({
            enabled: hasSSL,
            certsExist: certsExist,
            message: hasSSL ? 'HTTPS is active' :
                certsExist ? 'Certificates exist, restart server to enable HTTPS' :
                    'No certificates found'
        });
    });

    // Generate SSL certificates endpoint
    app.post('/generate-ssl', async (req, res) => {
        try {
            const { execSync } = await import('child_process');
            execSync('node generate_ssl.js', { cwd: __dirname, stdio: 'pipe' });
            res.json({
                success: true,
                message: 'SSL certificates generated! Restart the server to enable HTTPS.'
            });
        } catch (e) {
            res.status(500).json({
                success: false,
                error: e.message
            });
        }
    });

    // Debug UI Endpoint
    app.get('/debug-ui', async (req, res) => {
        if (!cdpConnection) return res.status(503).json({ error: 'CDP not connected' });
        const uiTree = await inspectUI(cdpConnection);
        console.log('--- UI TREE ---');
        console.log(uiTree);
        console.log('---------------');
        res.type('json').send(uiTree);
    });

    // Set Mode
    app.post('/set-mode', async (req, res) => {
        const { mode } = req.body;
        if (!cdpConnection) return res.status(503).json({ error: 'CDP disconnected' });
        const result = await setMode(cdpConnection, mode);
        res.json(result);
    });

    // Set Model
    app.post('/set-model', async (req, res) => {
        const { model } = req.body;
        if (!cdpConnection) return res.status(503).json({ error: 'CDP disconnected' });
        const result = await setModel(cdpConnection, model);
        res.json(result);
    });

    // Stop Generation
    app.post('/stop', async (req, res) => {
        if (!cdpConnection) return res.status(503).json({ error: 'CDP disconnected' });
        const result = await stopGeneration(cdpConnection);
        res.json(result);
    });

    // Send message or handle actions
    app.post('/send', async (req, res) => {
        const { action, agId, stableId, checked } = req.body;
        
        if (action === 'click_element') {
            if (!cdpConnection) return res.status(503).json({ error: 'CDP not connected' });
            if (!agId || typeof agId !== 'string' || agId.length > 100) return res.status(400).json({ error: 'Invalid or missing agId' });
            
            // Try to find the element by data-ag-id and get its coordinates
            const EXP = `(async () => {
                function findNodeById(root, id) {
                    if (!root) return null;
                    let found = root.querySelector && root.querySelector('[data-ag-id=' + CSS.escape(id) + ']');
                    if (found) return found;
                    const all = root.querySelectorAll ? root.querySelectorAll('*') : [];
                    for (const el of all) {
                        if (el.shadowRoot) {
                            const res = findNodeById(el.shadowRoot, id);
                            if (res) return res;
                        }
                    }
                    return null;
                }
                try {
                    const el = findNodeById(document, ${JSON.stringify(agId)});
                    if (!el) return { success: false, reason: 'not_found' };
                    
                    const tagName = (el.tagName || '').toLowerCase();
                    const forceJsClick = tagName === 'vscode-radio' || tagName === 'vscode-checkbox';
                    
                    // Force instant scroll to avoid async animation race conditions
                    el.scrollIntoView({block: 'center', inline: 'center', behavior: 'instant'});
                    
                    const rect = el.getBoundingClientRect();
                    
                    // If the element has no dimensions or is wildly off-screen despite scrolling, 
                    // fallback to an untrusted programmatic click as a last resort.
                    if (forceJsClick || rect.width === 0 || rect.height === 0 || rect.x < -1000 || rect.y < -1000) {
                        el.click();
                        return { success: true, js_fallback: true };
                    }
                    
                    return { 
                        success: true, 
                        x: rect.x + rect.width / 2, 
                        y: rect.y + rect.height / 2 
                    };
                } catch (e) { return { success: false, reason: e.toString() }; }
            })()`;
            
            let coords = null;
            for (const ctx of cdpConnection.contexts) {
                try {
                    const result = await cdpConnection.call("Runtime.evaluate", {
                        expression: EXP,
                        contextId: ctx.id,
                        returnByValue: true,
                        awaitPromise: true,
                    });
                    if (result.result && result.result.value && result.result.value.success) {
                        coords = result.result.value;
                        break;
                    }
                } catch(e) {}
            }
            
            if (coords) {
                try {
                    // If JS fallback was triggered, skip the hardware CDP click
                    if (coords.js_fallback) {
                        return res.json({ success: true, fallback: true });
                    }
                    
                    // Perform true hardware click via CDP (isTrusted=true)
                    await cdpConnection.call("Input.dispatchMouseEvent", {
                        type: "mousePressed",
                        x: coords.x, y: coords.y,
                        button: "left", clickCount: 1
                    });
                    await new Promise(r => setTimeout(r, 50));
                    await cdpConnection.call("Input.dispatchMouseEvent", {
                        type: "mouseReleased",
                        x: coords.x, y: coords.y,
                        button: "left", clickCount: 1
                    });
                    return res.json({ success: true });
                } catch (e) {
                    console.error("CDP Click Failed:", e);
                    return res.status(500).json({ error: e.toString() });
                }
            }
            
            return res.json({ success: false, error: 'Element not found' });
        }
        
        if (action === 'type_text') {
            if (!cdpConnection) return res.status(503).json({ error: 'CDP not connected' });
            
            const { text } = req.body;
            if (agId !== undefined && (typeof agId !== 'string' || agId.length > 100)) return res.status(400).json({ error: 'Invalid agId' });
            if (stableId !== undefined && (typeof stableId !== 'string' || stableId.length > 1000)) return res.status(400).json({ error: 'Invalid stableId' });
            if (typeof text !== 'string' || text.length > 100000) return res.status(400).json({ error: 'Invalid text payload' });
            
            const TYPE_SCRIPT = `(async () => {
                const sId = ${JSON.stringify(stableId || '')};
                const aId = ${JSON.stringify(agId || '')};
                let el = null;
                if (sId) {
                    el = document.querySelector('[data-stable-id=' + CSS.escape(sId) + ']');
                }
                if (!el && aId) {
                    el = document.querySelector('[data-ag-id=' + CSS.escape(aId) + ']');
                }
                if (el) {
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                    const nativeTextAreaValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
                    
                    if (nativeInputValueSetter && el.tagName === 'INPUT') {
                        nativeInputValueSetter.call(el, ${JSON.stringify(text || '')});
                    } else if (nativeTextAreaValueSetter && el.tagName === 'TEXTAREA') {
                        nativeTextAreaValueSetter.call(el, ${JSON.stringify(text || '')});
                    } else {
                        el.value = ${JSON.stringify(text || '')};
                    }
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }
            })();`;
            
            cdpConnection.call('Runtime.evaluate', {
                expression: TYPE_SCRIPT,
                awaitPromise: true
            }).catch(console.error);
            
            return res.json({ success: true });
        }

        if (action === 'toggle_input') {
            if (!cdpConnection) return res.status(503).json({ error: 'CDP not connected' });
            
            // Strict type and length validation to prevent payload abuse
            if (agId !== undefined && (typeof agId !== 'string' || agId.length > 100)) {
                return res.status(400).json({ error: 'Invalid agId' });
            }
            if (stableId !== undefined && (typeof stableId !== 'string' || stableId.length > 1000)) {
                return res.status(400).json({ error: 'Invalid stableId' });
            }
            if (typeof checked !== 'boolean') {
                return res.status(400).json({ error: 'Invalid checked value' });
            }
            
            const TOGGLE_SCRIPT = `(async () => {
                const sId = ${JSON.stringify(stableId || '')};
                const aId = ${JSON.stringify(agId || '')};
                let el = null;
                if (sId) {
                    el = document.querySelector('[data-stable-id=' + CSS.escape(sId) + ']');
                }
                if (!el && aId) {
                    el = document.querySelector('[data-ag-id=' + CSS.escape(aId) + ']');
                }
                if (el) {
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'checked')?.set;
                    if (nativeInputValueSetter) {
                        nativeInputValueSetter.call(el, ${!!checked});
                    } else {
                        el.checked = ${!!checked};
                    }
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    return { ok: true, found: true };
                }
                return { ok: false, found: false };
            })()`;
            
            for (const ctx of cdpConnection.contexts) {
                try {
                    const result = await cdpConnection.call("Runtime.evaluate", {
                        expression: TOGGLE_SCRIPT,
                        contextId: ctx.id,
                        returnByValue: true,
                        awaitPromise: true,
                    });
                    if (result.result && result.result.value && result.result.value.ok) {
                        return res.json({ success: true });
                    }
                } catch(e) {}
            }
            return res.json({ success: false, error: 'Element not found' });
        }

        let { message, attachments } = req.body;

        // Bypass for voice memos that persist across chat resets
        if (Array.isArray(attachments)) {
            for (const filename of attachments) {
                // Prevent path traversal
                if (typeof filename !== 'string' || filename.includes('/') || filename.includes('\\')) continue;
                
                const memoPath = join(__dirname, 'scratch', 'voice_memos', filename);
                if (fs.existsSync(memoPath)) {
                    const appendText = `[Attached Voice Memo: ${memoPath}]`;
                    if (!message) {
                        message = appendText;
                    } else {
                        message = message + '\n' + appendText;
                    }
                }
            }
        }

        if (!message) {
            return res.status(400).json({ error: 'Message required' });
        }

        if (!cdpConnection) {
            return res.status(503).json({ error: 'CDP not connected' });
        }

        const result = await injectMessage(cdpConnection, message);

        if (!result.ok && result.reason === 'busy') {
            return res.json({ success: false, error: 'busy' });
        }

        // Always return 200 - the message usually goes through even if CDP reports issues
        // The client will refresh and see if the message appeared
        
        if (result.method === 'cdp_enter') {
            console.log("Triggering explicit snapshot dump because we just queued a message!");
            setTimeout(async () => {
                const snap = await captureSnapshot(cdpConnection);
                if (snap && snap.html) {
                    try {
                        fs.writeFileSync('pending_dump.html', snap.html);
                        console.log("Dumped post-enter snapshot to pending_dump.html");
                    } catch(e) { console.error('Error writing dump', e); }
                } else {
                    console.log("Failed to take snapshot for dump!");
                }
            }, 500);
        }

        res.json({
            success: result.ok !== false,
            method: result.method || 'attempted',
            details: result
        });
    });

    // UI Inspection endpoint - Returns all buttons as JSON for debugging
    app.get('/ui-inspect', async (req, res) => {
        if (!cdpConnection) return res.status(503).json({ error: 'CDP disconnected' });

        const EXP = `(() => {
    try {
        // Safeguard for non-DOM contexts
        if (typeof window === 'undefined' || typeof document === 'undefined') {
            return { error: 'Non-DOM context' };
        }

        // Helper to get string class name safely (handles SVGAnimatedString)
        function getCls(el) {
            if (!el) return '';
            if (typeof el.className === 'string') return el.className;
            if (el.className && typeof el.className.baseVal === 'string') return el.className.baseVal;
            return '';
        }

        // Helper to pierce Shadow DOM
        function findAllElements(selector, root = document) {
            let results = Array.from(root.querySelectorAll(selector));
            const elements = root.querySelectorAll('*');
            for (const el of elements) {
                try {
                    if (el.shadowRoot) {
                        results = results.concat(Array.from(el.shadowRoot.querySelectorAll(selector)));
                    }
                } catch (e) { }
            }
            return results;
        }

        // Get standard info
        const url = window.location ? window.location.href : '';
        const title = document.title || '';
        const bodyLen = document.body ? document.body.innerHTML.length : 0;
        const hasCascade = !!document.getElementById('cascade') || !!document.querySelector('.cascade');

        // Scan for buttons
        const allLucideElements = findAllElements('svg[class*="lucide"]').map(svg => {
            const parent = svg.closest('button, [role="button"], div, span, a');
            if (!parent || parent.offsetParent === null) return null;
            const rect = parent.getBoundingClientRect();
            return {
                type: 'lucide-icon',
                tag: parent.tagName.toLowerCase(),
                x: Math.round(rect.left),
                y: Math.round(rect.top),
                svgClasses: getCls(svg),
                className: getCls(parent).substring(0, 100),
                ariaLabel: parent.getAttribute('aria-label') || '',
                title: parent.getAttribute('title') || '',
                parentText: (parent.innerText || '').trim().substring(0, 50)
            };
        }).filter(Boolean);

        const buttons = findAllElements('button, [role="button"]').map((btn, i) => {
            const rect = btn.getBoundingClientRect();
            const svg = btn.querySelector('svg');

            return {
                type: 'button',
                index: i,
                x: Math.round(rect.left),
                y: Math.round(rect.top),
                text: (btn.innerText || '').trim().substring(0, 50) || '(empty)',
                ariaLabel: btn.getAttribute('aria-label') || '',
                title: btn.getAttribute('title') || '',
                svgClasses: getCls(svg),
                className: getCls(btn).substring(0, 100),
                visible: btn.offsetParent !== null
            };
        }).filter(b => b.visible);

        return {
            url, title, bodyLen, hasCascade,
            buttons, lucideIcons: allLucideElements
        };
    } catch (err) {
        return { error: err.toString(), stack: err.stack };
    }
})()`;

        try {
            // 1. Get Frames
            const { frameTree } = await cdpConnection.call("Page.getFrameTree");
            function flattenFrames(node) {
                let list = [{
                    id: node.frame.id,
                    url: node.frame.url,
                    name: node.frame.name,
                    parentId: node.frame.parentId
                }];
                if (node.childFrames) {
                    for (const child of node.childFrames) list = list.concat(flattenFrames(child));
                }
                return list;
            }
            const allFrames = flattenFrames(frameTree);

            // 2. Map Contexts
            const contexts = cdpConnection.contexts.map(c => ({
                id: c.id,
                name: c.name,
                origin: c.origin,
                frameId: c.auxData ? c.auxData.frameId : null,
                isDefault: c.auxData ? c.auxData.isDefault : false
            }));

            // 3. Scan ALL Contexts
            const contextResults = [];
            for (const ctx of [{id: undefined}]) {
                try {
                    const result = await cdpConnection.call("Runtime.evaluate", {
                        expression: EXP,
                        returnByValue: true,
                        /* contextId: ctx.id */
                    });

                    if (result.result?.value) {
                        const val = result.result.value;
                        contextResults.push({
                            /* contextId: ctx.id (removed) */
                            frameId: ctx.frameId,
                            url: val.url,
                            title: val.title,
                            hasCascade: val.hasCascade,
                            buttonCount: val.buttons.length,
                            lucideCount: val.lucideIcons.length,
                            buttons: val.buttons, // Store buttons for analysis
                            lucideIcons: val.lucideIcons
                        });
                    } else if (result.exceptionDetails) {
                        contextResults.push({
                            /* contextId: ctx.id (removed) */
                            frameId: ctx.frameId,
                            error: `Script Exception: ${result.exceptionDetails.text} ${result.exceptionDetails.exception?.description || ''} `
                        });
                    } else {
                        contextResults.push({
                            /* contextId: ctx.id (removed) */
                            frameId: ctx.frameId,
                            error: 'No value returned (undefined)'
                        });
                    }
                } catch (e) {
                    contextResults.push({ /* contextId: ctx.id (removed) */ error: e.message });
                }
            }

            // 4. Match and Analyze
            const cascadeFrame = allFrames.find(f => f.url.includes('cascade'));
            const matchingContext = contextResults.find(c => c.frameId === cascadeFrame?.id);
            const contentContext = contextResults.sort((a, b) => (b.buttonCount || 0) - (a.buttonCount || 0))[0];

            // Prepare "useful buttons" from the best context
            const bestContext = matchingContext || contentContext;
            const usefulButtons = bestContext ? (bestContext.buttons || []).filter(b =>
                b.ariaLabel?.includes('New Conversation') ||
                b.title?.includes('New Conversation') ||
                b.ariaLabel?.includes('Past Conversations') ||
                b.title?.includes('Past Conversations') ||
                b.ariaLabel?.includes('History')
            ) : [];

            res.json({
                summary: {
                    frameFound: !!cascadeFrame,
                    cascadeFrameId: cascadeFrame?.id,
                    contextFound: !!matchingContext,
                    bestContextId: bestContext?.contextId
                },
                frames: allFrames,
                contexts: contexts,
                scanResults: contextResults.map(c => ({
                    id: c.contextId,
                    frameId: c.frameId,
                    url: c.url,
                    hasCascade: c.hasCascade,
                    buttons: c.buttonCount,
                    error: c.error
                })),
                usefulButtons: usefulButtons,
                bestContextData: bestContext // Full data for the best context
            });

        } catch (e) {
            res.status(500).json({ error: e.message, stack: e.stack });
        }
    });

    // Endpoint to list all CDP targets - helpful for debugging connection issues
    app.get('/cdp-targets', async (req, res) => {
        const results = {};
        for (const port of PORTS) {
            try {
                const list = await getJson(`http://127.0.0.1:${port}/json/list`);
                results[port] = list;
            } catch (e) {
                results[port] = e.message;
            }
        }
        res.json(results);
    });

    // WebSocket connection with Auth check
    wss.on('connection', (ws, req) => {
        // Parse cookies from headers
        const rawCookies = req.headers.cookie || '';
        const parsedCookies = {};
        rawCookies.split(';').forEach(c => {
            const [k, v] = c.trim().split('=');
            if (k && v) {
                try {
                    parsedCookies[k] = decodeURIComponent(v);
                } catch (e) {
                    parsedCookies[k] = v;
                }
            }
        });

        // Verify signed cookie manually
        const signedToken = parsedCookies[AUTH_COOKIE_NAME];
        let isAuthenticated = false;

        // Exempt local Wi-Fi devices from authentication
        if (isLocalRequest(req)) {
            isAuthenticated = true;
        } else if (signedToken) {
            const sessionSecret = process.env.SESSION_SECRET || 'antigravity_secret_key_1337';

            if (sessionSecret === 'antigravity_secret_key_1337') {
                // Warning already printed on startup, but we check here for token verification
            }

            const token = cookieParser.signedCookie(signedToken, sessionSecret);
            if (token === AUTH_TOKEN) {
                isAuthenticated = true;
            }
        }

        if (!isAuthenticated) {
            console.log('🚫 Unauthorized WebSocket connection attempt');
            ws.send(JSON.stringify({ type: 'error', message: 'Unauthorized' }));
            setTimeout(() => ws.close(), 100);
            return;
        }

        console.log('📱 Client connected (Authenticated)');

        ws.on('close', () => {
            console.log('📱 Client disconnected');
        });
    });

    return { server, wss, app, hasSSL };
}

// Main
async function main() {
    try {
        await initCDP();
    } catch (err) {
        console.warn(`⚠️  Initial CDP discovery failed: ${err.message}`);
        console.log('💡 Start Antigravity with --remote-debugging-port=9000 to connect.');
    }

    try {
        const { server, wss, app, hasSSL } = await createServer();

        // Start background polling (it will now handle reconnections)
        startPolling(wss);

        // Remote Click
        app.post('/remote-click', async (req, res) => {
            const { id, selector, index, textContent, autoConfirmText } = req.body;
            if (!cdpConnection) return res.status(503).json({ error: 'CDP disconnected' });
            const result = await clickElement(cdpConnection, { id, selector, index, textContent });
            
            if (autoConfirmText) {
                console.log(`[autoConfirm] Waiting for modal...`);
                
                const modalCheckExp = `new Promise((resolve) => {
                    const check = () => {
                        const modals = document.querySelectorAll('[role="dialog"], [role="alertdialog"], [aria-modal="true"], dialog, .radix-dialog-content');
                        if (modals.length > 0) resolve(true);
                        else requestAnimationFrame(check);
                    };
                    check();
                    setTimeout(() => resolve(false), 600);
                })`;
                
                let isModalOpen = false;
                try {
                    const checkRes = await cdpConnection.call("Runtime.evaluate", {
                        expression: modalCheckExp,
                        returnByValue: true,
                        awaitPromise: true
                    });
                    if (checkRes.result?.value) {
                        isModalOpen = true;
                    }
                } catch (e) {}

                if (isModalOpen || autoConfirmText === 'Revert') {
                    // Small delay to ensure the modal is fully rendered and focus is trapped
                    await new Promise(r => setTimeout(r, 50));
                    
                    try {
                        console.log(`[autoConfirm] Dispatching Enter key`);
                        await cdpConnection.call("Input.dispatchKeyEvent", { type: "keyDown", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13, text: "\r" });
                        await cdpConnection.call("Input.dispatchKeyEvent", { type: "keyUp", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 });
                        result.autoConfirmed = true;
                    } catch (e) {
                        console.error(`[autoConfirm] Failed to dispatch Enter:`, e);
                    }
                } else {
                    console.log(`[autoConfirm] No modal detected, skipping Enter key`);
                }
            }
            
            res.json(result);
        });

        // Kill Task
        app.post('/kill-task', async (req, res) => {
            const { taskName } = req.body;
            if (!cdpConnection) return res.status(503).json({ error: 'CDP disconnected' });
            
            const KILL_EXP = `(async () => {
                const taskRegex = /^\\d+ .*running$/i;
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
                let taskEl = null;
                while (walker.nextNode()) {
                    if (taskRegex.test(walker.currentNode.nodeValue.trim())) {
                        taskEl = walker.currentNode.parentElement;
                        break;
                    }
                }
                if (!taskEl) return { success: false, error: 'Task indicator not found' };
                
                const btn = taskEl.closest('button');
                if (!btn || !btn.nextElementSibling) return { success: false, error: 'Task dropdown not found' };
                
                const spans = Array.from(btn.nextElementSibling.querySelectorAll('span.font-mono, span.truncate'));
                const span = spans.find(el => el.innerText.trim() === ${JSON.stringify(taskName)});
                if (!span) return { success: false, error: 'Task not found in dropdown' };
                
                const container = span.closest('.group');
                if (!container) return { success: false, error: 'Task container not found' };
                
                const stopBtn = container.querySelector('button[data-tooltip-id^="stop-task"], button[data-tooltip-id^="stop-subagent"]');
                if (!stopBtn) return { success: false, error: 'Stop button not found' };
                
                stopBtn.click();
                return { success: true };
            })()`;
            
            try {
                let success = false;
                for (const ctx of cdpConnection.contexts) {
                    const resCDP = await cdpConnection.call("Runtime.evaluate", {
                        expression: KILL_EXP,
                        returnByValue: true,
                        awaitPromise: true
                    });
                    if (resCDP.result?.value?.success) {
                        success = true;
                        break;
                    }
                }
                res.json({ success });
            } catch (e) {
                res.json({ success: false, error: e.toString() });
            }
        });

        // Remote Scroll - sync phone scroll to desktop
        app.post('/remote-scroll', async (req, res) => {
            const { scrollTop, scrollPercent } = req.body;
            if (!cdpConnection) return res.status(503).json({ error: 'CDP disconnected' });
            const result = await remoteScroll(cdpConnection, { scrollTop, scrollPercent });
            res.json(result);
        });

        // Get App State
        app.get('/app-state', async (req, res) => {
            if (!cdpConnection) return res.json({ mode: 'Unknown', model: 'Unknown' });
            const result = await getAppState(cdpConnection);
            res.json(result);
        });

        // Start New Chat
        app.get('/dump-dom', async (req, res) => {
    try {
        const result = await cdpConnection.call('Runtime.evaluate', {
            expression: 'document.body.innerHTML',
            returnByValue: true
        });
        require('fs').writeFileSync('dom_dump.html', result.result.value);
        res.send('OK');
    } catch (e) {
        res.status(500).send(e.toString());
    }
});

        app.post('/new-chat', async (req, res) => {
            if (!cdpConnection) return res.status(503).json({ error: 'CDP disconnected' });
            
            const { workspace } = req.body || {};
            
            const result = await startNewChat(cdpConnection, workspace);
            res.json(result);
        });

        // Get Chat History
        app.get('/chat-history', async (req, res) => {
            if (!cdpConnection) return res.json({ error: 'CDP disconnected', chats: [] });
            const result = await getChatHistory(cdpConnection);
            if (result && result.chats) {
                const filterRegex = /(You are the|Review the|Please review|Please query|Your objective|Created At:|Call the MCP|I have drafted|Just reply|Review the plan|Review the implementation|You are a JS Style|Review the modifications|The user has proposed|Debate Proposition|You are participating|You operate in a strict|You are tasked with|You are responsible|# Technical Debate|This is the Iterative-Implement|Please perform a diff|The user has raised a|The Design-Validate|New Chat)/i;
                result.chats = result.chats.filter(c => !filterRegex.test(c.title));
            }
            res.json(result);
        });

        // Debug route
        app.get('/debug-brain', (req, res) => {
            try {
                const fs = require('fs');
                const path = require('path');
                const os = require('os');
                const brainDir = path.join(os.homedir(), '.gemini', 'antigravity', 'brain');
                if (!fs.existsSync(brainDir)) return res.json({ error: 'brainDir does not exist', path: brainDir });
                const folders = fs.readdirSync(brainDir).filter(f => f.length === 36);
                res.json({ success: true, count: folders.length, path: brainDir });
            } catch(e) {
                res.json({ error: e.message });
            }
        });

        // Select a Chat
        app.post('/select-chat', async (req, res) => {
            const { title } = req.body;
            if (!title) return res.status(400).json({ error: 'Chat title required' });
            if (!cdpConnection) return res.status(503).json({ error: 'CDP disconnected' });
            const result = await selectChat(cdpConnection, title);
            res.json(result);
        });

        // Close Chat History
        app.post('/close-history', async (req, res) => {
            if (!cdpConnection) return res.status(503).json({ error: 'CDP disconnected' });
            const result = await closeHistory(cdpConnection);
            res.json(result);
        });

        app.post('/api/history/load-more', async (req, res) => {
            try {
                if (!cdpConnection) return res.status(503).json({ error: 'CDP disconnected' });
                await loadMoreHistory(cdpConnection);
                // wait for react to render new items in the DOM
                await new Promise(r => setTimeout(r, 400));
                const historyResult = await getChatHistory(cdpConnection);
                if (historyResult.success) {
                    if (historyResult.chats) {
                        const filterRegex = /(You are the|Review the|Please review|Please query|Your objective|Created At:|Call the MCP|I have drafted|Just reply|Review the plan|Review the implementation|You are a JS Style|Review the modifications|The user has proposed|Debate Proposition|You are participating|You operate in a strict|You are tasked with|You are responsible|# Technical Debate|This is the Iterative-Implement|Please perform a diff|The user has raised a|The Design-Validate|New Chat)/i;
                        historyResult.chats = historyResult.chats.filter(c => !filterRegex.test(c.title));
                    }
                    if (lastSnapshot) lastSnapshot.history = historyResult; 
                    res.json(historyResult);
                } else {
                    res.status(500).json({ error: 'Failed to fetch history after scroll' });
                }
            } catch (e) {
                res.status(500).json({ error: e.toString() });
            }
        });

        // Check if Chat is Open
        app.get('/chat-status', async (req, res) => {
            if (!cdpConnection) return res.json({ hasChat: false, hasMessages: false, editorFound: false });
            const result = await hasChatOpen(cdpConnection);
            res.json(result);
        });

        // Kill any existing process on the port before starting
        await killPortProcess(SERVER_PORT);

        // Start server
        const localIP = getLocalIP();
        const protocol = hasSSL ? 'https' : 'http';
        server.listen(SERVER_PORT, '0.0.0.0', () => {
            console.log(`🚀 Server running on ${protocol}://${localIP}:${SERVER_PORT}`);
            if (hasSSL) {
                console.log(`💡 First time on phone? Accept the security warning to proceed.`);
            }
        });

        // Graceful shutdown handlers
        const gracefulShutdown = (signal) => {
            console.log(`\n🛑 Received ${signal}. Shutting down gracefully...`);
            wss.close(() => {
                console.log('   WebSocket server closed');
            });
            server.close(() => {
                console.log('   HTTP server closed');
            });
            if (cdpConnection?.ws) {
                cdpConnection.ws.close();
                console.log('   CDP connection closed');
            }
            setTimeout(() => process.exit(0), 1000);
        };

        process.on('SIGINT', () => gracefulShutdown('SIGINT'));
        process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));

    } catch (err) {
        console.error('❌ Fatal error:', err.message);
        process.exit(1);
    }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
    main();
}
