// --- CSS Reset for Web Components ---
document.body.setAttribute('ontouchstart', '');
// --- CSS Reset for Web Components ---
const shadowStyle = document.createElement('style');
shadowStyle.textContent = `
    vscode-radio::part(control),
    vscode-radio::part(checked-indicator),
    vscode-checkbox::part(control),
    vscode-checkbox::part(checked-indicator) {
        transition: none !important;
    }
`;
document.head.appendChild(shadowStyle);

// --- Elements ---
const chatContainer = document.getElementById('chatContainer');
const chatContent = document.getElementById('chatContent');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const scrollToBottomBtn = document.getElementById('scrollToBottom');
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');
const stopBtn = document.getElementById('stopBtn');
const newChatBtn = document.getElementById('newChatBtn');
const historyBtn = document.getElementById('historyBtn');
const voiceBtn = document.getElementById('voiceBtn');

const modeBtn = document.getElementById('modeBtn') || { classList: { toggle: () => {} }, addEventListener: () => {} };
const modelBtn = document.getElementById('modelBtn') || { classList: { toggle: () => {} }, addEventListener: () => {} };
const modalOverlay = document.getElementById('modalOverlay');
const modalList = document.getElementById('modalList');
const modalTitle = document.getElementById('modalTitle');
const modeText = document.getElementById('modeText') || { textContent: '' };
const modelText = document.getElementById('modelText') || { textContent: '' };
const historyLayer = document.getElementById('historyLayer');
const historyList = document.getElementById('historyList');

// New elements for event listeners
const enableHttpsBtn = document.getElementById('enableHttpsBtn');
const dismissSslBtn = document.querySelector('.dismiss-btn');
const closeModalBtn = document.getElementById('closeModalBtn');
const supportBtn = document.getElementById('supportBtn');
const supportOverlay = document.getElementById('supportOverlay');
const closeSupportBtn = document.getElementById('closeSupportBtn');
const backHistoryBtn = document.querySelector('.history-header .icon-btn');
const quickActionChips = document.querySelectorAll('.action-chip');

const SVG_SEND_STANDARD = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m22 2-7 20-4-9-9-4Z"></path><path d="M22 2 11 13"></path></svg>`;
const SVG_SEND_QUEUE = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 10 4 15 9 20"></polyline><path d="M20 4v7a4 4 0 0 1-4 4H4"></path></svg>`;

// --- State ---
let autoRefreshEnabled = true;
let userIsScrolling = false;
let isProgrammaticScroll = false;
let userScrollLockUntil = 0; // Timestamp until which we respect user scroll
let lastScrollPosition = 0;
let ws = null;
let idleTimer = null;
let lastHash = '';
let currentMode = 'Fast';
let chatIsOpen = true; // Track if a chat is currently open
let currentRunningTasksList = [];

window.stagedAttachments = [];
function renderStagedAttachments() {
    const container = document.getElementById('stagedAttachmentsContainer');
    if (!container) return;
    if (window.stagedAttachments.length === 0) {
        container.classList.add('hidden');
        container.innerHTML = '';
        return;
    }
    container.classList.remove('hidden');
    container.innerHTML = '';
    window.stagedAttachments.forEach(filename => {
        const chip = document.createElement('div');
        chip.className = 'attachment-chip';
        chip.innerHTML = `
            <svg class="file-icon" viewBox="0 0 24 24">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8"></polyline>
            </svg>
            ${filename}
            <button class="edit-btn" aria-label="Edit file" style="margin-left: auto; margin-right: 5px; background: none; border: none; color: #a1a1aa; cursor: pointer;">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="16" height="16"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"></path><path d="m15 5 4 4"></path></svg>
            </button>
            <button class="remove-btn" aria-label="Remove file">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
            </button>
        `;
        chip.querySelector('.remove-btn').addEventListener('click', async () => {
            window.stagedAttachments = window.stagedAttachments.filter(f => f !== filename);
            renderStagedAttachments();
            try {
                await fetchWithAuth('/remove-attachment', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ filename })
                });
            } catch (e) {
                console.error('Failed to remove attachment', e);
            }
        });
        container.appendChild(chip);
    });
    
    updateInputButtons();
}

// --- Virtual Keyboard API ---
// Prevents Android Chrome from abruptly resizing the viewport when keyboard opens
if ('virtualKeyboard' in navigator) {
    navigator.virtualKeyboard.overlaysContent = true;
    navigator.virtualKeyboard.addEventListener('geometrychange', (event) => {
        // When keyboard opens, smoothly pin the chat to the bottom at 60fps 
        // to match the CSS padding-bottom transition (0.25s)
        let start = performance.now();
        function syncScroll(time) {
            scrollToBottom();
            if (time - start < 300) {
                requestAnimationFrame(syncScroll);
            }
        }
        requestAnimationFrame(syncScroll);
    });
}

// --- Auth Utilities ---
async function fetchWithAuth(url, options = {}) {
    console.log("FETCH TYPE:", typeof fetch, fetch.name);
    // Add ngrok skip warning header to all requests
    if (!options.headers) options.headers = {};
    options.headers['ngrok-skip-browser-warning'] = 'true';

    try {
        const res = await fetch(url, options);
        if (res.status === 401) {
            console.log('[AUTH] Unauthorized, redirecting to login...');
            window.location.href = '/login.html';
            return new Promise(() => { }); // Halt execution
        }
        return res;
    } catch (e) {
        throw e;
    }
}
const USER_SCROLL_LOCK_DURATION = 500; // 0.5 seconds of scroll protection

// --- Sync State (Desktop is Always Priority) ---
async function fetchAppState() {
    try {
        const res = await fetchWithAuth(`/app-state?_t=${Date.now()}`);
        const data = await res.json();

        // Mode Sync (Fast/Planning) - Desktop is source of truth
        if (data.mode && data.mode !== 'Unknown') {
            modeText.textContent = data.mode;
            modeBtn.classList.toggle('active', data.mode === 'Planning');
            currentMode = data.mode;
        }

        // Model Sync - Desktop is source of truth
        if (data.model && data.model !== 'Unknown') {
            modelText.textContent = data.model;
        }

        // Running Tasks Sync
        let taskIndicator = document.getElementById('taskIndicator');
        let taskIndicatorText = document.getElementById('taskIndicatorText');
        
        // Dynamically inject if missing (handles heavily cached PWA index.html)
        if (!taskIndicator) {
            const inputSection = document.querySelector('.input-section > div[style*="display:flex"]');
            if (inputSection) {
                const indicatorHtml = `
                <div class="task-indicator hidden" id="taskIndicator" aria-label="Running Tasks">
                    <svg class="task-spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="2" x2="12" y2="6"></line><line x1="12" y1="18" x2="12" y2="22"></line><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"></line><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"></line><line x1="2" y1="12" x2="6" y2="12"></line><line x1="18" y1="12" x2="22" y2="12"></line><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"></line><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"></line></svg>
                    <span id="taskIndicatorText">1 task running</span>
                </div>`;
                inputSection.insertAdjacentHTML('beforeend', indicatorHtml);
                taskIndicator = document.getElementById('taskIndicator');
                taskIndicatorText = document.getElementById('taskIndicatorText');
                
                // Re-bind click event
                taskIndicator.addEventListener('click', () => {
                    if (currentRunningTasksList && currentRunningTasksList.length > 0) {
                        const options = currentRunningTasksList.map(task => ({
                            label: task,
                            html: `
                                  <div style="display:flex; justify-content:space-between; align-items:center; width:100%;">
                                      <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:80%;" onclick="showToast('${task.replace(/'/g, "\\'")}')">${task}</span>
                                      <div class="kill-task-btn" data-task="${task.replace(/'/g, "\\'")}" style="display:inline-block; padding:4px;">
                                          <svg style="width:16px; height:16px; stroke:var(--error); cursor:pointer;" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                              <animate attributeName="opacity" values="1;0.2;1" dur="1.5s" repeatCount="indefinite" />
                                              <animate attributeName="stroke-width" values="2;4;2" dur="1.5s" repeatCount="indefinite" />
                                              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="9" y1="9" x2="15" y2="15"></line><line x1="15" y1="9" x2="9" y2="15"></line>
                                          </svg>
                                      </div>
                                  </div>`
                        }));
                        openModal('Running Tasks', options, () => {});
                        
                        setTimeout(() => {
                            document.querySelectorAll('.kill-task-btn').forEach(btn => {
                                btn.addEventListener('click', async (e) => {
                                    e.stopPropagation();
                                    const taskName = btn.dataset.task;
                                    try {
                                        await fetchWithAuth('/kill-task', {
                                            method: 'POST',
                                            headers: { 'Content-Type': 'application/json' },
                                            body: JSON.stringify({ taskName: taskName })
                                        });
                                        const optionDiv = btn.closest('.modal-option');
                                        if (optionDiv) optionDiv.remove();
                                        if (document.querySelectorAll('#modal-list .modal-option').length === 0) closeModal();
                                    } catch (err) {
                                        console.error('Failed to kill task:', err);
                                    }
                                });
                            });
                        }, 50);
                    }
                });
            }
        }

        if (taskIndicator && taskIndicatorText) {
            if (data.runningTasksText) {
                taskIndicatorText.textContent = data.runningTasksText;
                taskIndicator.classList.remove('hidden');
                currentRunningTasksList = data.runningTasksList || [];
            } else {
                taskIndicator.classList.add('hidden');
                currentRunningTasksList = [];
            }
        }

        console.log('[SYNC] State refreshed from Desktop:', data);
    } catch (e) { console.error('[SYNC] Failed to sync state', e); }
}

// --- SSL Banner ---
const sslBanner = document.getElementById('sslBanner');

async function checkSslStatus() {
    // Only show banner if currently on HTTP
    if (window.location.protocol === 'https:') return;

    // Check if user dismissed the banner before
    if (localStorage.getItem('sslBannerDismissed')) return;

    sslBanner.style.display = 'flex';
}

async function enableHttps() {
    const btn = document.getElementById('enableHttpsBtn');
    btn.textContent = 'Generating...';
    btn.disabled = true;

    try {
        const res = await fetchWithAuth('/generate-ssl', { method: 'POST' });
        const data = await res.json();

        if (data.success) {
            sslBanner.innerHTML = `
                <span>✅ ${data.message}</span>
                <button id="sslReloadBtn">Reload After Restart</button>
            `;
            sslBanner.style.background = 'linear-gradient(90deg, #22c55e, #16a34a)';
            
            // Add listener to the newly created button
            const reloadBtn = document.getElementById('sslReloadBtn');
            if (reloadBtn) reloadBtn.addEventListener('click', () => location.reload());
        } else {
            btn.textContent = 'Failed - Retry';
            btn.disabled = false;
        }
    } catch (e) {
        btn.textContent = 'Error - Retry';
        btn.disabled = false;
    }
}

function dismissSslBanner() {
    sslBanner.style.display = 'none';
    localStorage.setItem('sslBannerDismissed', 'true');
}

// Check SSL on load
checkSslStatus();
// --- Models ---
const MODELS = [
    "Gemini 3.1 Pro (High)",
    "Gemini 3.1 Pro (Low)",
    "Gemini 3 Flash",
    "Claude Sonnet 4.6 (Thinking)",
    "Claude Opus 4.6 (Thinking)",
    "GPT-OSS 120B (Medium)"
];

