import { chromium } from "playwright"; import path from "node:path";
const dir = path.join(import.meta.dirname, "..", "brand");
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 2 });
await p.goto("https://agentic-core-468826425509.us-central1.run.app/intro", { waitUntil: "networkidle", timeout: 90000 });
await p.waitForTimeout(2200);
await p.screenshot({ path: path.join(dir, "intro.png") });
console.log("wrote intro.png");
await b.close();
