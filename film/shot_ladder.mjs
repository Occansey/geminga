import { chromium } from "playwright"; import path from "node:path";
const dir = path.join(import.meta.dirname, "..", "brand");
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 1100 }, deviceScaleFactor: 2 });
await p.goto("http://127.0.0.1:8077/", { waitUntil: "networkidle" });
await p.click("#connect"); await p.waitForTimeout(5200);
await p.evaluate(() => { document.querySelector(".split").scrollIntoView({block:"start"}); });
await p.waitForTimeout(900);
await p.screenshot({ path: path.join(dir, "ui-ladder.png") });
// check nothing overflows its column
const over = await p.evaluate(() => [...document.querySelectorAll(".rung .m")].map(el => {
  const r = el.getBoundingClientRect(); return { w: Math.round(r.width), right: Math.round(r.right), vw: innerWidth };
}));
console.log("  rung description boxes:", JSON.stringify(over));
await b.close();
