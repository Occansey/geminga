import { chromium } from "playwright";
import path from "node:path";
const dir = import.meta.dirname;
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
for (const c of ["title","problem","ladder","fault","arch","end"]) {
  await p.goto("file://" + path.join(dir, "card.html") + "?c=" + c, { waitUntil: "networkidle" });
  await p.waitForTimeout(700);
  await p.screenshot({ path: path.join(dir, "..", "out", "cards", c + ".png") });
  console.log("  card:", c);
}
await b.close();
