const CDP = require('chrome-remote-interface');
const fs = require('fs');

(async function() {
    try {
        const client = await CDP({ port: 9000 });
        const { DOM, Runtime } = client;
        
        const doc = await DOM.getDocument({ depth: -1 });
        const node = await DOM.querySelector({ nodeId: doc.root.nodeId, selector: 'input[type="file"]' });
        
        if (node && node.nodeId) {
            console.log('Uploading file...');
            await DOM.setFileInputFiles({ files: ['C:/Projects/antigravity-core/.agents/sidecars/antigravity_phone_chat/scratch/test_image.png'], nodeId: node.nodeId });
            
            console.log('Waiting 2 seconds...');
            await new Promise(r => setTimeout(r, 2000));
            
            console.log('Clearing file and dispatching change...');
            const resolved = await DOM.resolveNode({ nodeId: node.nodeId });
            await Runtime.callFunctionOn({
                objectId: resolved.object.objectId,
                functionDeclaration: 'function() { this.value = ""; this.dispatchEvent(new Event("change", { bubbles: true })); }'
            });
            
            console.log('Waiting 2 seconds...');
            await new Promise(r => setTimeout(r, 2000));
            
            console.log('Injecting message...');
            const EXPRESSION = `(async () => {
                const editors = [...document.querySelectorAll('[data-testid="conversation-view"] [contenteditable="true"], #root [contenteditable="true"], .overflow-y-auto [contenteditable="true"]')].filter(el => el.offsetParent !== null);
                const editor = editors.at(-1);
                editor.focus();
                document.execCommand?.("selectAll", false, null);
                document.execCommand?.("delete", false, null);
                editor.textContent = "Test from script to see if image is sent";
                editor.dispatchEvent(new InputEvent("beforeinput", { bubbles:true, inputType:"insertText", data: "Test from script to see if image is sent" }));
                editor.dispatchEvent(new InputEvent("input", { bubbles:true, inputType:"insertText", data: "Test from script to see if image is sent" }));
                await new Promise(r => setTimeout(r, 150));
                let submit = document.querySelector('button[aria-label="Send Message"]') || document.querySelector('button[aria-label="Send"]') || document.querySelector("svg.lucide-arrow-up")?.closest("button");
                if (submit && !submit.disabled) { submit.click(); return "clicked"; }
                return "failed";
            })()`;
            
            let res = await Runtime.evaluate({ expression: EXPRESSION, awaitPromise: true });
            console.log('Inject result:', res.result.value);
        }
        await client.close();
    } catch (e) {
        console.error(e);
    }
})();
