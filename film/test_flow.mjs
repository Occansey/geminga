import { chromium } from "playwright"; import path from "node:path";
const dir = path.join(import.meta.dirname, "..", "brand");
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 2 });
const errs = []; p.on("pageerror", e => errs.push(String(e).slice(0,140)));
await p.goto("http://127.0.0.1:8077/", { waitUntil: "networkidle" });
await p.waitForTimeout(1200);
await p.screenshot({ path: path.join(dir, "ui-0-gate.png") });
console.log("  1. gate visible:", await p.isVisible("#gate"));
console.log("     connect button visible:", await p.isVisible("#connect"));
await p.click("#connect");
await p.waitForTimeout(4600);
await p.screenshot({ path: path.join(dir, "ui-0b-connecting.png") });
await p.waitForTimeout(1200);
const gateGone = await p.evaluate(() => document.getElementById("gate").classList.contains("gone"));
console.log("  2. gate dismissed after connect:", gateGone);
// THE bug: are the controls actually visible to a human now?
const vis = await p.evaluate(() => ["run","sabotage","reset"].map(id => ({
  id, opacity: getComputedStyle(document.getElementById(id)).opacity })));
console.log("  3. control opacity:", JSON.stringify(vis));
await p.screenshot({ path: path.join(dir, "ui-1-connected.png") });
console.log("  4. page errors:", errs.length ? errs : "none");
await b.close();
