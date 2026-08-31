import { chromium } from "playwright";
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 1000 } });
await p.goto("https://agentic-core-468826425509.us-central1.run.app/", { waitUntil: "networkidle", timeout: 90000 });
await p.waitForTimeout(3000);
const info = await p.evaluate(() => {
  const g = id => document.getElementById(id);
  const box = el => { if(!el) return null; const r = el.getBoundingClientRect();
    const s = getComputedStyle(el); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height),
    opacity:s.opacity, display:s.display, visibility:s.visibility}; };
  return {
    controls: box(document.querySelector(".controls")),
    run: box(g("run")), sabotage: box(g("sabotage")), reset: box(g("reset")),
    runText: g("run") ? g("run").innerText : null,
    // what a first-time visitor can actually read, in order
    firstScreen: document.body.innerText.split("\n").filter(Boolean).slice(0, 14),
  };
});
console.log(JSON.stringify(info, null, 1));
await b.close();