// --- WebSocket ---
async function connectWebSocket() {
    try {
        const res = await fetch('/');
        if (res.redirected && res.url.includes('/login.html')) {
            window.location.href = '/login.html';
            return;
        } else if (res.status === 401 || res.status === 403) {
            window.location.href = '/login.html';
            return;
        }
    } catch(e) {
        console.warn('Fetch health check failed before WS connection', e);
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${window.location.host}`);

    ws.onopen = () => {
        console.log('WS Connected');
        updateStatus(true);
        loadSnapshot();
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'force_reload') {
            window.location.reload(true);
            return;
        }
        if (data.type === 'error' && data.message === 'Unauthorized') {
            window.location.href = '/login.html';
            return;
        }
        if (data.type === 'snapshot_update' && autoRefreshEnabled && !userIsScrolling) {
            loadSnapshot();
        }
        if (data.type === 'cdp_connected') {
            checkChatStatus();
            fetchAppState();
            loadSnapshot();
        }
    };

    ws.onclose = () => {
        console.log('WS Disconnected');
        updateStatus(false);
        setTimeout(connectWebSocket, 2000);
    };
}

let isGenerating = false;
let optimisticGeneratingUntil = 0;
let lockedOptionNumber = null;
let generationPlaceholderInterval = null;

function updateInputButtons() {
    const wrapper = document.querySelector('.input-wrapper');
    
    const hasInput = messageInput.value.trim().length > 0 || (window.stagedAttachments && window.stagedAttachments.length > 0);
    
    // RHS: Toggle between Send and Stop
    if (isGenerating && hasInput) {
        sendBtn.innerHTML = SVG_SEND_QUEUE;
        sendBtn.classList.add('visible');
        stopBtn.classList.remove('visible');
    } else if (isGenerating && !hasInput) {
        sendBtn.classList.remove('visible');
        stopBtn.classList.add('visible');
    } else if (hasInput) {
        sendBtn.innerHTML = SVG_SEND_STANDARD;
        sendBtn.classList.add('visible');
        stopBtn.classList.remove('visible');
    } else {
        sendBtn.classList.remove('visible');
        stopBtn.classList.remove('visible');
    }

    // LHS: Attach wrapper remains visible
    const attachWrapper = document.querySelector('.attach-wrapper');
    if (attachWrapper) attachWrapper.style.display = 'flex';

    if (isGenerating) {
        if (wrapper) wrapper.classList.add('generating');
        // Start "Working..." animation
        if (!generationPlaceholderInterval) {
            let dotCount = 1;
            messageInput.placeholder = 'Working.';
            generationPlaceholderInterval = setInterval(() => {
                dotCount = (dotCount % 3) + 1;
                messageInput.placeholder = 'Working' + '.'.repeat(dotCount);
            }, 500);
        }

        const inputActionBtn = document.querySelector('.input-action-btn:first-child');
        if (inputActionBtn) {
            inputActionBtn.style.opacity = '0.5';
            inputActionBtn.style.pointerEvents = 'none';
        }
    } else {
        if (wrapper) wrapper.classList.remove('generating');
        
        // Stop animation and reset placeholder
        if (generationPlaceholderInterval) {
            clearInterval(generationPlaceholderInterval);
            generationPlaceholderInterval = null;
        }
        messageInput.placeholder = 'Ask anything, @ to mention, / for actions';

        const inputActionBtn = document.querySelector('.input-action-btn:first-child');
        if (inputActionBtn) {
            inputActionBtn.style.opacity = '1';
            inputActionBtn.style.pointerEvents = 'auto';
        }
    }
}

function updateStatus(connected) {
    if (connected) {
        statusDot.classList.remove('disconnected');
        statusDot.classList.add('connected');
        statusText.textContent = 'Live';
        statusText.style.fontSize = ''; // Reset to default CSS
    } else {
        statusDot.classList.remove('connected');
        statusDot.classList.add('disconnected');
        statusText.textContent = 'Reconnecting';
        statusText.style.fontSize = '9px'; // Dynamically smaller so it fits same width!
        
        // Ensure the UI doesn't get stuck in "Stop" mode if the server dies
        sendBtn.classList.add('visible');
        stopBtn.classList.remove('visible');
    }
}

// --- Rendering ---
window.isThumbAnimating = false;
window.pendingSnapshot = false;

async function loadSnapshot() {
    if (window.isThumbAnimating) {
        window.pendingSnapshot = true;
        return;
    }
    window.pendingSnapshot = false;

    try {
        const response = await fetchWithAuth('/snapshot');
        if (!response.ok) {
            if (response.status === 503) {
                // No snapshot available - likely no chat open
                chatIsOpen = false;
                showEmptyState();
                return;
            }
            throw new Error('Failed to load');
        }

        // Mark chat as open since we got a valid snapshot
        chatIsOpen = true;

        const data = await response.json();

        // Check again after fetch resolves to prevent replacing DOM if user clicked during the network request!
        if (window.isThumbAnimating) {
            window.pendingSnapshot = true;
            return;
        }

        // Capture scroll state BEFORE updating content
        const scrollerBefore = getScrollContainer();
        const scrollPos = scrollerBefore.scrollTop;
        const scrollHeight = scrollerBefore.scrollHeight;
        const clientHeight = scrollerBefore.clientHeight;
        const isNearBottom = scrollHeight - scrollPos - clientHeight < 120;
        const isUserScrollLocked = Date.now() < userScrollLockUntil;

        // --- UPDATE GENERATION STATE ---
        if (Date.now() < optimisticGeneratingUntil && !data.isGenerating) {
            // Force it to true during the optimistic window if the snapshot hasn't caught up yet
            isGenerating = true;
        } else {
            isGenerating = data.isGenerating;
            if (!isGenerating) {
                lockedOptionNumber = null;
            }
        }
        updateInputButtons();

        // --- UPDATE STATS ---
        if (data.stats) {
            const kbs = Math.round((data.stats.htmlSize + data.stats.cssSize) / 1024);
            const nodes = data.stats.nodes;
            const statsText = document.getElementById('statsText');
            if (statsText) statsText.textContent = `${nodes} Nodes · ${kbs}KB`;
        }

        // --- CSS INJECTION (Cached) ---
        let styleTag = document.getElementById('cdp-styles');
        if (!styleTag) {
            styleTag = document.createElement('style');
            styleTag.id = 'cdp-styles';
            document.head.appendChild(styleTag);
        }

        const darkModeOverrides = '/* --- BASE SNAPSHOT CSS --- */\n' +
            data.css +
            '\n\n/* --- FORCE DARK MODE OVERRIDES --- */\n' +
            ':root {\n' +
            '    --bg-app: #0f172a;\n' +
            '    --text-main: #f8fafc;\n' +
            '    --text-muted: #94a3b8;\n' +
            '    --border-color: #334155;\n' +
            '}\n' +
            '\n' +
            '/* Hide the desktop input box and tasks tray since they are non-functional in the proxy */\n' +
            '#antigravity\\.agentSidePanelInputBox, [data-testid="conversation-view"] > div:has([aria-label="Message input"]) {\n' +
            '    display: none !important;\n' +
            '}\n' +
            '\n' +
            '[data-testid="conversation-view"], #conversation, #chat, #cascade {\n' +
            '    background-color: transparent !important;\n' +
            '    color: var(--text-main) !important;\n' +
            '    font-family: \'Inter\', system-ui, sans-serif !important;\n' +
            '    position: relative !important;\n' +
            '    height: auto !important;\n' +
            '    width: 100% !important;\n' +
            '    overflow: visible !important;\n' +
            '}\n' +
            '\n' +
            '/* Let chatContainer handle all scrolling so its scrollTop survives innerHTML replacement! */\n' +

            '#chatContainer {\n' +
            '    overflow: hidden !important; /* Move scroll handling to desktop virtual container */\n' +
            '}\n' +
            '#root > div {\n' +
            '    flex: 1 !important;\n' +
            '    height: 100% !important;\n' +
            '    padding: 0 !important;\n' +
            '    padding-bottom: 24px !important;\n' +
            '}\n' +
            '#chatContent {\n' +
            '    display: flex !important;\n' +
            '    flex-direction: column !important;\n' +
            '    flex: 1 !important;\n' +
            '}\n' +
            '[data-testid="conversation-view"], #conversation, #chat, #cascade {\n' +
            '    flex: 1 !important;\n' +
            '    height: 100% !important;\n' +
            '    overflow: hidden !important;\n' +
            '}\n' +
            '/* EXCEPT code blocks, keep them horizontally scrollable */\n' +
            '[data-testid="conversation-view"] pre, [data-testid="conversation-view"] code {\n' +
            '    overflow-x: auto !important;\n' +
            '}\n' +
            '\n' +
            '/* Prevent sticky elements from floating and blocking the mobile screen, EXCEPT tasks block */\n' +
            '[data-testid="conversation-view"] .sticky:not(.backdrop-blur-md) {\n' +
            '    position: relative !important;\n' +
            '    top: auto !important;\n' +
            '    z-index: 1 !important;\n' +
            '}\n' +
            '\n' +
            '/* Move the Tasks Running block to the bottom of the chat window */\n' +
            '[data-testid="conversation-view"] .sticky.backdrop-blur-md {\n' +
            '    position: fixed !important;\n' +
            '    top: auto !important;\n' +
            '    bottom: 24px !important;\n' +
            '    left: 50% !important;\n' +
            '    transform: translateX(-50%) !important;\n' +
            '    width: calc(100% - 32px) !important;\n' +
            '    max-width: 400px !important;\n' +
            '    z-index: 100 !important;\n' +
            '    border-radius: 12px !important;\n' +
            '    background: var(--bg-app) !important;\n' +
            '    box-shadow: 0 4px 20px rgba(0,0,0,0.6) !important;\n' +
            '    border: 1px solid var(--border-color) !important;\n' +
            '    padding: 12px !important;\n' +
            '    margin-top: 0 !important;\n' +
            '}\n' +
            '\n' +
            '/* Custom Semi-Transparent Scrollbar for Chat Window */\n' +
            '[data-testid="conversation-view"] * {\n' +
            '    scrollbar-color: rgba(255, 255, 255, 0.2) transparent !important;\n' +
            '    scrollbar-width: thin !important;\n' +
            '}\n' +
            '[data-testid="conversation-view"] *::-webkit-scrollbar {\n' +
            '    width: 6px !important;\n' +
            '}\n' +
            '[data-testid="conversation-view"] *::-webkit-scrollbar-track {\n' +
            '    background: transparent !important;\n' +
            '}\n' +
            '[data-testid="conversation-view"] *::-webkit-scrollbar-thumb {\n' +
            '    background: rgba(255, 255, 255, 0.2) !important;\n' +
            '    border-radius: 10px !important;\n' +
            '}\n' +
            '[data-testid="conversation-view"] *::-webkit-scrollbar-thumb:hover {\n' +
            '    background: rgba(255, 255, 255, 0.4) !important;\n' +
            '}\n' +
            '\n' +
            '[data-testid="conversation-view"] p, [data-testid="conversation-view"] h1, [data-testid="conversation-view"] h2, [data-testid="conversation-view"] h3, [data-testid="conversation-view"] h4, [data-testid="conversation-view"] h5, [data-testid="conversation-view"] span, [data-testid="conversation-view"] div, [data-testid="conversation-view"] li,\n' +
            '#conversation p, #chat p, #cascade p, #conversation h1, #chat h1, #cascade h1, #conversation h2, #chat h2, #cascade h2, #conversation h3, #chat h3, #cascade h3, #conversation h4, #chat h4, #cascade h4, #conversation h5, #chat h5, #cascade h5, #conversation span, #chat span, #cascade span, #conversation div, #chat div, #cascade div, #conversation li, #chat li, #cascade li {\n' +
            '    color: inherit !important;\n' +
            '}\n' +
            '\n' +
            '/* Force black inline text to white */\n' +
            '[style*="color: rgb(0, 0, 0)"], [style*="color: black"],\n' +
            '[style*="color:#000"], [style*="color: #000"] {\n' +
            '    color: #e2e8f0 !important;\n' +
            '}\n' +
            '\n' +
            '[data-testid="conversation-view"] a, #conversation a, #chat a, #cascade a {\n' +
            '    color: #60a5fa !important;\n' +
            '    text-decoration: underline;\n' +
            '}\n' +
            '\n' +
            '/* Add scrollbar and limit height for long user prompts */\n' +
            '[data-testid="user-input-step"] [class*="max-h-"] {\n' +
            '    max-height: 25vh !important;\n' +
            '    overflow-y: auto !important;\n' +
            '}\n' +
            '\n' +
            '/* Force user message buttons to sit underneath the text */\n' +
            '[data-testid="conversation-view"] .flex-row:has(> .user-input-buttons-container) {\n' +
            '    flex-direction: column !important;\n' +
            '    align-items: flex-end !important;\n' +
            '}\n' +
            '[data-testid="conversation-view"] .user-input-buttons-container {\n' +
            '    position: relative !important;\n' +
            '    bottom: auto !important;\n' +
            '    right: auto !important;\n' +
            '    margin-top: 4px;\n' +
            '}\n' +
            '\n' +
            '/* Reveal hover-dependent action buttons on mobile (e.g. Queued message Delete/Redirect) */\n' +
            '[data-testid="conversation-view"] .opacity-0,\n' +
            '[data-testid="conversation-view"] [class*="opacity-0"],\n' +
            '[data-testid="conversation-view"] [class*="group-hover:opacity-100"] {\n' +
            '    opacity: 1 !important;\n' +
            '    visibility: visible !important;\n' +
            '}\n' +
            '[data-testid="conversation-view"] .hidden.group-hover\\:flex,\n' +
            '[data-testid="conversation-view"] [class*="group-hover:flex"] {\n' +
            '    display: flex !important;\n' +
            '}\n' +
            '\n' +
            '/* Hide broken local file icons (served from /c:/Users/... paths) */\n' +
            'img[src^="/c:"], img[src^="/C:"], img[src*="AppData"] {\n' +
            '    display: none !important;\n' +
            '}\n' +
            '\n' +
            '/* Override Tailwind default block display for embedded file icons */\n' +
            'img, svg {\n' +
            '    display: inline !important;\n' +
            '    vertical-align: middle !important;\n' +
            '}\n' +
            '/* Force file-reference wrappers (icon + filename) to stay inline */\n' +
            'div:has(> img[src^="data:"]), div:has(> img[alt]), span:has(> img) {\n' +
            '    display: inline !important;\n' +
            '    vertical-align: middle !important;\n' +
            '}\n' +
            '/* Inline-flex containers from Antigravity (e.g. file mentions) */\n' +
            '[class*="inline-flex"], [class*="inline-block"], [class*="items-center"]:has(img) {\n' +
            '    display: inline-flex !important;\n' +
            '    vertical-align: middle !important;\n' +
            '}\n' +
            '\n' +
            '/* Fix Inline Code - Ultra-compact */\n' +
            ':not(pre) > code {\n' +
            '    padding: 0px 2px !important;\n' +
            '    border-radius: 2px !important;\n' +
            '    background-color: rgba(255, 255, 255, 0.1) !important;\n' +
            '    font-size: 0.82em !important;\n' +
            '    line-height: 1 !important;\n' +
            '    white-space: normal !important;\n' +
            '}\n' +
            '\n' +
            'pre, code, .monaco-editor-background, [class*="terminal"] {\n' +
            '    background-color: #1e293b !important;\n' +
            '    color: #e2e8f0 !important;\n' +
            '    font-family: \'JetBrains Mono\', monospace !important;\n' +
            '    border-radius: 3px;\n' +
            '    border: 1px solid #334155;\n' +
            '}\n' +
            '                \n' +
            '/* Multi-line Code Block - Minimal */\n' +
            'pre {\n' +
            '    position: relative !important;\n' +
            '    white-space: pre-wrap !important; \n' +
            '    word-break: break-word !important;\n' +
            '    padding: 4px 6px !important;\n' +
            '    margin: 2px 0 !important;\n' +
            '    display: block !important;\n' +
            '    width: 100% !important;\n' +
            '}\n' +
            '                \n' +
            'pre.has-copy-btn {\n' +
            '    padding-right: 28px !important;\n' +
            '}\n' +
            '                \n' +
            '/* Single-line Code Block - Minimal */\n' +
            'pre.single-line-pre {\n' +
            '    display: inline-block !important;\n' +
            '    width: auto !important;\n' +
            '    max-width: 100% !important;\n' +
            '    padding: 0px 4px !important;\n' +
            '    margin: 0px !important;\n' +
            '    vertical-align: middle !important;\n' +
            '    background-color: #1e293b !important;\n' +
            '    font-size: 0.85em !important;\n' +
            '}\n' +
            '                \n' +
            'pre.single-line-pre > code {\n' +
            '    display: inline !important;\n' +
            '    white-space: nowrap !important;\n' +
            '}\n' +
            '                \n' +
            'pre:not(.single-line-pre) > code {\n' +
            '    display: block !important;\n' +
            '    width: 100% !important;\n' +
            '    overflow-x: auto !important;\n' +
            '    background: transparent !important;\n' +
            '    border: none !important;\n' +
            '    padding: 0 !important;\n' +
            '    margin: 0 !important;\n' +
            '}\n' +
            '                \n' +
            '.mobile-copy-btn {\n' +
            '    position: absolute !important;\n' +
            '    top: 2px !important;\n' +
            '    right: 2px !important;\n' +
            '    background: rgba(30, 41, 59, 0.5) !important;\n' +
            '    color: #94a3b8 !important;\n' +
            '    border: none !important;\n' +
            '    width: 24px !important; \n' +
            '    height: 24px !important;\n' +
            '    padding: 0 !important;\n' +
            '    cursor: pointer !important;\n' +
            '    display: flex !important;\n' +
            '    align-items: center !important;\n' +
            '    justify-content: center !important;\n' +
            '    border-radius: 4px !important;\n' +
            '    transition: all 0.5s ease-in-out !important;\n' +
            '    -webkit-tap-highlight-color: transparent !important;\n' +
            '    z-index: 10 !important;\n' +
            '    margin: 0 !important;\n' +
            '}\n' +
            '                \n' +
            '.mobile-copy-btn:hover,\n' +
            '.mobile-copy-btn:focus {\n' +
            '    background: rgba(59, 130, 246, 0.2) !important;\n' +
            '    color: #60a5fa !important;\n' +
            '}\n' +
            '\n' +
            '.mobile-copy-btn.copied {\n' +
            '    color: #4ade80 !important;\n' +
            '    background: rgba(74, 222, 128, 0.2) !important;\n' +
            '    transform: scale(1.1) !important;\n' +
            '}\n' +
            '                \n' +
            '.mobile-copy-btn svg {\n' +
            '    width: 16px !important;\n' +
            '    height: 16px !important;\n' +
            '    stroke: currentColor !important;\n' +
            '    stroke-width: 2 !important;\n' +
            '    fill: none !important;\n' +
            '}\n' +
            '                \n' +
            'blockquote {\n' +
            '    border-left: 3px solid #3b82f6 !important;\n' +
            '    background: rgba(59, 130, 246, 0.1) !important;\n' +
            '    color: #cbd5e1 !important;\n' +
            '    padding: 8px 12px !important;\n' +
            '    margin: 8px 0 !important;\n' +
            '}\n' +
            '\n' +
            'table {\n' +
            '    border-collapse: collapse !important;\n' +
            '    width: 100% !important;\n' +
            '    border: 1px solid #334155 !important;\n' +
            '}\n' +
            'th, td {\n' +
            '    border: 1px solid #334155 !important;\n' +
            '    padding: 8px !important;\n' +
            '    color: #e2e8f0 !important;\n' +
            '}\n' +
            '\n' +
            '::-webkit-scrollbar {\n' +
            '    width: 0 !important;\n' +
            '}\n' +
            '                \n' +
            '[style*="background-color: rgb(255, 255, 255)"],\n' +
            '[style*="background-color: white"],\n' +
            '[style*="background: white"] {\n' +
            '    background-color: transparent !important;\n' +
            '}';
        styleTag.textContent = darkModeOverrides;
        let modifiedHtml = data.html;
        if (!updateDOMPreservingScroll(chatContent, modifiedHtml, isNearBottom, isUserScrollLocked)) {
            chatContent.innerHTML = modifiedHtml;
        }

        // Re-apply modal-submit-lock if a question option was clicked
        if (lockedOptionNumber) {
            const messages = Array.from(document.querySelectorAll('.message li, .message p, .message div'));
            for (let i = messages.length - 1; i >= 0; i--) {
                const el = messages[i];
                const text = (el.textContent || el.innerText || '').trim();
                const match = text.match(/^\[?(\d+)\]?[.:\)]?\s+(.+)/);
                if (match && match[1] === lockedOptionNumber) {
                    el.classList.add('modal-submit-lock');
                    break;
                }
            }
        }

        // Re-apply local input states (garbage collect expired ones)
        if (window.localInputStates) {
            const now = Date.now();
            Object.keys(window.localInputStates).forEach(stableId => {
                const state = window.localInputStates[stableId];
                if (now > state.expiresAt) {
                    delete window.localInputStates[stableId];
                } else {
                    let el = null;
                    if (stableId.startsWith('ag-stable-')) {
                        el = document.querySelector('[data-stable-id=' + CSS.escape(stableId) + ']');
                    }
                    if (!el) el = document.querySelector('[data-ag-id=' + CSS.escape(stableId) + ']');
                    if (el) {
                        el.checked = state.checked;
                    }
                }
            });
        }

        // Re-apply active thumb visual states based on data-message-id
        window.tappedThumbs = window.tappedThumbs || {};
        const allBtns = document.querySelectorAll('button[aria-label="Good response"], button[aria-label="Bad response"]');
        allBtns.forEach(btn => {
            const type = btn.getAttribute('aria-label');
            const article = btn.closest('[role="article"]') || (btn.closest('.group') ? btn.closest('.group').querySelector('[role="article"]') : null);
            const messageId = article ? article.getAttribute('data-message-id') : null;
            if (messageId && window.tappedThumbs[messageId] === type) {
                btn.classList.add('active-thumb');
            }
        });

        // Add mobile copy buttons to all code blocks
        addMobileCopyButtons();

        // Setup resize observer for dynamic content loading (images/fonts)
        setupResizeObserver();

        // Smart scroll behavior: respect user scroll, only auto-scroll when appropriate
        const scrollerAfter = getScrollContainer();
        if (scrollerAfter) {
            if (isUserScrollLocked) {
                shouldStickToBottom = false;
            } else if (isNearBottom) {
                scrollToBottom();
            } else {
                shouldStickToBottom = false;
            }
        }
        
        // Hide loader if we are no longer at the top
        const loader = document.getElementById('infiniteScrollLoader');
        if (loader && scrollerAfter.scrollTop >= 50) {
            loader.classList.add('hidden');
        }

    } catch (err) {
        console.error(err);
    }
}

// --- Mobile Code Block Copy Functionality ---
// Removed addAgentMessageCopyButtons in favor of backend clipboard hooking

function addMobileCopyButtons() {
    // Find all pre elements (code blocks) in the chat
    const codeBlocks = chatContent.querySelectorAll('pre');

    codeBlocks.forEach((pre, index) => {
        // Skip if already has our button
        if (pre.querySelector('.mobile-copy-btn')) return;

        // Get the code text
        const codeElement = pre.querySelector('code') || pre;
        const textToCopy = (codeElement.textContent || codeElement.innerText).trim();

        // Check if there's a newline character in the TRIMMED text
        // This ensures single-line blocks with trailing newlines don't get buttons
        const hasNewline = /\n/.test(textToCopy);

        // If it's a single line code block, don't add the copy button
        if (!hasNewline) {
            pre.classList.remove('has-copy-btn');
            pre.classList.add('single-line-pre');
            return;
        }

        // Add class for padding
        pre.classList.remove('single-line-pre');
        pre.classList.add('has-copy-btn');

        // Create the copy button (icon only)
        const copyBtn = document.createElement('button');
        copyBtn.className = 'mobile-copy-btn';
        copyBtn.setAttribute('data-code-index', index);
        copyBtn.setAttribute('aria-label', 'Copy code');
        copyBtn.innerHTML = `
            <svg viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>
            `;

        // Add click handler for copy
        copyBtn.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation();

            const success = await copyToClipboard(textToCopy);

            if (success) {
                // Visual feedback - show checkmark
                copyBtn.classList.add('copied');
                copyBtn.innerHTML = `
            <svg viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
            `;

                // Reset after 2 seconds
                setTimeout(() => {
                    copyBtn.classList.remove('copied');
                    copyBtn.innerHTML = `
            <svg viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round">
                            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                        </svg>
            `;
                }, 2000);
            } else {
                // Show X icon briefly on error
                copyBtn.innerHTML = `
            <svg viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="18" y1="6" x2="6" y2="18"></line>
                        <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
            `;
                setTimeout(() => {
                    copyBtn.innerHTML = `
            <svg viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round">
                            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                        </svg>
            `;
                }, 2000);
            }
        });

        // Insert button into pre element
        pre.appendChild(copyBtn);
    });
}

async function copyToClipboard(text) {
    // Method 1: Modern Clipboard API (works on HTTPS or localhost)
    if (navigator.clipboard && window.isSecureContext) {
        try {
            await navigator.clipboard.writeText(text);
            console.log('[COPY] Success via Clipboard API');
            return true;
        } catch (err) {
            console.warn('[COPY] Clipboard API failed:', err);
        }
    }

    // Method 3: Fallback using execCommand (works on HTTP, older browsers)
    let execSuccess = false;
    try {
        const textArea = document.createElement('textarea');
        textArea.value = text;

        textArea.style.position = 'fixed';
        textArea.style.top = '0';
        textArea.style.left = '0';
        textArea.style.width = '2em';
        textArea.style.height = '2em';
        textArea.style.padding = '0';
        textArea.style.border = 'none';
        textArea.style.outline = 'none';
        textArea.style.boxShadow = 'none';
        textArea.style.background = 'white';
        textArea.style.color = 'black';
        textArea.style.opacity = '0.01';

        document.body.appendChild(textArea);

        if (navigator.userAgent.match(/ipad|iphone/i)) {
            const range = document.createRange();
            range.selectNodeContents(textArea);
            const selection = window.getSelection();
            selection.removeAllRanges();
            selection.addRange(range);
            textArea.setSelectionRange(0, text.length);
        } else {
            textArea.select();
        }

        execSuccess = document.execCommand('copy');
        document.body.removeChild(textArea);

        if (execSuccess) {
            // On Android Chrome, execCommand often returns true even when it silently fails.
            if (navigator.userAgent.match(/Android/i)) {
                console.warn('[COPY] execCommand lies on Android. Forcing modal.');
                showManualCopyModal(text);
                return false;
            }
            console.log('[COPY] Success via execCommand fallback');
            return true;
        }
    } catch (err) {
        console.warn('[COPY] execCommand fallback failed:', err);
    }

    // Method 3: Mobile fallback modal (Guaranteed to work if user interacts)
    console.warn('[COPY] Falling back to manual copy modal');
    showManualCopyModal(text);
    return false; // Returns false so the button shows a failure initially, but user can still copy
}

function showManualCopyModal(text) {
    const overlay = document.createElement('div');
    overlay.style.position = 'fixed';
    overlay.style.top = '0';
    overlay.style.left = '0';
    overlay.style.width = '100vw';
    overlay.style.height = '100vh';
    overlay.style.backgroundColor = 'rgba(0,0,0,0.6)';
    overlay.style.zIndex = '999999';
    overlay.style.display = 'flex';
    overlay.style.justifyContent = 'center';
    overlay.style.alignItems = 'center';

    const modal = document.createElement('div');
    modal.style.backgroundColor = 'var(--bg-panel, #1e1e2e)';
    modal.style.color = 'var(--text-main, #fff)';
    modal.style.padding = '20px';
    modal.style.borderRadius = '12px';
    modal.style.width = '90%';
    modal.style.maxWidth = '400px';
    modal.style.boxShadow = '0 10px 25px rgba(0,0,0,0.5)';
    modal.style.display = 'flex';
    modal.style.flexDirection = 'column';
    modal.style.gap = '15px';

    const header = document.createElement('div');
    header.style.fontWeight = 'bold';
    header.style.fontSize = '16px';
    header.style.textAlign = 'center';
    header.innerText = 'Copy Manually';

    const helpText = document.createElement('div');
    helpText.style.fontSize = '12px';
    helpText.style.color = 'var(--text-muted, #aaa)';
    helpText.style.textAlign = 'center';
    helpText.innerText = 'Automatic copy failed. Long-press the text below to copy it.';

    const textAreaFallback = document.createElement('textarea');
    textAreaFallback.value = text;
    textAreaFallback.readOnly = true;
    textAreaFallback.style.width = '100%';
    textAreaFallback.style.height = '200px';
    textAreaFallback.style.backgroundColor = 'var(--bg-input, #000)';
    textAreaFallback.style.color = 'var(--text-main, #fff)';
    textAreaFallback.style.border = '1px solid var(--border, #333)';
    textAreaFallback.style.padding = '12px';
    textAreaFallback.style.borderRadius = '8px';
    textAreaFallback.style.fontSize = '14px';

    const closeBtn = document.createElement('button');
    closeBtn.innerText = 'Close';
    closeBtn.style.padding = '12px';
    closeBtn.style.backgroundColor = 'var(--accent, #3b82f6)';
    closeBtn.style.color = 'white';
    closeBtn.style.border = 'none';
    closeBtn.style.borderRadius = '8px';
    closeBtn.style.fontWeight = 'bold';
    closeBtn.onclick = () => document.body.removeChild(overlay);

    modal.appendChild(header);
    modal.appendChild(helpText);
    modal.appendChild(textAreaFallback);
    modal.appendChild(closeBtn);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    setTimeout(() => {
        textAreaFallback.focus();
        textAreaFallback.setSelectionRange(0, text.length);
    }, 100);
}

let scrollObserver = null;
let shouldStickToBottom = true;
let anchorDistanceFromBottom = null;
let anchorScrollTimeout = null;

function setupResizeObserver() {
    const scroller = getScrollContainer();
    if (!scroller) return;
    
    if (scrollObserver) scrollObserver.disconnect();
    
    // We observe the first child of the scroller, which is the actual content wrapper
    const innerContent = scroller.firstElementChild;
    if (!innerContent) return;
    
    scrollObserver = new ResizeObserver(() => {
        const activeScroll = getScrollContainer();
        if (!activeScroll) return;
        
        if (anchorDistanceFromBottom !== null) {
            const newScrollPos = activeScroll.scrollHeight - activeScroll.clientHeight - anchorDistanceFromBottom;
            isProgrammaticScroll = true;
            activeScroll.scrollTop = Math.max(0, newScrollPos);
            setTimeout(() => isProgrammaticScroll = false, 50);
        } else if (shouldStickToBottom) {
            isProgrammaticScroll = true;
            activeScroll.scrollTop = activeScroll.scrollHeight;
            setTimeout(() => isProgrammaticScroll = false, 50);
        }
    });
    
    scrollObserver.observe(innerContent);
}

// Add helper to find active scroll container
function getScrollContainer() {
    // The desktop DOM structure wraps the scrolling virtual list in a few layers
    const grandchild = document.querySelector('[data-testid="conversation-view"] > div > div');
    if (grandchild && grandchild.scrollHeight > grandchild.clientHeight) return grandchild;
    
    const child = document.querySelector('[data-testid="conversation-view"] > div');
    if (child && child.scrollHeight > child.clientHeight) return child;
    
    const root = document.querySelector('[data-testid="conversation-view"]');
    if (root && root.scrollHeight > root.clientHeight) return root;
    
    return chatContainer;
}

function scrollToBottom() {
    const container = getScrollContainer();
    if (container) {
        shouldStickToBottom = true;
        isProgrammaticScroll = true;
        container.scrollTop = container.scrollHeight;
        setTimeout(() => isProgrammaticScroll = false, 50);
    }
}

// --- Inputs ---
async function sendMessage(lockedElement = null) {
    const message = messageInput.value.trim();
    if (!message && window.stagedAttachments.length === 0) return;

    const attachmentsToProcess = [...window.stagedAttachments];
    window.stagedAttachments = [];
    renderStagedAttachments();

    // Optimistic UI updates
    const previousValue = messageInput.value;
    messageInput.value = ''; // Clear immediately
    messageInput.style.height = 'auto'; // Reset height
    messageInput.blur(); // Close keyboard on mobile immediately

    isGenerating = true;
    optimisticGeneratingUntil = Date.now() + 3000; // Lock isGenerating to true for 3 seconds to prevent UI toggle flash
    updateInputButtons();

    sendBtn.disabled = true;
    sendBtn.style.opacity = '0.5';

    try {
        // If no chat is open, start a new one first
        if (!chatIsOpen) {
            const newChatRes = await fetchWithAuth('/new-chat', { method: 'POST' });
            const newChatData = await newChatRes.json();
            if (newChatData.success) {
                // Wait for the new chat to be ready
                await new Promise(r => setTimeout(r, 800));
                chatIsOpen = true;
            }
        }

        const res = await fetchWithAuth('/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, attachments: attachmentsToProcess })
        });
        
        const data = await res.json();
        
        if (data.success === false) {
            // Revert optimistic UI
            isGenerating = false;
            optimisticGeneratingUntil = 0;
            updateInputButtons();
            if (lockedElement) {
                lockedElement.style.opacity = '1';
                lockedElement.classList.remove('modal-submit-lock');
                lockedOptionNumber = null;
            }
            alert('Failed to submit option to desktop UI: ' + (data.error || 'Unknown error'));
        } else {
            if (lockedElement) {
                lockedElement.classList.add('modal-submit-success');
            }
        }

        // Always reload snapshot to check if message appeared

        // Don't revert the input - if user sees the message in chat, it was sent
        // Only log errors for debugging, don't show alert popups
        if (!res.ok) {
            console.warn('Send response not ok, but message may have been sent:', data);
        }
    } catch (e) {
        // Network error - still try to refresh in case it went through
        console.error('Send error:', e);
        if (lockedElement) {
            lockedElement.style.opacity = '1';
            lockedElement.classList.remove('modal-submit-lock');
            lockedOptionNumber = null;
        }
    } finally {
        sendBtn.disabled = false;
        sendBtn.style.opacity = '1';
    }
}

// --- Event Listeners ---
sendBtn.addEventListener('click', () => sendMessage());



messageInput.addEventListener('input', function () {
    this.style.height = 'auto';
    this.style.height = (this.scrollHeight) + 'px';
    updateInputButtons();
});

// --- Support Modal Logic ---
if (supportBtn) {
    supportBtn.addEventListener('click', () => {
        if (supportOverlay) {
            supportOverlay.classList.add('show');
        }
    });
}

if (closeSupportBtn) {
    closeSupportBtn.addEventListener('click', () => {
        if (supportOverlay) {
            supportOverlay.classList.remove('show');
        }
    });
}

if (supportOverlay) {
    supportOverlay.addEventListener('click', (e) => {
        if (e.target === supportOverlay) {
            supportOverlay.classList.remove('show');
        }
    });
}

// --- DOM Morphing for Scroll Jitter Fix ---
// Replaces DOM without destroying the scroll container, preserving native touch momentum!
function updateDOMPreservingScroll(container, newHTML, isNearBottom, isUserScrollLocked) {
    const parser = new DOMParser();
    const doc = parser.parseFromString(newHTML, 'text/html');
    
    const currentScroll = getScrollContainer();
    const newScroll = doc.querySelector('.overflow-y-auto, [class*="scroll"], [data-testid="conversation-view"] > div > div');
    
    if (!currentScroll || !newScroll || currentScroll === chatContainer) {
        return false;
    }
    
    const scrollPos = currentScroll.scrollTop;
    const scrollHeight = currentScroll.scrollHeight;
    const clientHeight = currentScroll.clientHeight;
    
    function morph(oldEl, newEl, isRoot = false) {
        if (!oldEl || !newEl) return;
        
        // 1. Sync Attributes (skip for root container because doc.body doesn't match chatContent's attributes)
        if (!isRoot && oldEl.attributes && newEl.attributes) {
            const agId = oldEl.getAttribute && oldEl.getAttribute('data-ag-id');
            const stableId = oldEl.getAttribute && (oldEl.getAttribute('data-stable-id') || agId);
            const isPending = stableId && window.pendingMutations && window.pendingMutations.has(stableId);

            // Remove attributes that no longer exist
            for (let i = oldEl.attributes.length - 1; i >= 0; i--) {
                const attr = oldEl.attributes[i];
                if (isPending && (attr.name === 'checked' || attr.name === 'current-checked')) continue;
                if (!newEl.hasAttribute(attr.name)) {
                    oldEl.removeAttribute(attr.name);
                }
            }
            // Add or update attributes
            for (let i = 0; i < newEl.attributes.length; i++) {
                const attr = newEl.attributes[i];
                if (isPending && (attr.name === 'checked' || attr.name === 'current-checked')) continue;
                if (oldEl.getAttribute(attr.name) !== attr.value) {
                    oldEl.setAttribute(attr.name, attr.value);
                }
            }
            
            // Sync Properties (focus-aware)
            if (oldEl.tagName === 'INPUT' || oldEl.tagName === 'TEXTAREA' || oldEl.tagName === 'SELECT' || oldEl.tagName === 'VSCODE-CHECKBOX' || oldEl.tagName === 'VSCODE-RADIO') {
                if (document.activeElement !== oldEl) {
                    if (oldEl.value !== newEl.value) oldEl.value = newEl.value;
                }
                if (!isPending) {
                    if (oldEl.checked !== newEl.checked) oldEl.checked = newEl.checked;
                    if (oldEl.currentChecked !== newEl.currentChecked) oldEl.currentChecked = newEl.currentChecked;
                }
                if (oldEl.selected !== newEl.selected) oldEl.selected = newEl.selected;
            }
        }
        
        // 2. Diff Children recursively
        const oldChildren = Array.from(oldEl.childNodes);
        const newChildren = Array.from(newEl.childNodes);
        
        for (let i = 0; i < Math.max(oldChildren.length, newChildren.length); i++) {
            if (!oldChildren[i]) {
                oldEl.appendChild(newChildren[i].cloneNode(true));
            } else if (!newChildren[i]) {
                oldEl.removeChild(oldChildren[i]);
            } else if (
                oldChildren[i].nodeType !== newChildren[i].nodeType || 
                oldChildren[i].nodeName !== newChildren[i].nodeName ||
                (oldChildren[i].nodeType === Node.ELEMENT_NODE && newChildren[i].nodeType === Node.ELEMENT_NODE && (
                    (oldChildren[i].id && oldChildren[i].id !== newChildren[i].id) ||
                    (oldChildren[i].getAttribute('data-message-id') && oldChildren[i].getAttribute('data-message-id') !== newChildren[i].getAttribute('data-message-id'))
                ))
            ) {
                oldEl.replaceChild(newChildren[i].cloneNode(true), oldChildren[i]);
            } else if (oldChildren[i].nodeType === Node.TEXT_NODE) {
                if (oldChildren[i].nodeValue !== newChildren[i].nodeValue) {
                    oldChildren[i].nodeValue = newChildren[i].nodeValue;
                }
            } else {
                morph(oldChildren[i], newChildren[i], false);
            }
        }
    }
    
    morph(container, doc.body, true);
    
    const distanceFromBottom = scrollHeight - scrollPos - clientHeight;
    
    // Synchronously adjust scroll immediately to prevent a 1-frame jitter
    const activeScrollSync = getScrollContainer();
    if (activeScrollSync) {
        isProgrammaticScroll = true;
        if (isUserScrollLocked) {
            // If the user is at the absolute top, they are likely loading older history.
            // In this case, new content is injected at the top, so we must preserve distanceFromBottom
            // to prevent the view from jumping to the very top.
            // Otherwise, new content is streaming at the bottom, so we preserve absolute scrollPos.
            if (window.isAtAbsoluteTop) {
                const newScrollPosSync = activeScrollSync.scrollHeight - activeScrollSync.clientHeight - distanceFromBottom;
                activeScrollSync.scrollTop = Math.max(0, newScrollPosSync);
            } else {
                activeScrollSync.scrollTop = scrollPos;
            }
        } else if (isNearBottom) {
            // Pin to bottom if user is already at the bottom
            activeScrollSync.scrollTop = activeScrollSync.scrollHeight;
        } else {
            activeScrollSync.scrollTop = scrollPos;
        }
    }
    
    // Wait for the browser to recalculate layout after DOM insertion
    // so that currentScroll.scrollHeight reflects the newly loaded messages
    requestAnimationFrame(() => {
        const activeScroll = getScrollContainer(); // Get the NEW scroll container in case morph replaced it
        if (!activeScroll) return;
        
        isProgrammaticScroll = true;
        if (isUserScrollLocked) {
            if (window.isAtAbsoluteTop) {
                const newScrollPos = activeScroll.scrollHeight - activeScroll.clientHeight - distanceFromBottom;
                activeScroll.scrollTop = Math.max(0, newScrollPos);
            } else {
                // Keep absolute scroll position to prevent jumping
                activeScroll.scrollTop = scrollPos;
            }
        } else if (isNearBottom) {
            // Pin to bottom
            activeScroll.scrollTop = activeScroll.scrollHeight;
            
            // Lock the anchor for 1 second to handle CSS transitions and image loads that expand height
            anchorDistanceFromBottom = distanceFromBottom;
            clearTimeout(anchorScrollTimeout);
            anchorScrollTimeout = setTimeout(() => {
                anchorDistanceFromBottom = null;
            }, 1000);
        } else {
            activeScroll.scrollTop = scrollPos;
        }

        // Hide infinite scroll loader if we just loaded older messages
        if (activeScroll.scrollHeight > scrollHeight + 100) {
            const loader = document.getElementById('infiniteScrollLoader');
            if (loader) loader.classList.add('hidden');
            isAtAbsoluteTop = true;
            if (topHitTimeout !== null) {
                clearTimeout(topHitTimeout);
                topHitTimeout = null;
            }
            loadAttempts = 0; // Reset load attempts on success
        }
        
        // Track the highest scroll height to know if we actually grew
        if (activeScroll.scrollHeight > highestScrollHeight) {
            highestScrollHeight = activeScroll.scrollHeight;
        }
        
        setTimeout(() => isProgrammaticScroll = false, 50);
    });
    
    return true;
}

// --- Snapshot Loading & Desktop Sync ---
let scrollSyncTimeout = null;
let lastScrollSync = 0;
const SCROLL_SYNC_DEBOUNCE = 150; // ms between scroll syncs
let snapshotReloadPending = false;

async function syncScrollToDesktop() {
    const container = getScrollContainer();
    if (!container) return;
    
    if (container.scrollTop <= 50) {
        if (hasMoreHistory()) {
            if (loadAttempts < 3) {
                loadAttempts++;
            } else {
                return; // Give up after 3 attempts to prevent infinite loading
            }
        }
    }
    
    const maxScroll = container.scrollHeight - container.clientHeight;
    const scrollPercent = maxScroll > 0 ? container.scrollTop / maxScroll : 0;
    
    try {
        await fetchWithAuth('/remote-scroll', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ scrollPercent })
        });

        // Server MutationObserver will automatically push the new DOM state as virtual scrolling renders new nodes
    } catch (e) {
        console.log('Scroll sync failed:', e.message);
    }
}

let isAtAbsoluteTop = false;
let topHitTimeout = null;
let loadAttempts = 0;
let highestScrollHeight = 0;

function hasMoreHistory() {
    if (loadAttempts >= 3) return false;

    if (chatContent && chatContent.textContent.includes("The server cleared a prefix of the conversation as it grew too large")) {
        return false;
    }

    const btn = document.querySelector('button[aria-label^="Load older messages"]');
    if (!btn) return false;
    if (btn.getAttribute('aria-disabled') === 'true' || btn.disabled) return false;
    
    const ariaLabel = btn.getAttribute('aria-label') || '';
    const match = ariaLabel.match(/showing ([\d,]+) of ([\d,]+)/);
    if (match) {
        const loaded = parseInt(match[1].replace(/,/g, ''), 10);
        const total = parseInt(match[2].replace(/,/g, ''), 10);
        return loaded < total;
    }
    
    return false; // Safely return false if there's no matching numbers found
}

function updateLoaderVisibility(container) {
    const loader = document.getElementById('infiniteScrollLoader');
    if (!loader) return;
    
    if (!hasMoreHistory()) {
        loader.classList.add('hidden');
        return;
    }

    if (!isAtAbsoluteTop && container && container.scrollTop < 50) {
        if (loader) loader.classList.remove('hidden');
    } else {
        if (loader) loader.classList.add('hidden');
    }
}

// Use event capture to intercept scroll events from the dynamically injected virtualized container
chatContent.addEventListener('scroll', (e) => {
    if (isProgrammaticScroll) return; // Ignore our own scrolling
    if (!e.isTrusted) return; // Ignore programmatic scroll events caused by DOM replacement
    
    // Clear anchor lock on manual scroll
    anchorDistanceFromBottom = null;
    clearTimeout(anchorScrollTimeout);
    
    const container = e.target;
    // Only process vertical scrolling containers
    if (!container || !container.scrollHeight) return;
    
    userIsScrolling = true;
    // Set a lock to prevent auto-scroll jumping for a few seconds
    userScrollLockUntil = Date.now() + USER_SCROLL_LOCK_DURATION;
    
    // Calculate if they are at the bottom of THIS specific container
    const scrollBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    let isNearBottom = scrollBottom < 50;
    shouldStickToBottom = isNearBottom;

    clearTimeout(idleTimer);
    
    if (isNearBottom) {
        scrollToBottomBtn.classList.remove('show');
        // If user scrolled to bottom, clear the lock so auto-scroll works
        userScrollLockUntil = 0;
    } else {
        scrollToBottomBtn.classList.add('show');
    }
    
    // Auto-reset state if pulling hard into negative overscroll
    if (container.scrollTop < 0) {
        isAtAbsoluteTop = false;
        if (topHitTimeout !== null) {
            clearTimeout(topHitTimeout);
            topHitTimeout = null;
        }
    }

    if (container.scrollTop < 50) {
        if (topHitTimeout === null && !isAtAbsoluteTop) {
            topHitTimeout = setTimeout(() => {
                isAtAbsoluteTop = true;
                updateLoaderVisibility(container);
            }, 10000); // Wait 10s for desktop app to load older messages
        }
    } else {
        if (topHitTimeout !== null) {
            clearTimeout(topHitTimeout);
            topHitTimeout = null;
        }
        // Reset when they scroll down just a bit
        if (container.scrollTop > 50) {
            isAtAbsoluteTop = false;
        }
    }
    
    // Toggle infinite scroll loader at the top
    updateLoaderVisibility(container);

    // Debounced scroll sync to desktop
    const now = Date.now();
    if (now - lastScrollSync > SCROLL_SYNC_DEBOUNCE) {
        lastScrollSync = now;
        clearTimeout(scrollSyncTimeout);
        scrollSyncTimeout = setTimeout(syncScrollToDesktop, 100);
    }

    idleTimer = setTimeout(() => {
        userIsScrolling = false;
        autoRefreshEnabled = true;
        // Catch up immediately if we missed streaming updates
        if (isGenerating) {
            loadSnapshot();
        }
    }, 500);
}, true); // USE CAPTURE

// Catch desktop mouse wheel attempts to scroll past the top
chatContent.addEventListener('wheel', (e) => {
    const container = e.currentTarget;
    if (e.deltaY < 0 && container.scrollTop <= 50) {
        if (!hasMoreHistory()) return;
        
        isAtAbsoluteTop = false;
        if (topHitTimeout !== null) clearTimeout(topHitTimeout);
        topHitTimeout = setTimeout(() => {
            isAtAbsoluteTop = true;
            updateLoaderVisibility(container);
        }, 10000);
        updateLoaderVisibility(container);
        
        // Ensure we actually tell the desktop app to scroll to top to trigger loading
        clearTimeout(scrollSyncTimeout);
        scrollSyncTimeout = setTimeout(syncScrollToDesktop, 100);
    }
}, { passive: true });

// Catch touchscreen drag attempts to scroll past the top (Windows/Android)
let lastTouchY = 0;
chatContent.addEventListener('touchstart', (e) => {
    if (e.touches?.length) {
        lastTouchY = e.touches[0].clientY;
    }
}, { passive: true });

chatContent.addEventListener('touchmove', (e) => {
    if (!e.touches?.length) return;
    const currentY = e.touches[0].clientY;
    const deltaY = lastTouchY - currentY;
    lastTouchY = currentY;
    const container = e.currentTarget;
    
    if (deltaY < 0 && container.scrollTop <= 50) {
        if (!hasMoreHistory()) return;
        
        isAtAbsoluteTop = false;
        if (topHitTimeout !== null) clearTimeout(topHitTimeout);
        topHitTimeout = setTimeout(() => {
            isAtAbsoluteTop = true;
            updateLoaderVisibility(container);
        }, 10000);
        updateLoaderVisibility(container);
        
        // Ensure we actually tell the desktop app to scroll to top to trigger loading
        clearTimeout(scrollSyncTimeout);
        scrollSyncTimeout = setTimeout(syncScrollToDesktop, 100);
    }
}, { passive: true });

scrollToBottomBtn.addEventListener('click', () => {
    userIsScrolling = false;
    userScrollLockUntil = 0; // Clear lock so auto-scroll works again
    scrollToBottom();
});

// --- Quick Actions ---
function quickAction(text) {
    messageInput.value = text;
    messageInput.style.height = 'auto';
    messageInput.style.height = messageInput.scrollHeight + 'px';
    messageInput.focus();
}

// --- Stop Logic ---
stopBtn.addEventListener('click', async () => {
    stopBtn.style.opacity = '0.5';
    
    // Optimistic UI update
    isGenerating = false;
    updateInputButtons();

    try {
        const res = await fetchWithAuth('/stop', { method: 'POST' });
        const data = await res.json();
    } catch(e) { console.error('[PhoneUI] Error:', e); }
    setTimeout(() => stopBtn.style.opacity = '1', 500);
});

async function startNewChat() {
    newChatBtn.style.opacity = '0.5';
    newChatBtn.style.pointerEvents = 'none';

    try {
        const historyRes = await fetchWithAuth('/chat-history');
        const historyData = await historyRes.json();
        
        const workspaces = new Set();
        if (historyData && historyData.chats) {
            historyData.chats.forEach(c => {
                if (c.workspace) workspaces.add(c.workspace);
            });
        }
        
        if (workspaces.size === 0) {
            doStartNewChat();
            return;
        }
        
        const list = document.getElementById('workspaceModalList');
        list.innerHTML = '';
        
        // Add unscoped option at the top
        const globalItem = document.createElement('div');
        globalItem.className = 'modal-option';
        globalItem.textContent = 'Global (Unscoped)';
        globalItem.onclick = () => {
            document.getElementById('workspaceModalOverlay').classList.remove('show');
            doStartNewChat(null);
        };
        list.appendChild(globalItem);
        
        Array.from(workspaces).forEach(ws => {
            const item = document.createElement('div');
            item.className = 'modal-option';
            item.textContent = ws;
            item.onclick = () => {
                document.getElementById('workspaceModalOverlay').classList.remove('show');
                doStartNewChat(ws);
            };
            list.appendChild(item);
        });
        
        document.getElementById('workspaceModalOverlay').classList.add('show');
    } catch (e) {
        console.error('Error fetching chat history for workspaces:', e);
        doStartNewChat(); // fallback
    }
}

async function doStartNewChat(workspace = null) {
    newChatBtn.style.opacity = '0.5';
    newChatBtn.style.pointerEvents = 'none';

    try {
        const body = workspace ? JSON.stringify({ workspace }) : '{}';
        const res = await fetchWithAuth('/new-chat', { 
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: body
        });
        const data = await res.json();

        if (data.success) {
            // Reload snapshot to show new empty chat
            
            // If the history layer was open, let's keep it open or close it? 
            // Better to close it so user sees the new chat.
            hideChatHistory();
        } else {
            console.error('Failed to start new chat:', data.error);
        }
    } catch (e) {
        console.error('New chat error:', e);
    }

    setTimeout(() => {
        newChatBtn.style.opacity = '1';
        newChatBtn.style.pointerEvents = 'auto';
    }, 500);
}
newChatBtn.addEventListener('click', startNewChat);

// --- Chat History Logic ---
async function showChatHistory() {
    const historyLayer = document.getElementById('historyLayer');
    const historyList = document.getElementById('historyList');

    // Show loading state
    historyList.innerHTML = `
        <div class="history-state-container">
            <div class="history-spinner"></div>
            <div class="history-state-text">Loading History...</div>
        </div>
    `;
    historyLayer.style.display = 'flex'; // Force reset in case it was hidden
    
    // Force a reflow for iOS Safari
    void historyLayer.offsetWidth;

    historyLayer.classList.add('show');
    historyBtn.style.opacity = '1';

    try {
        const res = await fetchWithAuth('/chat-history');
        const data = await res.json();

        if (data.error) {
            historyList.innerHTML = `
                <div class="history-state-container">
                    <div class="history-state-icon">⚠️</div>
                    <div class="history-state-title">Error loading history</div>
                    <div class="history-state-desc">${data.error}</div>
                    <button class="history-new-btn mt-4">
                        <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
                            <line x1="12" y1="5" x2="12" y2="19"></line>
                            <line x1="5" y1="12" x2="19" y2="12"></line>
                        </svg>
                        Start New Conversation
                    </button>
                </div>
            `;
            return;
        }

        renderHistoryData(data.chats || []);
    } catch (e) {
        historyList.innerHTML = `
            <div class="history-state-container">
                <div class="history-state-icon">🔌</div>
                <div class="history-state-title">Connection Error</div>
                <div class="history-state-desc">Failed to reach the server.</div>
                <button class="history-new-btn mt-4">
                    <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="12" y1="5" x2="12" y2="19"></line>
                        <line x1="5" y1="12" x2="19" y2="12"></line>
                    </svg>
                    Start New Conversation
                </button>
            </div>
        `;
        console.error('Error fetching chat history:', e);
    }
}

function renderHistoryData(chats) {
    if (chats.length === 0) {
        historyList.innerHTML = `
            <div class="history-state-container">
                <div class="history-state-icon">📝</div>
                <div class="history-state-title">No recent chats found</div>
                <div class="history-state-desc">Start a new conversation to see them here.</div>
                <button class="history-new-btn mt-4">
                    <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="12" y1="5" x2="12" y2="19"></line>
                        <line x1="5" y1="12" x2="19" y2="12"></line>
                    </svg>
                    Start New Conversation
                </button>
            </div>
        `;
        return;
    }

    let html = `
        <div class="history-action-container">
            <button class="history-new-btn">
                <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="12" y1="5" x2="12" y2="19"></line>
                    <line x1="5" y1="12" x2="19" y2="12"></line>
                </svg>
                New Conversation
            </button>
        </div>
        <div class="history-list-group">
    `;

    const pinnedChats = [];
    const projectChats = {};
    const globalChats = [];

    chats.forEach(chat => {
        if (chat.isPinned) {
            pinnedChats.push(chat);
        } else if (!chat.workspace || chat.workspace === 'Global') {
            globalChats.push(chat);
        } else {
            if (!projectChats[chat.workspace]) projectChats[chat.workspace] = [];
            projectChats[chat.workspace].push(chat);
        }
    });

    const renderCard = (chat, customIcon = null, isHidden = false) => {
        const safeTitle = chat.title.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
        const defaultIcon = `<svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                        </svg>`;
        let style = isHidden ? 'display: none;' : '';
        let extraClass = '';
        if (chat.isActive) {
            style += ' opacity: 0.5; cursor: default;';
            extraClass = ' active-chat';
        }
        return `
            <div class="history-card${extraClass}" data-title="${safeTitle}" style="${style}" ${chat.isActive ? 'data-active="true"' : ''}>
                <div class="history-card-icon">
                    ${customIcon || defaultIcon}
                </div>
                <div class="history-card-content">
                    <span class="history-card-title">${escapeHtml(chat.title)}</span>
                </div>
                ${chat.isActive ? '' : `<div class="history-card-arrow">
                    <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="9 18 15 12 9 6"></polyline>
                    </svg>
                </div>`}
            </div>
        `;
    };

    const renderCollapsibleHeader = (title, id, isClosed = false, extraStyle = '') => {
        const transform = isClosed ? 'transform: rotate(-90deg);' : '';
        return `
            <div class="history-group-header collapsible-header" data-target="${id}" style="${extraStyle}">
                <span class="toggle-icon" style="${transform}">▼</span>
                ${title}
            </div>
        `;
    };

    if (pinnedChats.length > 0) {
        html += renderCollapsibleHeader('Pinned Conversations', 'pinned-group', true);
        html += `<div id="pinned-group" class="collapsible-content" style="display: none;">`;
        const starIcon = `<svg viewBox="0 0 24 24" width="18" height="18" stroke="currentColor" stroke-width="2" fill="var(--accent)" stroke-linecap="round" stroke-linejoin="round">
                            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon>
                         </svg>`;
        pinnedChats.forEach(chat => { html += renderCard(chat, starIcon); });
        html += `</div>`;
    }

    const projectKeys = Object.keys(projectChats);
    if (projectKeys.length > 0) {
        html += renderCollapsibleHeader('Projects', 'projects-group');
        html += `<div id="projects-group" class="collapsible-content">`;
        projectKeys.forEach((ws, idx) => {
            const subId = `project-sub-${idx}`;
            html += renderCollapsibleHeader(escapeHtml(ws), subId, true, 'margin-left: 16px;');
            html += `<div id="${subId}" class="collapsible-content project-sub-group" style="display: none;">`;
            projectChats[ws].forEach(chat => { html += renderCard(chat); });
            html += `</div>`;
        });
        html += `</div>`;
    }

    if (globalChats.length > 0) {
        html += renderCollapsibleHeader('Conversations (Non-Project)', 'global-group', false, 'margin-left: 16px;');
        html += `<div id="global-group" class="collapsible-content project-sub-group">`;
        const firstSix = globalChats.slice(0, 6);
        const rest = globalChats.slice(6);
        firstSix.forEach(chat => { html += renderCard(chat); });
        
        if (rest.length > 0) {
            html += `<div id="global-group-rest" class="collapsible-content" style="display: none;">`;
            rest.forEach(chat => { html += renderCard(chat, null, false); });
            html += `</div>`;
            html += `<div class="pagination-controls" id="global-pagination-controls" style="display: flex; gap: 8px; margin-top: 4px;">`;
            html += `<div class="history-show-more-btn" data-target="global-group-rest" style="flex: 1; color: var(--accent); cursor: pointer; padding: 8px 12px; font-size: 13px; text-align: center; border-radius: 6px; background: rgba(255,255,255,0.03); user-select: none;">Show More</div>`;
            html += `<div class="history-show-less-btn" data-target="global-group-rest" style="flex: 1; color: var(--accent); cursor: pointer; padding: 8px 12px; font-size: 13px; text-align: center; border-radius: 6px; background: rgba(255,255,255,0.03); user-select: none; display: none;">Show Less</div>`;
            html += `</div>`;
        }
        html += `</div>`;
    }

    html += `</div>`; // Close history-list-group

    const oldScroll = historyList.scrollTop;
    
    // Preserve open states
    const openStates = {};
    const existingContents = historyList.querySelectorAll('.collapsible-content');
    existingContents.forEach(el => {
        openStates[el.id] = el.style.display !== 'none';
    });
    
    historyList.innerHTML = html;
    historyList.scrollTop = oldScroll;
    
    // Restore open states
    const newContents = historyList.querySelectorAll('.collapsible-content');
    newContents.forEach(el => {
        if (openStates[el.id] !== undefined) {
            el.style.display = openStates[el.id] ? 'block' : 'none';
        }
    });

    const headers = historyList.querySelectorAll('.collapsible-header');
    headers.forEach(header => {
        const targetId = header.getAttribute('data-target');
        const content = document.getElementById(targetId);
        const icon = header.querySelector('.toggle-icon');
        if (content && icon) {
            icon.style.transform = content.style.display === 'none' ? 'rotate(-90deg)' : 'rotate(0deg)';
        }
        
        header.addEventListener('click', (e) => {
            if (content.style.display === 'none') {
                content.style.display = 'block';
                if (icon) icon.style.transform = 'rotate(0deg)';
            } else {
                content.style.display = 'none';
                if (icon) icon.style.transform = 'rotate(-90deg)';
            }
        });
    });
    
    const showMoreBtns = historyList.querySelectorAll('.history-show-more-btn');
    const showLessBtns = historyList.querySelectorAll('.history-show-less-btn');

    const updatePaginationButtons = (content, moreBtn, lessBtn) => {
        if (content.style.display === 'none') {
            moreBtn.style.display = 'block';
            lessBtn.style.display = 'none';
        } else {
            moreBtn.style.display = 'none';
            lessBtn.style.display = 'block';
        }
    };

    showMoreBtns.forEach(btn => {
        const targetId = btn.getAttribute('data-target');
        const content = document.getElementById(targetId);
        const lessBtn = btn.parentElement.querySelector('.history-show-less-btn');
        if (content) {
            updatePaginationButtons(content, btn, lessBtn);
            btn.addEventListener('click', () => {
                content.style.display = 'block';
                updatePaginationButtons(content, btn, lessBtn);
            });
        }
    });

    showLessBtns.forEach(btn => {
        const targetId = btn.getAttribute('data-target');
        const content = document.getElementById(targetId);
        const moreBtn = btn.parentElement.querySelector('.history-show-more-btn');
        if (content) {
            btn.addEventListener('click', () => {
                content.style.display = 'none';
                updatePaginationButtons(content, moreBtn, btn);
            });
        }
    });
}

function hideChatHistory() {
    historyLayer.classList.remove('show');
    // Send an escape key to Antigravity to close the History panel
    try {
        fetchWithAuth('/close-history', { method: 'POST' });
    } catch (e) {
        console.error('Failed to close history on desktop:', e);
    }
}

historyBtn.addEventListener('click', showChatHistory);

// --- Select Chat from History ---
async function selectChat(title) {
    // Visual reset while desktop switches conversation
    chatContent.innerHTML = '<div class="loading-state"><div class="loading-spinner"></div><p>Switching Conversation...</p></div>';

    try {
        const res = await fetchWithAuth('/select-chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title })
        });
        const data = await res.json();

        if (data.success) {
            // Close the desktop drawer so it doesn't get synced to mobile view
            await fetchWithAuth('/close-history', { method: 'POST' });

            // Server MutationObserver will push updates automatically
        } else {
            console.error('Failed to select chat:', data.error);
        }
    } catch (e) {
        console.error('Select chat error:', e);
    }
}

// --- Check Chat Status ---
async function checkChatStatus() {
    try {
        const res = await fetchWithAuth('/chat-status');
        const data = await res.json();

        chatIsOpen = data.hasChat || data.editorFound;

        if (!chatIsOpen) {
            showEmptyState();
        }
    } catch (e) {
        console.error('Chat status check failed:', e);
    }
}

// --- Empty State (No Chat Open) ---
function showEmptyState() {
    chatContent.innerHTML = `
        <div class="empty-state">
            <svg class="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                <line x1="9" y1="10" x2="15" y2="10"></line>
            </svg>
            <h2>No Chat Open</h2>
            <p>Start a new conversation or select one from your history to begin chatting.</p>
            <button class="empty-state-btn" id="newChatFromEmptyBtn">
                Start New Conversation
            </button>
        </div>
    `;
}

// --- Utility: Escape HTML ---
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// --- Settings Logic ---


function openModal(title, options, onSelect) {
    modalTitle.textContent = title;
    modalList.innerHTML = '';
    options.forEach(opt => {
        const div = document.createElement('div');
        div.className = 'modal-option';
        
        const isObj = typeof opt === 'object';
        const label = isObj ? opt.label : opt;
        const html = isObj ? opt.html : null;
        
        if (html) {
            div.innerHTML = html;
        } else {
            div.textContent = label;
        }
        
        div.addEventListener('click', () => {
            onSelect(isObj ? opt.value : opt, div);
            if (!(isObj && opt.keepOpen)) {
                closeModal();
            }
        });
        modalList.appendChild(div);
    });
    modalOverlay.classList.add('show');
}

function closeModal() {
    modalOverlay.classList.remove('show');
}

modalOverlay.onclick = (e) => {
    if (e.target === modalOverlay) closeModal();
};

modeBtn.addEventListener('click', () => {
    openModal('Select Mode', ['Fast', 'Planning'], async (mode) => {
        modeText.textContent = 'Setting...';
        try {
            const res = await fetchWithAuth('/set-mode', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mode })
            });
            const data = await res.json();
            if (data.success) {
                currentMode = mode;
                modeText.textContent = mode;
                modeBtn.classList.toggle('active', mode === 'Planning');
            } else {
                alert('Error: ' + (data.error || 'Unknown'));
                modeText.textContent = currentMode;
            }
        } catch (e) {
            modeText.textContent = currentMode;
        }
    });
});

modelBtn.addEventListener('click', () => {
    openModal('Select Model', MODELS, async (model) => {
        const prev = modelText.textContent;
        modelText.textContent = 'Setting...';
        try {
            const res = await fetchWithAuth('/set-model', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model })
            });
            const data = await res.json();
            if (data.success) {
                modelText.textContent = model;
            } else {
                alert('Error: ' + (data.error || 'Unknown'));
                modelText.textContent = prev;
            }
        } catch (e) {
            modelText.textContent = prev;
        }
    });
});

// --- Viewport / Keyboard Handling ---
// We now rely on CSS 100dvh and interactive-widget=resizes-content in the meta viewport
// to handle keyboard resizing natively and smoothly without JS snapping.

const handleTextInputSync = (e) => {
    if (e.target.matches('input[type="text"], input[type="password"], input[type="email"], input[type="number"], input[type="search"], input[type="url"], textarea, vscode-text-field, vscode-text-area')) {
        const agId = e.target.getAttribute('data-ag-id');
        const stableId = e.target.getAttribute('data-stable-id') || agId;
        if (!agId && !stableId) return Promise.resolve();

        if (e.target._lastSentValue === e.target.value) return Promise.resolve();
        e.target._lastSentValue = e.target.value;

        const promise = fetchWithAuth('/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: 'type_text',
                agId: agId,
                stableId: stableId !== agId ? stableId : undefined,
                text: e.target.value
            })
        }).catch(err => console.error('Failed to sync text:', err));

        window.pendingTextSyncPromises = window.pendingTextSyncPromises || new Set();
        window.pendingTextSyncPromises.add(promise);
        promise.finally(() => window.pendingTextSyncPromises.delete(promise));

        e.target._syncPromise = promise;
        return promise;
    }
    return Promise.resolve();
};

document.addEventListener('input', (e) => {
    if (e.target.matches('input[type="text"], input[type="password"], input[type="email"], input[type="number"], input[type="search"], input[type="url"], textarea, vscode-text-field, vscode-text-area')) {
        if (e.target._syncTimer) clearTimeout(e.target._syncTimer);
        e.target._syncTimer = setTimeout(() => {
            handleTextInputSync(e);
        }, 250);
    }
});

document.addEventListener('focusout', (e) => {
    if (e.target.matches('input[type="text"], input[type="password"], input[type="email"], input[type="number"], input[type="search"], input[type="url"], textarea, vscode-text-field, vscode-text-area')) {
        if (e.target._syncTimer) clearTimeout(e.target._syncTimer);
        handleTextInputSync(e);
    }
});

document.addEventListener('change', (e) => {
    if (e.target.matches('input[type="radio"], input[type="checkbox"]')) {
        const agId = e.target.getAttribute('data-ag-id');
        const stableId = e.target.getAttribute('data-stable-id') || agId;
        if (!agId && !stableId) return;

        // Initialize store
        window.localInputStates = window.localInputStates || {};

        // If checking a radio button, clear others with the same name
        if (e.target.type === 'radio' && e.target.checked) {
            const name = e.target.name;
            if (name) {
                const siblings = document.querySelectorAll('input[type="radio"][name=' + CSS.escape(name) + ']');
                siblings.forEach(sibling => {
                    const siblingStableId = sibling.getAttribute('data-stable-id') || sibling.getAttribute('data-ag-id');
                    if (siblingStableId && siblingStableId !== stableId) {
                        window.localInputStates[siblingStableId] = {
                            checked: false,
                            expiresAt: Date.now() + 3000
                        };
                    }
                });
            }
        }

        // Lock local state
        window.localInputStates[stableId] = {
            checked: e.target.checked,
            expiresAt: Date.now() + 3000
        };

        // Sync to server
        fetchWithAuth('/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: 'toggle_input',
                agId: agId,
                stableId: stableId !== agId ? stableId : undefined,
                checked: e.target.checked
            })
        }).then(() => {
            // Rapidly poll snapshot to reflect conditional UI updates (e.g. enabling a submit button) instantly
        }).catch(err => console.error('Failed to sync input state:', err));
    }
});



// --- Remote Click Logic (Thinking/Thought) ---
chatContainer.addEventListener('click', async (e) => {
    // --- Universal Click Proxy ---
    
    const redirectBtn = e.target.closest('.ag-queued-redirect-btn');
    if (redirectBtn) {
        e.preventDefault();
        e.stopPropagation();
        const agId = redirectBtn.getAttribute('data-target-ag-id') || redirectBtn.getAttribute('data-ag-id');
        try {
            await fetchWithAuth('/api/orchestrate/replace_input', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ targetAgId: agId, prefix: '/redirect ' })
            });
        } catch (err) { console.error(err); }
        return;
    }

    // --- Native Mobile Copy Intercept (Bypass Backend) ---
    const copyBtn = e.target.closest('button[aria-label="Copy"]');
    if (copyBtn) {
        e.preventDefault();
        e.stopPropagation();

        // 1. Find the main message bubble or article
        let article = copyBtn.closest('[role="article"], .message');
        let contentWrapper = null;

        if (article) {
            contentWrapper = article.querySelector('.leading-relaxed.select-text, .whitespace-pre-wrap');
        } else {
            // Fallback for new Omni chat structure: find the group container
            const group = copyBtn.closest('.group');
            if (group) {
                const agentArticle = group.querySelector('[aria-label="Agent response"], [aria-label="System response"]');
                const closestUserMsg = copyBtn.closest('[aria-label="User message"]');
                
                if (closestUserMsg) {
                    contentWrapper = closestUserMsg.querySelector('.leading-relaxed.select-text, .whitespace-pre-wrap');
                } else if (agentArticle) {
                    contentWrapper = agentArticle.querySelector('.leading-relaxed.select-text, .whitespace-pre-wrap');
                }
                
                if (!contentWrapper) {
                    const wrappers = Array.from(group.querySelectorAll('.leading-relaxed.select-text, .whitespace-pre-wrap'));
                    const agentWrappers = wrappers.filter(w => !w.closest('[aria-label="User message"]'));
                    if (agentWrappers.length > 0) {
                        contentWrapper = agentWrappers[agentWrappers.length - 1];
                    }
                }
            }
        }
        
        if (!contentWrapper) return;

        // 3. Extract text cleanly using the browser's native selection engine
        const selection = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(contentWrapper);
        selection.removeAllRanges();
        selection.addRange(range);
        
        const textToCopy = selection.toString().trim();
        selection.removeAllRanges(); // Clear immediately so user doesn't see a flash

        if (!textToCopy) return;

        // 4. Execute native copy synchronously
        const success = await copyToClipboard(textToCopy);
        
        if (success) {
            // Guard against double-click state corruption
            if (copyBtn.dataset.copySuccess) return;
            copyBtn.dataset.copySuccess = "true";

            const originalColor = copyBtn.style.color;
            const originalTransition = copyBtn.style.transition;
            const originalTransform = copyBtn.style.transform;
            
            copyBtn.style.transition = 'all 0.5s ease-in-out';
            copyBtn.style.color = '#4ade80';
            copyBtn.style.transform = 'scale(1.1)';
            
            const svg = copyBtn.querySelector('svg');
            let originalSvg = null;
            if (svg) {
                originalSvg = copyBtn.innerHTML;
                copyBtn.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>`;
            }
            setTimeout(() => {
                copyBtn.style.color = originalColor;
                copyBtn.style.transform = originalTransform || '';
                setTimeout(() => {
                    if (copyBtn.style) copyBtn.style.transition = originalTransition || '';
                }, 500);
                
                if (svg && originalSvg) copyBtn.innerHTML = originalSvg;
                delete copyBtn.dataset.copySuccess;
            }, 2000);
        }
        return;
    }



    // Strategy: Check if the clicked element OR its parent contains "Thought" or "Thinking" text.
    // This handles both opening (collapsed) and closing (expanded) states.

    // 1. Find the nearest container that might be the "Thought" block
    const target = e.target.closest('div, span, p, summary, button, details');
    if (!target) return;

    const text = target.innerText || '';

    // --- Auto-Respond to Text Options (e.g. "1. Option A") ---
    // If the user taps on a numbered list item or line, auto-send the number
    const listElement = e.target.closest('li, p, div');
    if (listElement && listElement.closest('.message')) {
        const elText = (listElement.textContent || listElement.innerText || '').trim();
        // Match standard option formats: "1. Option", "1) Option", "[1] Option"
        const optionMatch = elText.match(/^\[?(\d+)\]?[.:\)]?\s+(.+)/);
        
        // Ensure it's short, doesn't have line breaks, and isn't just a generic number (must have some text)
        if (optionMatch && elText.length < 200 && !elText.includes('\n')) {
            const optionNumber = optionMatch[1];
            
            // Provide visual feedback
            listElement.style.opacity = '0.5';
            listElement.classList.add('modal-submit-lock');
            lockedOptionNumber = optionNumber;
            
            // Set input and send
            messageInput.value = optionNumber;
            sendMessage(listElement);
            return;
        }
    }

    // Check if this looks like a clickable UI toggle from Antigravity/Cascade
    // Includes: Thought blocks, Worked status, Edited files status, and File lists
    const isUiToggle = /Thought|Thinking|Worked for|Edited|\d+\s+file/i.test(text) && text.length < 500;

    if (isUiToggle) {
        // Visual feedback - briefly dim the clicked element
        target.style.opacity = '0.5';
        setTimeout(() => target.style.opacity = '1', 300);

        // Extract just the first line for matching
        const firstLine = text.split('\n')[0].trim();

        // Determine which occurrence of this text the user tapped
        // This handles multiple Thought blocks with identical labels
        const allElements = chatContainer.querySelectorAll(target.tagName.toLowerCase());
        let tapIndex = 0;
        for (let i = 0; i < allElements.length; i++) {
            const el = allElements[i];
            const elText = el.innerText || '';
            const elFirstLine = elText.split('\n')[0].trim();

            // Only count if it looks like a UI toggle and matches the first line exactly
            if (/Thought|Thinking|Worked for|Edited|\d+\s+file/i.test(elText) && elText.length < 500 && elFirstLine === firstLine) {
                // If this is our target (or contains it), we've found the correct index
                if (el === target || el.contains(target)) {
                    break;
                }
                tapIndex++;
            }
        }

        try {
            const response = await fetchWithAuth('/remote-click', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    selector: target.tagName.toLowerCase(),
                    index: tapIndex,
                    textContent: firstLine  // Use first line for more reliable matching
                })
            });

            // Reload snapshot multiple times to catch the UI change
            // Desktop animation takes time, so we poll a few times
        } catch (e) {
            console.error('Remote click failed:', e);
        }
        return;
    }


    // --- Native Mobile Copy Intercept (Bypass Backend) ---
    // Instead of only looking for <button>, we find the nearest interactive element 
    // or just pass the exact element tapped, so the desktop can trigger it regardless of HTML tag.
    if (e.target.closest('.mobile-copy-btn')) return;

    let interactiveEl = e.target.closest('button, a, input, select, textarea, [role="button"], [data-testid]');
    
    if (!interactiveEl) {
        let curr = e.target;
        while (curr && curr !== chatContainer && curr !== document.body) {
            if (window.getComputedStyle(curr).cursor === 'pointer') {
                interactiveEl = curr;
                break;
            }
            curr = curr.parentElement;
        }
    }

    // Prioritize actual interactive semantic elements OVER generic data-ag-id nodes
    // because text nodes inside custom elements (like vscode-radio) get their own agId
    // which incorrectly swallows the click target and breaks optimistic UI.
    const elToClick = interactiveEl || 
                      e.target.closest('vscode-radio, vscode-button, vscode-checkbox, button, a, [role="button"]') || 
                      e.target.closest('[data-ag-id]') || 
                      e.target;
                      
    const agId = elToClick.getAttribute('data-ag-id');

    if (elToClick._optimisticLocked) {
        if (e.cancelable) e.preventDefault();
        e.stopPropagation();
        return;
    }

    if (agId || elToClick !== chatContainer) {
        
        const checkAriaLabel = (interactiveEl && interactiveEl.getAttribute('aria-label')) || elToClick.getAttribute('aria-label');
        const isThumbBtn = checkAriaLabel === 'Good response' || checkAriaLabel === 'Bad response';

        // Optimistic UI Updates for instant perceived performance
        const elText = (elToClick.innerText || '').trim().toLowerCase();
        const tag = (elToClick.tagName || '').toUpperCase();
        const isSubmitBtn = (tag === 'BUTTON' || tag === 'VSCODE-BUTTON') && (elText === 'submit' || elText === 'confirm' || elText === 'continue' || elText === 'yes' || elText === 'no');
        const isRadioBtn = tag === 'VSCODE-RADIO' || (tag === 'INPUT' && elToClick.type === 'radio');
        const isCheckbox = tag === 'VSCODE-CHECKBOX' || (tag === 'INPUT' && elToClick.type === 'checkbox');

        const stableId = elToClick.getAttribute('data-stable-id') || agId;

        if (isSubmitBtn) {
            elToClick.innerHTML = '<span class="loading-spinner" style="width:14px;height:14px;border-width:2px;border-top-color:transparent;border-radius:50%;animation:spin 1s linear infinite;margin-right:8px;display:inline-block;vertical-align:middle;"></span>Working...';
            elToClick.style.opacity = '0.8';
            elToClick.style.pointerEvents = 'none';
        } else if (isThumbBtn) {
            elToClick.classList.add('active-thumb');
            elToClick.style.color = '#3b82f6';
            if (elToClick.querySelector('svg')) elToClick.querySelector('svg').style.fill = '#3b82f6';
        } else if (isCheckbox && stableId) {
            window.pendingMutations = window.pendingMutations || new Set();
            window.pendingMutations.add(stableId);
            // Browser natively toggles .checked before the click event fires.
            // So elToClick.checked is ALREADY the new intended state.
            const isNowChecked = elToClick.checked;
            elToClick.currentChecked = isNowChecked;
            if (isNowChecked) {
                elToClick.setAttribute('checked', '');
                elToClick.setAttribute('current-checked', '');
            } else {
                elToClick.removeAttribute('checked');
                elToClick.removeAttribute('current-checked');
            }
            
            // Add a brief optimistic highlight to the parent container (like an option row)
            const row = elToClick.closest('div, label, li');
            if (row && row !== elToClick && row.innerText.length < 150) {
                row.style.transition = 'none';
                row.style.backgroundColor = isNowChecked ? 'rgba(59, 130, 246, 0.15)' : 'transparent';
            }
        } else if (isRadioBtn && stableId) {
            window.pendingMutations = window.pendingMutations || new Set();
            window.pendingMutations.add(stableId);
            elToClick.checked = true;
            elToClick.currentChecked = true;
            elToClick.setAttribute('checked', '');
            elToClick.setAttribute('current-checked', '');
            
            // Highlight the selected radio's parent row
            const row = elToClick.closest('div, label, li');
            if (row && row !== elToClick && row.innerText.length < 150) {
                row.style.transition = 'none';
                row.style.backgroundColor = 'rgba(59, 130, 246, 0.15)';
            }
            
            const name = elToClick.getAttribute('name');
            let siblings = [];
            if (name) {
                siblings = Array.from(document.querySelectorAll(`[name="${CSS.escape(name)}"]`));
            } else {
                const container = elToClick.closest('vscode-radio-group, [role="radiogroup"], ul, .modal-content, form, div.flex.flex-col');
                if (container) {
                    siblings = Array.from(container.querySelectorAll('vscode-radio, input[type="radio"]'));
                }
            }
            
            siblings.forEach(sib => {
                if (sib !== elToClick) {
                    const sibId = sib.getAttribute('data-stable-id') || sib.getAttribute('data-ag-id');
                    if (sibId) window.pendingMutations.add(sibId);
                    sib.checked = false;
                    sib.currentChecked = false;
                    sib.removeAttribute('checked');
                    sib.removeAttribute('current-checked');
                    
                    const sibRow = sib.closest('div, label, li');
                    if (sibRow && sibRow !== sib && (sibRow.innerText || '').length < 150) {
                        sibRow.style.transition = 'none';
                        sibRow.style.backgroundColor = 'transparent';
                    }
                }
            });
        }
        elToClick._optimisticLocked = true;

        // Lock out the element to prevent double-tapping while the network request is in flight
        const originalPointerEvents = elToClick.style.pointerEvents;
        if (!isSubmitBtn && !isCheckbox && !isRadioBtn) { // Buttons lock out, inputs stay interactive
            elToClick.style.pointerEvents = 'none';
        }

        const activeInputs = Array.from(document.querySelectorAll('input[type="text"], input[type="password"], input[type="email"], input[type="number"], input[type="search"], input[type="url"], textarea, vscode-text-field, vscode-text-area'));
        
        activeInputs.forEach(input => {
            if (input._syncTimer) {
                clearTimeout(input._syncTimer);
                input._syncTimer = null;
                handleTextInputSync({ target: input });
            } else if (input.value !== input._lastSentValue) {
                handleTextInputSync({ target: input });
            }
        });

        if (window.pendingTextSyncPromises && window.pendingTextSyncPromises.size > 0) {
            await Promise.all(Array.from(window.pendingTextSyncPromises)).catch(err => console.error('Sync error:', err));
        }

        try {
            fetchWithAuth('/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'click_element', agId: agId })
            }).then(() => {
                if (stableId && window.pendingMutations) {
                    window.pendingMutations.delete(stableId);
                    if (isRadioBtn) {
                        const name = elToClick.getAttribute('name');
                        let siblings = [];
                        if (name) {
                            siblings = Array.from(document.querySelectorAll(`[name="${CSS.escape(name)}"]`));
                        } else {
                            const container = elToClick.closest('vscode-radio-group, [role="radiogroup"], ul, .modal-content, form, div.flex.flex-col');
                            if (container) {
                                siblings = Array.from(container.querySelectorAll('vscode-radio, input[type="radio"]'));
                            }
                        }
                        siblings.forEach(sib => {
                            const sibId = sib.getAttribute('data-stable-id') || sib.getAttribute('data-ag-id');
                            if (sibId) window.pendingMutations.delete(sibId);
                        });
                    }
                }
                if (checkAriaLabel === 'Clear history') {
                    chatContent.innerHTML = '<div class="loading-state"><div class="loading-spinner"></div><p>Clearing history...</p></div>';
                }
                // Rapidly poll snapshot to reflect the click instantly and reduce input delay
            }).catch(err => {
                console.error('Failed to remote click:', err);
            }).finally(() => {
                elToClick._optimisticLocked = false;
                if (!isSubmitBtn && elToClick.style) {
                    elToClick.style.pointerEvents = originalPointerEvents || '';
                }
            });
        } catch (e) {
            if (!isSubmitBtn && elToClick.style) {
                elToClick.style.pointerEvents = originalPointerEvents || '';
            }
        }

        // Enhanced visual feedback for thumbs up/down
        if (isThumbBtn) {
            const btn = interactiveEl || elToClick;
            const article = btn.closest('[role="article"]') || (btn.closest('.group') ? btn.closest('.group').querySelector('[role="article"]') : null);
            const messageId = article ? article.getAttribute('data-message-id') : null;
            
            if (messageId) {
                window.tappedThumbs = window.tappedThumbs || {};
                const isAlreadyActive = btn.classList.contains('active-thumb');
                
                if (isAlreadyActive) {
                    // Toggle off
                    btn.classList.remove('active-thumb');
                    if (window.tappedThumbs[messageId] === checkAriaLabel) {
                        delete window.tappedThumbs[messageId];
                    }
                } else {
                    // Toggle on
                    btn.classList.add('active-thumb');
                    window.tappedThumbs[messageId] = checkAriaLabel;
                    
                    // If they tapped one, remove the other (mutually exclusive)
                    const oppositeLabel = checkAriaLabel === 'Good response' ? 'Bad response' : 'Good response';
                    
                    // Remove visual class from opposite button if it's currently on screen
                    const oppositeBtnList = Array.from(document.querySelectorAll(`button[aria-label="${oppositeLabel}"]`));
                    oppositeBtnList.forEach(oppBtn => {
                        const oppArticle = oppBtn.closest('[role="article"]') || (oppBtn.closest('.group') ? oppBtn.closest('.group').querySelector('[role="article"]') : null);
                        if (oppArticle && oppArticle.getAttribute('data-message-id') === messageId) {
                            oppBtn.classList.remove('active-thumb');
                        }
                    });
                }
            }
        }

        // Generate robust fallback selector
        let fallbackSelector = elToClick.tagName.toLowerCase();
        const testId = elToClick.getAttribute('data-testid');
        const ariaLabel = elToClick.getAttribute('aria-label');
        if (testId) {
            fallbackSelector += `[data-testid="${testId}"]`;
        } else if (ariaLabel) {
            fallbackSelector += `[aria-label="${ariaLabel}"]`;
        } else if (elToClick.className && typeof elToClick.className === 'string') {
            const cls = elToClick.className.trim().split(/\s+/)[0];
            if (cls) fallbackSelector += `.${CSS.escape(cls)}`;
        }

        // Generate text content filter
        let textContent = (elToClick.innerText || elToClick.textContent || '').trim();
        if (textContent.length > 50) textContent = textContent.substring(0, 50);

        // Check if this is a Revert button
        const isRevertBtn = (ariaLabel || '').toLowerCase().includes('revert') || 
                            (ariaLabel || '').toLowerCase().includes('undo changes') || 
                            textContent.toLowerCase().includes('revert') || 
                            elToClick.getAttribute('data-testid') === 'revert-button';
        let autoConfirmText = null;
        if (isRevertBtn) {
            if (!window.confirm('Are you sure you want to revert to this step?')) {
                return; // User cancelled
            }
            autoConfirmText = 'Revert'; // Tell backend to auto-click the confirm button in the desktop modal
        }

        // Calculate index
        let elements = [];
        try {
            elements = Array.from(document.querySelectorAll(fallbackSelector));
        } catch(e) { console.error('[PhoneUI] Error:', e); }
        let index = elements.indexOf(elToClick);
        if (index === -1) index = 0;

        const sendRemoteClick = async () => {
            try {
                await fetchWithAuth('/remote-click', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        id: agId || '',
                        selector: fallbackSelector,
                        index: index,
                        textContent: textContent,
                        autoConfirmText: autoConfirmText
                    })
                });
                
            } catch (err) {
                console.error('Remote click failed:', err);
            }
        };

        if (isThumbBtn) {
            window.thumbClickQueue = window.thumbClickQueue || Promise.resolve();
            window.activeThumbClicks = (window.activeThumbClicks || 0) + 1;
            window.isThumbAnimating = true;

            // Clear any stray timers from old debounce logic if they exist
            if (window.thumbAnimationTimer) clearTimeout(window.thumbAnimationTimer);

            window.thumbClickQueue = window.thumbClickQueue.then(async () => {
                // Wait 200ms before sending click to let the local CSS transition play
                await new Promise(r => setTimeout(r, 200));
                await sendRemoteClick();
                // Tail buffer to let server DOM settle
                await new Promise(r => setTimeout(r, 200));
            }).catch(e => console.error(e))
              .finally(() => {
                window.activeThumbClicks--;
                if (window.activeThumbClicks <= 0) {
                    window.activeThumbClicks = 0;
                    window.isThumbAnimating = false;
                    if (window.pendingSnapshot) loadSnapshot();
                }
            });
        } else {
            sendRemoteClick();
        }
    }
});

