const { connectToCDP } = require('./test-cdp.js'); 
(async () => { 
  const connection = await connectToCDP(); 
  await connection.send('Runtime.evaluate', { 
      expression: `
          var ta = document.querySelector('textarea');
          var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
          nativeInputValueSetter.call(ta, 'Pending Msg');
          var ev2 = new Event('input', { bubbles: true});
          ta.dispatchEvent(ev2);
          document.querySelector('button[aria-label="Send Message"]').click();
      ` 
  }); 
  await new Promise(r => setTimeout(r, 100)); 
  const res = await fetch('http://localhost:3000/snapshot'); 
  const data = await res.json(); 
  require('fs').writeFileSync('simulated_pending.html', data.html); 
  process.exit(0); 
})();
