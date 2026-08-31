/* Capture the DEPLOYED console as video. Every frame is the real Cloud Run service, driven
   deterministically so the run is reshootable after any change. */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const TARGET = "https://agentic-core-468826425509.us-central1.run.app/";
import path from "node:path";
const OUT = path.join(import.meta.dirname, "out");
mkdirSync(OUT, { recursive: true });

const wait = ms => new Promise(r => setTimeout(r, ms));
const marks = [];
const t0 = Date.now();
const mark = name => { const t = (Date.now() - t0) / 1000; marks.push({ name, t }); console.log(`  ${t.toFixed(1)}s  ${name}`); };

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({
  viewport: { width: 1920, height: 1080 },
  deviceScaleFactor: 1,
  recordVideo: { dir: OUT, size: { width: 1920, height: 1080 } },
});
const page = await ctx.newPage();

await page.goto(TARGET, { waitUntil: "networkidle" });
// the gate is the first thing a visitor meets now — hold on it, then connect on camera
await page.waitForSelector("#connect");
mark("the gate: what this is, and why nobody deletes it");
await wait(20000);                        // shot 1 — read the pitch
await page.click("#connect");
mark("connecting to Google Cloud");
await wait(6000);                         // the auth + inventory read plays out
await page.waitForFunction(() => document.querySelectorAll("#estate .item").length > 0);
mark("the estate revealed — real waste");
await wait(16000);                       // shot 2

await page.evaluate(() => document.querySelector(".split").scrollIntoView({ behavior: "smooth", block: "start" }));
mark("estate + HUMAN locks + fixture disclosure");
await wait(23000);                       // shot 2

await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
mark("authority ladder, shadow");
await wait(20000);                       // shot 3

await page.click("#run");
mark("RUN — rehearsals in shadow, then promotion and first real commit");
await wait(70000);                       // shots 4+5 (the run streams)
await page.waitForFunction(() => document.getElementById("status").textContent === "done", { timeout: 120000 }).catch(() => {});

await page.click("#reset");
await wait(2500);
await page.click("#sabotage");
mark("FAULT — the tool lies from run 6");
await wait(65000);                       // shots 6+7
await page.waitForFunction(() => document.getElementById("status").textContent === "done", { timeout: 120000 }).catch(() => {});

await page.evaluate(() => {
  const row = [...document.querySelectorAll("#estate .item")].find(e => /delete_unattached_disk/i.test(e.textContent));
  if (row) row.scrollIntoView({ behavior: "smooth", block: "center" });
});
mark("the human lock, held at every rung");
await wait(18000);                       // shot 8

await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
mark("close on the live Cloud Run console");
await wait(20000);                       // shot 9

await ctx.close();                        // flushes the video
await browser.close();
console.log("\n  marks:", JSON.stringify(marks.map(m => [m.name, +m.t.toFixed(1)])));
console.log(`  video written to ${OUT}`);
