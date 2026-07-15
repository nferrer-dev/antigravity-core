import CDP from 'chrome-remote-interface';
async function test() {
    let client;
    try {
        client = await CDP({ port: 63798 });
        const { Runtime, Input, DOM } = client;
        
        await Runtime.evaluate({
            expression: `(function() {
                const editors = [...document.querySelectorAll('[data-testid="conversation-view"] [contenteditable="true"], #root [contenteditable="true"], .overflow-y-auto [contenteditable="true"]')];
                editors.at(-1).focus();
            })()`
        });

        // Type TEST!
        await Input.insertText({ text: "TEST!" });
        
        // Wait
        await new Promise(r => setTimeout(r, 100));

        // Press Enter
        await Input.dispatchKeyEvent({ type: "keyDown", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13, text: "\r" });
        await Input.dispatchKeyEvent({ type: "keyUp", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 });

        console.log("Sent TEST! and Enter");
    } catch (err) {
        console.error(err);
    } finally {
        if (client) {
            await client.close();
        }
    }
}
test();
