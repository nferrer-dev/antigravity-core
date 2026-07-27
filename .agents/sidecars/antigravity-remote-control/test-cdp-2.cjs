const cdp = require('chrome-remote-interface');
(async function() {
    let client;
    try {
        client = await cdp({ port: 9000, target: '4F80951B295F539668591F8AF0FB99DB' });
        const { Runtime } = client;
        
        const res = await Runtime.evaluate({
            expression: `(() => {
                let modelBtn = document.querySelector('button[aria-label^="Select model"]');
                const executeClick = (targetEl) => {
                    const events = ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'];
                    events.forEach(type => {
                        targetEl.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
                    });
                };
                executeClick(modelBtn);
                return 'Clicked!';
            })()`,
            returnByValue: true,
            awaitPromise: true
        });
        console.log(res);

        // Wait a bit to let the DOM update
        await new Promise(r => setTimeout(r, 1000));

        const res2 = await Runtime.evaluate({
            expression: `(() => {
                const allDivs = Array.from(document.querySelectorAll('[role="dialog"], [role="listbox"], [role="menu"], [data-radix-popper-content-wrapper], div'));
                const candidates = allDivs.filter(d => {
                    if (d.offsetHeight === 0) return false;
                    const style = window.getComputedStyle(d);
                    const isPositioned = style.position === 'absolute' || style.position === 'fixed';
                    const isRadix = d.hasAttribute('data-radix-popper-content-wrapper') || d.getAttribute('role');
                    if (!isPositioned && !isRadix) return false;
                    if (d.offsetWidth > window.innerWidth * 0.6) return false;
                    if (d.offsetHeight >= window.innerHeight * 0.95) return false;
                    return true;
                });
                return candidates.map(c => c.outerHTML.substring(0, 100));
            })()`,
            returnByValue: true,
            awaitPromise: true
        });
        console.log(res2);
    } catch (err) {
        console.error(err);
    } finally {
        if (client) {
            await client.close();
        }
    }
})();
