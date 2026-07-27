import CDP from 'chrome-remote-interface';
async function test() {
    let client;
    try {
        client = await CDP({ port: 63798 });
        const { Runtime, DOM } = client;
        await DOM.enable();
        
        const result = await Runtime.evaluate({
            expression: `(function() {
                const editors = [...document.querySelectorAll('[data-testid="conversation-view"] [contenteditable="true"], #root [contenteditable="true"], .overflow-y-auto [contenteditable="true"]')];
                const editor = editors.at(-1);
                if (!editor) return "no editor";
                
                let submit = document.querySelector('[data-tooltip-id="input-send-button-tooltip"]') 
                  || document.querySelector('[data-tooltip-id="send-button-tooltip"]')
                  || document.querySelector('button[aria-label="Send Message"]')
                  || document.querySelector('button[aria-label="Send"]')
                  || document.querySelector("svg.lucide-arrow-right")?.closest("button")
                  || document.querySelector("svg.lucide-arrow-up")?.closest("button")
                  || document.querySelector("svg.lucide-send")?.closest("button");
                  
                return {
                    editorFound: !!editor,
                    editorFocused: document.activeElement === editor,
                    submitFound: !!submit,
                    submitDisabled: submit ? submit.disabled : null,
                    submitHTML: submit ? submit.outerHTML : null
                };
            })()`,
            returnByValue: true
        });
        console.log(result.result.value);
    } catch (err) {
        console.error(err);
    } finally {
        if (client) {
            await client.close();
        }
    }
}
test();
