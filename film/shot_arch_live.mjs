import { chromium } from "playwright"; import path from "node:path";
const dir = path.join(import.meta.dirname, "..", "brand");
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 1100 }, deviceScaleFactor: 2 });
await p.goto("https://agentic-core-468826425509.us-central1.run.app/architecture", { waitUntil: "networkidle", timeout: 90000 });
await p.waitForTimeout(2000);
const stage = await p.$(".stage");
await (stage || p).screenshot({ path: path.join(dir, "arch-live.png") });
// are all fifteen name tags actually on screen and unclipped?
// measure against the STAGE, which is what we screenshot — measuring against the window
// reported everything visible while the top floor was clipped out of the captured frame
const tags = await p.evaluate(() => {
  const s = document.querySelector(".stage").getBoundingClientRect();
  return [...document.querySelectorAll(".bot .tag")].map(t => {
    const r = t.getBoundingClientRect();
    return { text: (t.innerText||"").split("\n")[0].trim(),
             onscreen: r.top > s.top+2 && r.bottom < s.bottom-2 && r.left > s.left+2 && r.right < s.right-2 };
  });
});
console.log("  tags found:", tags.length, "| fully on screen:", tags.filter(t=>t.onscreen).length);
console.log("  offscreen:", tags.filter(t=>!t.onscreen).map(t=>t.text).join(", ") || "none");
await b.close();