// --- Initial Event Listeners (Refactored from inline) ---
if (enableHttpsBtn) enableHttpsBtn.addEventListener('click', enableHttps);
if (dismissSslBtn) dismissSslBtn.addEventListener('click', dismissSslBanner);
if (closeModalBtn) closeModalBtn.addEventListener('click', closeModal);
if (backHistoryBtn) backHistoryBtn.addEventListener('click', hideChatHistory);

quickActionChips.forEach(chip => {
    chip.addEventListener('click', () => {
        const actionText = chip.getAttribute('data-action') || chip.innerText.trim();
        // Handle specific cases if needed, otherwise just pass the text
        if (actionText.includes('Explain')) {
            quickAction('Explain this code in detailed and elaborate manner.');
        } else if (actionText.includes('Fix')) {
            quickAction('Please fix the bugs in this code...');
        } else if (actionText.includes('Create')) {
            quickAction('Please create or update documentation for this code.');
        } else {
            quickAction(actionText);
        }
    });
});

// Delegation for dynamic history items
if (historyList) {
    historyList.addEventListener('click', (e) => {
        const newBtn = e.target.closest('.history-new-btn');
        const card = e.target.closest('.history-card');
        
        if (newBtn) {
            hideChatHistory();
            startNewChat();
        } else if (card) {
            if (card.getAttribute('data-active') === 'true') return; // Ignore clicks on the active chat
            
            const title = card.getAttribute('data-title');
            
            // Debug visual feedback
            card.style.opacity = '0.5';

            // Close the mobile UI overlay immediately for responsiveness
            // (We avoid hideChatHistory() to prevent POST /close-history from racing with /select-chat)
            historyLayer.classList.remove('show');
            
            // Force hide it after the transition (or immediately if transition fails)
            setTimeout(() => {
                historyLayer.style.display = 'none';
            }, 300);
            
            selectChat(title);
        }
    });

}

