const { JSDOM } = require("jsdom");
const dom = new JSDOM('<div data-id="123">hi</div>');
const doc = dom.window.document;
const cssEscaped = dom.window.CSS.escape("123");
console.log("CSS.escape('123') =", cssEscaped);
const sel = `[data-id="${cssEscaped}"]`;
console.log("Selector =", sel);
const el = doc.querySelector(sel);
console.log("FOUND without quotes:", el ? el.textContent : "NO");

const selQuotes = `[data-id="${cssEscaped}"]`; // actually the standard is to not use quotes when using CSS.escape
// Let's test what happens inside quotes:
const selWithQuotes = `[data-id="${cssEscaped.replace(/\\/g, '\\\\')}"]`;
console.log("selWithQuotes =", `[data-id="${cssEscaped}"]`);
const el2 = doc.querySelector(`[data-id="${cssEscaped}"]`);
console.log("FOUND with quotes:", el2 ? el2.textContent : "NO");
