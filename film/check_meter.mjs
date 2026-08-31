import { chromium } from "playwright";
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 1000 } });
await p.goto("https://agentic-core-468826425509.us-central1.run.app/", { waitUntil: "networkidle", timeout: 90000 });
await p.waitForTimeout(2500);
const before = await p.evaluate(() => {
  const m = document.querySelector(".meter"); const g = document.getElementById("gate");
  const r = m ? m.getBoundingClientRect() : null;
  return { gateVisible: g && !g.classList.contains("gone"),
           meterInDom: !!m,
           meterOnScreen: r ? (r.top >= 0 && r.bottom <= innerHeight && r.width > 0) : false,
           covered: g && !g.classList.contains("gone") ? "yes — gate overlay is on top" : "no" };
});
console.log("  BEFORE connect:", JSON.stringify(before));
await p.click("#connect"); await p.waitForTimeout(5400);
const after = await p.evaluate(() => {
  const m = document.querySelector(".meter");
  const amt = document.getElementById("accrued");
  const r = m.getBoundingClientRect();
  return { visible: r.top >= 0 && r.width > 0,
           colour: getComputedStyle(amt).color,
           reads: amt.textContent };
});
console.log("  AFTER connect :", JSON.stringify(after));
await b.close();