// Delegation for empty state
chatContent.addEventListener('click', (e) => {
    if (e.target.closest('#newChatFromEmptyBtn')) {
        startNewChat();
    }
});

// Add click handler for task indicator
const taskIndicator = document.getElementById('taskIndicator');
if (taskIndicator) {
    taskIndicator.addEventListener('click', () => {
        if (currentRunningTasksList && currentRunningTasksList.length > 0) {
            const options = currentRunningTasksList.map(task => ({
                value: task,
                keepOpen: true,
                html: `<div style="display: flex; justify-content: space-between; align-items: center; width: 100%;"><span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-right: 8px; flex: 1;">${task}</span><div style="flex: 0 0 16px; display: flex; align-items: center; justify-content: center;"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 -960 960 960" fill="currentColor" class="text-red-500 opacity-80 hover:opacity-100 transition-opacity"><path d="M330-330H630V-630H330v300ZM480.07-100q-78.84,0-148.2-29.92T211.18-211.13T129.93-331.76T100-479.93t29.92-148.2t81.21-120.68t120.63-81.25T479.93-860t148.2,29.92t120.68,81.21t81.25,120.63T860-480.07t-29.92,148.2T748.87-211.18T628.24-129.93T480.07-100ZM480-160q134,0 227-93t93-227T707-707T480-800T253-707T160-480t93,227t227,93Zm0-320Z"/></svg></div></div>`
            }));
            openModal('Running Tasks', options, async (selectedTask, optionDiv) => {
                optionDiv.style.opacity = '0.5';
                optionDiv.style.pointerEvents = 'none';
                try {
                    await fetchWithAuth('/kill-task', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ taskName: selectedTask })
                    });
                    setTimeout(() => {
                        optionDiv.remove();
                        if (document.querySelectorAll('#modal-list .modal-option').length === 0) {
                            closeModal();
                        }
                    }, 500);
                } catch (e) {
                    console.error('Failed to kill task:', e);
                }
            });
        }
    });
}

