const fs = require('fs');
const jsdom = require("jsdom");
const { JSDOM } = jsdom;

const h = fs.readFileSync('dom_dump.html', 'utf8');
const dom = new JSDOM(h);
const copyBtns = dom.window.document.querySelectorAll('button[aria-label="Copy"]');

copyBtns.forEach((btn, i) => {
    let article = btn.closest('[role="article"], .message');
    let contentWrapper = null;
    let strategy = '';

    if (article) {
        contentWrapper = article.querySelector('.leading-relaxed.select-text, .whitespace-pre-wrap');
        strategy = 'closest-article';
    } else {
        const group = btn.closest('.group');
        if (group) {
            const agentArticle = group.querySelector('[aria-label="Agent response"], [aria-label="System response"]');
            
            // Check if the button belongs to the User Message!
            // Wait, does the User message have its own copy button?
            // Let's see if the button is inside a User message
            const closestUserMsg = btn.closest('[aria-label="User message"]');
            
            if (closestUserMsg) {
                contentWrapper = closestUserMsg.querySelector('.leading-relaxed.select-text, .whitespace-pre-wrap');
                strategy = 'closest-user-msg';
            } else if (agentArticle) {
                contentWrapper = agentArticle.querySelector('.leading-relaxed.select-text, .whitespace-pre-wrap');
                strategy = 'agent-article-in-group';
            }
            
            if (!contentWrapper) {
                // To avoid getting the user message if we are an agent button, we filter out user message wrappers.
                const wrappers = Array.from(group.querySelectorAll('.leading-relaxed.select-text, .whitespace-pre-wrap'));
                const agentWrappers = wrappers.filter(w => !w.closest('[aria-label="User message"]'));
                if (agentWrappers.length > 0) {
                    contentWrapper = agentWrappers[agentWrappers.length - 1];
                    strategy = 'last-agent-wrapper';
                }
            }
        }
    }
    
    if (contentWrapper) {
        console.log(`Button ${i} (${strategy}):`, contentWrapper.textContent.substring(0, 30).replace(/\n/g, ' '));
    } else {
        console.log(`Button ${i}: NO WRAPPER FOUND`);
    }
});
