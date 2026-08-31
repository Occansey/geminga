import { chromium } from "playwright";
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 1000 } });
const errs = [];
p.on("pageerror", e => errs.push(String(e).slice(0, 160)));
p.on("console", m => { if (m.type() === "error") errs.push("console: " + m.text().slice(0, 160)); });
await p.goto("https://agentic-core-468826425509.us-central1.run.app/", { waitUntil: "networkidle", timeout: 90000 });
for (const t of [2000, 4000, 8000]) {
  await p.waitForTimeout(t === 2000 ? 2000 : 2000);
  const s = await p.evaluate(() => ({
    runOpacity: getComputedStyle(document.getElementById("run")).opacity,
    inlineStyle: document.getElementById("run").getAttribute("style"),
    gsapLoaded: typeof window.gsap,
    tweens: window.gsap ? gsap.globalTimeline.getChildren(true,true,false).length : -1,
    fontsReady: document.fonts ? document.fonts.status : "n/a",
  }));
  console.log(`  @${t}ms`, JSON.stringify(s));
}
console.log("  page errors:", errs.length ? errs : "none");
await b.close();
