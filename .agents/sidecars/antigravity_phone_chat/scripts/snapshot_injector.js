(async () => {
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
                // Check for background tool execution spinners
                const spinners = document.querySelectorAll('.animate-spin');
                for (let el of spinners) {
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
    })()