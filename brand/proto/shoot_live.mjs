import { createRequire } from "node:module";
const require = createRequire("/Users/maxwell/hackathon/film/");
const puppeteer = require("puppeteer-core");
const b = await puppeteer.launch({ executablePath:"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless:"shell" });
const p = await b.newPage();
await p.setViewport({ width:1440, height:900, deviceScaleFactor:2 });
await p.goto("https://agentic-core-468826425509.us-central1.run.app/", { waitUntil:"networkidle0", timeout:60000 });
await new Promise(r=>setTimeout(r,1500));
// drive a live run to capture the reclaimed arc
await p.click("#run");
await new Promise(r=>setTimeout(r,13000));
await p.evaluate(()=>{ if(window.gsap){gsap.globalTimeline.getChildren(true,true,false).forEach(t=>t.progress(1));} });
await new Promise(r=>setTimeout(r,600));
await p.screenshot({ path:"nightshift-live.png", type:"png" });
console.log("wrote nightshift-live.png"); await b.close();
