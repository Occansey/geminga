import { createRequire } from "node:module";
import path from "node:path";
const require = createRequire("/Users/maxwell/hackathon/film/");
const puppeteer = require("puppeteer-core");
const dir = import.meta.dirname;
const src  = "file://" + path.join(dir, "..", "docs", "architecture-3d.html");
const browser = await puppeteer.launch({
  executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: "shell" });
const page = await browser.newPage();

// The page's own default camera (rx=50, rz=-38) is the composed view. Do not override it:
// flattening the pitch rotates the room labels out of the frame entirely.
await page.setViewport({ width: 1400, height: 1100, deviceScaleFactor: 2 });
await page.goto(src, { waitUntil: "networkidle0" });
await new Promise(r => setTimeout(r, 2500));       // let the entry animation settle

const h = await page.evaluate(() => document.documentElement.scrollHeight);
await page.screenshot({ path: path.join(dir, "geminga-architecture.png"), fullPage: true });
console.log("wrote geminga-architecture.png  1400x" + h + " @2x");

// A 3:2 crop of the header + scene, for the Devpost gallery (which prefers 3:2).
await page.screenshot({
  path: path.join(dir, "geminga-architecture-3x2.png"),
  clip: { x: 0, y: 0, width: 1400, height: Math.round(1400 * 2 / 3) },
});
console.log("wrote geminga-architecture-3x2.png 1400x933 @2x");
await browser.close();
