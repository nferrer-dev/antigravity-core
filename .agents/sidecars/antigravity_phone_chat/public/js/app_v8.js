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
        const res = await fetchWithAuth('/app-state');
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
function connectWebSocket() {
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
    };

    ws.onclose = () => {
        console.log('WS Disconnected');
        updateStatus(false);
        setTimeout(connectWebSocket, 2000);
    };
}

let isGenerating = false;
let optimisticGeneratingUntil = 0;
let generationPlaceholderInterval = null;

function updateInputButtons() {
    const wrapper = document.querySelector('.input-wrapper');
    
    // Always evaluate Send Button visibility based on input value
    if (messageInput.value.trim().length > 0) {
        sendBtn.classList.add('visible');
    } else {
        sendBtn.classList.remove('visible');
    }

    if (isGenerating) {
        if (wrapper) wrapper.classList.add('generating');
        stopBtn.classList.add('visible');
        
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
        stopBtn.classList.remove('visible');
        
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
        
        if (!updateDOMPreservingScroll(chatContent, data.html)) {
            chatContent.innerHTML = data.html;
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
async function sendMessage() {
    const message = messageInput.value.trim();
    if (!message) return;

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
            body: JSON.stringify({ message })
        });

        // Always reload snapshot to check if message appeared
        setTimeout(loadSnapshot, 300);
        setTimeout(loadSnapshot, 800);
        setTimeout(checkChatStatus, 1000);

        // Don't revert the input - if user sees the message in chat, it was sent
        // Only log errors for debugging, don't show alert popups
        if (!res.ok) {
            console.warn('Send response not ok, but message may have been sent:', await res.json().catch(() => ({})));
        }
    } catch (e) {
        // Network error - still try to refresh in case it went through
        console.error('Send error:', e);
        setTimeout(loadSnapshot, 500);
    } finally {
        sendBtn.disabled = false;
        sendBtn.style.opacity = '1';
    }
}