// --- Init ---
updateInputButtons();
connectWebSocket();
// Sync state initially and every 2 seconds to keep phone in sync with desktop changes
fetchAppState();
setInterval(fetchAppState, 2000);

// Check chat status initially and periodically
checkChatStatus();

// --- Initialize Native File Upload ---
function initializeFileUpload() {
    const attachMenuBtn = document.getElementById('attachMenuBtn');
    const attachMenu = document.getElementById('attachMenu');
    const docInput = document.getElementById('mobile-file-document');
    const mediaInput = document.getElementById('mobile-file-media');

    if (attachMenuBtn && attachMenu && !attachMenuBtn.dataset.initialized) {
        attachMenuBtn.dataset.initialized = 'true';
        attachMenuBtn.addEventListener('click', () => {
            attachMenu.classList.toggle('show');
        });

        document.addEventListener('click', (e) => {
            if (!attachMenu.contains(e.target) && !attachMenuBtn.contains(e.target)) {
                attachMenu.classList.remove('show');
            }
        });
    }

    window.uploadFiles = async (files) => {
        if (!files || files.length === 0) return;
        
        if (window.isFileUploading) return;
        window.isFileUploading = true;
        
        const spinner = document.createElement('div');
        spinner.className = 'upload-spinner';
        spinner.innerHTML = '<div class="spinner"></div>';
        document.body.appendChild(spinner);
        
        const formData = new FormData();
        for (let i = 0; i < files.length; i++) {
            formData.append('files', files[i]);
        }
        
        try {
            const res = await fetchWithAuth('/upload-attachment', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            if (data.filenames) {
                window.stagedAttachments.push(...data.filenames);
                renderStagedAttachments();
            }
        } catch (err) {
            console.error('File upload failed:', err);
            alert('Upload failed: ' + err.message);
        } finally {
            window.isFileUploading = false;
            if (spinner.parentNode) spinner.parentNode.removeChild(spinner);
        }
    };

    const handleUpload = async (event) => {
        if (attachMenu) attachMenu.classList.remove('show');
        await window.uploadFiles(event.target.files);
        event.target.value = ''; // Reset so same file can be selected again
    };

    if (docInput && !docInput.dataset.initialized) {
        docInput.dataset.initialized = 'true';
        docInput.addEventListener('change', handleUpload);
    }
    if (mediaInput && !mediaInput.dataset.initialized) {
        mediaInput.dataset.initialized = 'true';
        mediaInput.addEventListener('change', handleUpload);
    }
}
initializeFileUpload();

// --- Push Notifications ---
async function initializePushNotifications() {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
        console.warn('[PUSH] Web Push not supported in this browser.');
        alert('Web Push is not supported in this browser or wrapper app. PushManager is missing.');
        return;
    }

    try {
        const swReg = await navigator.serviceWorker.register('/sw.js?v=3');
        swReg.update(); // Force check for updates bypassing some caches
        console.log('[PUSH] Service Worker Registered');

        let subscription = await swReg.pushManager.getSubscription();

        if (!subscription) {
            // Need to subscribe
            const res = await fetchWithAuth('/vapidPublicKey');
            if (!res.ok) {
                const text = await res.text();
                throw new Error(`Failed to fetch VAPID key. Status: ${res.status} ${res.statusText}. Body: ${text.substring(0, 50)}`);
            }
            const vapidPublicKey = await res.text();
            const convertedVapidKey = urlBase64ToUint8Array(vapidPublicKey);

            subscription = await swReg.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: convertedVapidKey
            });
            console.log('[PUSH] Subscribed to Web Push');
        }

        // Always send subscription to server to ensure it's registered
        await fetchWithAuth('/subscribe', {
            method: 'POST',
            body: JSON.stringify(subscription),
            headers: {
                'Content-Type': 'application/json'
            }
        });
        console.log('[PUSH] Subscription sent to server.');
    } catch (e) {
        console.error('[PUSH] Failed to initialize push notifications', e);
        alert('Push init failed: ' + e.message);
    }
}

// Utility to convert Base64 URL-safe string to Uint8Array
function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding)
        .replace(/\-/g, '+')
        .replace(/_/g, '/');

    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);

    for (let i = 0; i < rawData.length; ++i) {
        outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
}

// Initialize Push Notifications
initializePushNotifications();

// --- Notification Clearing ---
function clearNotifications() {
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.ready.then(reg => {
            if (reg.active) {
                reg.active.postMessage('clear_notifications');
            }
        });
    }
    // Clear the app icon badge (the unread number on the home screen)
    if ('clearAppBadge' in navigator) {
        navigator.clearAppBadge().catch(console.error);
    }
}
clearNotifications();
document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
        clearNotifications();
    }
});
window.addEventListener('focus', clearNotifications);

// --- Voice Input Logic ---
function initializeVoiceInput() {
    if (!voiceBtn) return;
    
    let mediaRecorder = null;
    let audioChunks = [];
    let isRecording = false;
    let startTime = 0;
    let maxDurationTimeout = null;

    const stopRecording = () => {
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            mediaRecorder.stop();
        }
    };

    const startRecording = async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            
            // Prefer webm, fallback to mp4
            let mimeType = '';
            if (MediaRecorder.isTypeSupported('audio/webm')) {
                mimeType = 'audio/webm';
            } else if (MediaRecorder.isTypeSupported('audio/mp4')) {
                mimeType = 'audio/mp4';
            }

            const options = mimeType ? { mimeType } : {};
            mediaRecorder = new MediaRecorder(stream, options);
            audioChunks = [];

            mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) {
                    audioChunks.push(e.data);
                }
            };

            mediaRecorder.onstop = () => {
                isRecording = false;
                voiceBtn.classList.remove('recording');
                clearTimeout(maxDurationTimeout);
                stream.getTracks().forEach(track => track.stop());

                const duration = Date.now() - startTime;
                
                // Discard if < 1000ms or 0 chunks
                if (duration < 1000 || audioChunks.length === 0) {
                    return;
                }
                
                const blob = new Blob(audioChunks, { type: mimeType || 'audio/webm' });
                if (blob.size === 0) return;

                const ext = mimeType.includes('mp4') ? 'mp4' : 'webm';
                const file = new File([blob], `voice_memo_${Date.now()}.${ext}`, { type: blob.type });

                if (typeof window.uploadFiles === 'function') {
                    window.uploadFiles([file]);
                }
            };

            mediaRecorder.start();
            isRecording = true;
            startTime = Date.now();
            voiceBtn.classList.add('recording');

            // 60 second timeout
            maxDurationTimeout = setTimeout(() => {
                if (isRecording) stopRecording();
            }, 60000);

        } catch (err) {
            console.error('Voice recording error:', err);
            if (err.name === 'NotAllowedError') {
                alert('Microphone access was denied. Please allow it in your browser settings.');
            } else {
                alert('Error accessing microphone: ' + err.message);
            }
        }
    };

    voiceBtn.addEventListener('click', () => {
        if (isRecording) {
            stopRecording();
        } else {
            startRecording();
        }
    });
}
initializeVoiceInput();


function showToast(message) {
    const toast = document.createElement('div');
    toast.textContent = message;
    toast.style.position = 'fixed';
    toast.style.bottom = '20px';
    toast.style.left = '50%';
    toast.style.transform = 'translateX(-50%)';
    toast.style.backgroundColor = 'rgba(0, 0, 0, 0.8)';
    toast.style.color = '#fff';
    toast.style.padding = '12px 24px';
    toast.style.borderRadius = '24px';
    toast.style.zIndex = '9999';
    toast.style.fontSize = '14px';
    toast.style.boxShadow = '0 4px 12px rgba(0,0,0,0.5)';
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.3s ease';
    toast.style.maxWidth = '90%';
    toast.style.wordBreak = 'break-word';
    document.body.appendChild(toast);
    
    requestAnimationFrame(() => {
        toast.style.opacity = '1';
    });
    
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}