// --- Event Listeners ---
sendBtn.addEventListener('click', sendMessage);


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
function updateDOMPreservingScroll(container, newHTML) {
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
    
    function morph(oldEl, newEl) {
        if (!oldEl || !newEl) return;
        
        if (oldEl === currentScroll) {
            oldEl.innerHTML = newEl.innerHTML;
            if (newEl.attributes) {
                for (let i = 0; i < newEl.attributes.length; i++) {
                    const attr = newEl.attributes[i];
                    if (oldEl.getAttribute(attr.name) !== attr.value) {
                        oldEl.setAttribute(attr.name, attr.value);
                    }
                }
            }
            return;
        }
        
        if (!oldEl.contains(currentScroll) && oldEl !== container) {
            oldEl.parentNode.replaceChild(newEl.cloneNode(true), oldEl);
            return;
        }
        
        if (oldEl.attributes && newEl.attributes) {
            for (let i = 0; i < newEl.attributes.length; i++) {
                const attr = newEl.attributes[i];
                if (oldEl.getAttribute(attr.name) !== attr.value) {
                    oldEl.setAttribute(attr.name, attr.value);
                }
            }
        }
        
        const oldChildren = Array.from(oldEl.childNodes);
        const newChildren = Array.from(newEl.childNodes);
        
        for (let i = 0; i < Math.max(oldChildren.length, newChildren.length); i++) {
            if (!oldChildren[i]) {
                oldEl.appendChild(newChildren[i].cloneNode(true));
            } else if (!newChildren[i]) {
                oldEl.removeChild(oldChildren[i]);
            } else if (oldChildren[i].nodeType !== newChildren[i].nodeType || oldChildren[i].nodeName !== newChildren[i].nodeName) {
                oldEl.replaceChild(newChildren[i].cloneNode(true), oldChildren[i]);
            } else if (oldChildren[i].nodeType === Node.TEXT_NODE) {
                if (oldChildren[i].nodeValue !== newChildren[i].nodeValue) {
                    oldChildren[i].nodeValue = newChildren[i].nodeValue;
                }
            } else {
                morph(oldChildren[i], newChildren[i]);
            }
        }
    }
    
    morph(container, doc.body);
    
    const distanceFromBottom = scrollHeight - scrollPos - clientHeight;
    
    // Wait for the browser to recalculate layout after DOM insertion
    // so that currentScroll.scrollHeight reflects the newly loaded messages
    requestAnimationFrame(() => {
        const activeScroll = getScrollContainer(); // Get the NEW scroll container in case morph replaced it
        if (!activeScroll) return;
        
        const newScrollPos = activeScroll.scrollHeight - activeScroll.clientHeight - distanceFromBottom;
        
        // Lock the anchor for 1 second to handle CSS transitions and image loads that expand height
        anchorDistanceFromBottom = distanceFromBottom;
        clearTimeout(anchorScrollTimeout);
        anchorScrollTimeout = setTimeout(() => {
            anchorDistanceFromBottom = null;
        }, 1000);
        
        isProgrammaticScroll = true;
        if (isUserScrollLocked) {
            activeScroll.scrollTop = Math.max(0, newScrollPos);
        } else if (isNearBottom) {
            activeScroll.scrollTop = activeScroll.scrollHeight;
        } else {
            activeScroll.scrollTop = Math.max(0, newScrollPos);
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

        // After scrolling desktop, reload snapshot to get newly visible content
        // (Antigravity uses virtualized scrolling - only visible messages are in DOM)
        if (!snapshotReloadPending) {
            snapshotReloadPending = true;
            setTimeout(() => {
                loadSnapshot();
                snapshotReloadPending = false;
            }, 300);
        }
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
    lastTouchY = e.touches[0].clientY;
}, { passive: true });

chatContent.addEventListener('touchmove', (e) => {
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
    } catch (e) { }
    setTimeout(() => stopBtn.style.opacity = '1', 500);
});

// --- New Chat Logic ---
async function startNewChat() {
    newChatBtn.style.opacity = '0.5';
    newChatBtn.style.pointerEvents = 'none';

    try {
        const res = await fetchWithAuth('/new-chat', { method: 'POST' });
        const data = await res.json();

        if (data.success) {
            // Reload snapshot to show new empty chat
            setTimeout(loadSnapshot, 500);
            setTimeout(loadSnapshot, 1000);
            setTimeout(checkChatStatus, 1500);
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

        const chats = data.chats || [];
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

        // Render chats
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

        // Group chats by workspace
        const groupedChats = {};
        chats.forEach(chat => {
            const ws = chat.workspace || 'Global';
            if (!groupedChats[ws]) groupedChats[ws] = [];
            groupedChats[ws].push(chat);
        });

        Object.keys(groupedChats).forEach(ws => {
            html += `<div class="history-group-header">${escapeHtml(ws)}</div>`;
            groupedChats[ws].forEach(chat => {
                const safeTitle = chat.title.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
                html += `
                    <div class="history-card" data-title="${safeTitle}">
                        <div class="history-card-icon">
                            <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                            </svg>
                        </div>
                        <div class="history-card-content">
                            <span class="history-card-title">${escapeHtml(chat.title)}</span>
                        </div>
                        <div class="history-card-arrow">
                            <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
                                <polyline points="9 18 15 12 9 6"></polyline>
                            </svg>
                        </div>
                    </div>
                `;
            });
        });

        html += `</div>`;

        historyList.innerHTML = html;

    } catch (e) {
        historyList.innerHTML = `
            <div class="history-state-container">
                <div class="history-state-icon">🔌</div>
                <div class="history-state-title">Connection Error</div>
                <div class="history-state-desc">Failed to reach the server.</div>
            </div>
        `;
    }
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

            // Persistent polling to catch delayed desktop render/update
            let attempts = 0;
            const poll = setInterval(async () => {
                await loadSnapshot();
                attempts++;
                if (attempts > 10) clearInterval(poll);
            }, 500);
        } else {
            console.error('Failed to select chat:', data.error);
            setTimeout(loadSnapshot, 500);
        }
    } catch (e) {
        console.error('Select chat error:', e);
        setTimeout(loadSnapshot, 500);
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
        div.textContent = opt;
        div.addEventListener('click', () => {
            onSelect(opt);
            closeModal();
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


// --- Remote Click Logic (Thinking/Thought) ---
chatContainer.addEventListener('click', async (e) => {
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
        const elText = (listElement.innerText || '').trim();
        // Match standard option formats: "1. Option", "1) Option", "[1] Option"
        const optionMatch = elText.match(/^\[?(\d+)\]?[.:\)]?\s+(.+)/);
        
        // Ensure it's short, doesn't have line breaks, and isn't just a generic number (must have some text)
        if (optionMatch && elText.length < 200 && !elText.includes('\n')) {
            const optionNumber = optionMatch[1];
            
            // Provide visual feedback
            listElement.style.opacity = '0.5';
            setTimeout(() => listElement.style.opacity = '1', 300);
            
            // Set input and send
            messageInput.value = optionNumber;
            sendMessage();
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
            setTimeout(loadSnapshot, 400);   // Quick check
            setTimeout(loadSnapshot, 800);   // After animation starts
            setTimeout(loadSnapshot, 1500);  // After animation completes
        } catch (e) {
            console.error('Remote click failed:', e);
        }
        return;
    }

    // --- Universal Click Proxy ---
    // Instead of only looking for <button>, we find the nearest interactive element 
    // or just pass the exact element tapped, so the desktop can trigger it regardless of HTML tag.
    if (e.target.closest('.mobile-copy-btn')) return;

    let interactiveEl = e.target.closest('button, a, [role="button"]');
    
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

    const elToClick = interactiveEl || e.target.closest('[data-ag-id]') || e.target;
    const agId = elToClick.getAttribute('data-ag-id');

    if (agId || elToClick !== chatContainer) {
        const checkAriaLabel = (interactiveEl && interactiveEl.getAttribute('aria-label')) || elToClick.getAttribute('aria-label');
        const isThumbBtn = checkAriaLabel === 'Good response' || checkAriaLabel === 'Bad response';

        // Smoother, slower visual feedback (Skip for thumbs up/down, they have their own visual state)
        if (!isThumbBtn) {
            const originalOpacity = elToClick.style.opacity;
            const originalTransition = elToClick.style.transition;
            elToClick.style.transition = 'opacity 0.4s ease-in-out';
            elToClick.style.opacity = '0.3';
            setTimeout(() => {
                elToClick.style.opacity = originalOpacity || '1';
                setTimeout(() => {
                    if (elToClick.style) elToClick.style.transition = originalTransition || '';
                }, 400);
            }, 400);
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
        const ariaLabel = elToClick.getAttribute('aria-label');
        if (ariaLabel) {
            fallbackSelector += `[aria-label="${ariaLabel}"]`;
        } else if (elToClick.className && typeof elToClick.className === 'string') {
            const cls = elToClick.className.trim().split(/\s+/)[0];
            if (cls) fallbackSelector += `.${CSS.escape(cls)}`;
        }

        // Generate text content filter
        let textContent = (elToClick.innerText || elToClick.textContent || '').trim();
        if (textContent.length > 50) textContent = textContent.substring(0, 50);

        // Calculate index
        let elements = [];
        try {
            elements = Array.from(document.querySelectorAll(fallbackSelector));
        } catch (e) {}
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
                        textContent: textContent
                    })
                });
                
                setTimeout(loadSnapshot, 1000);
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

// --- Init ---
updateInputButtons();
connectWebSocket();
// Sync state initially and every 5 seconds to keep phone in sync with desktop changes
fetchAppState();
setInterval(fetchAppState, 5000);

// Check chat status initially and periodically
checkChatStatus();
setInterval(checkChatStatus, 10000); // Check every 10 seconds

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
