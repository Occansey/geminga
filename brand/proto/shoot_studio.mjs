import { createRequire } from "node:module"; import path from "node:path";
const require = createRequire("/Users/maxwell/hackathon/film/");
const puppeteer = require("puppeteer-core");
const b = await puppeteer.launch({ executablePath:"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless:"shell" });
const p = await b.newPage(); const dir = import.meta.dirname;
await p.setViewport({ width:1440, height:900, deviceScaleFactor:2 });
await p.goto("file://"+path.join(dir,"nightshift-studio.html"), { waitUntil:"networkidle0" });
await new Promise(r=>setTimeout(r,2200));               // let the intro count-up + staggers settle
await p.evaluate(()=>{ if(window.gsap){gsap.globalTimeline.progress(1);} document.getElementById('num').textContent='174.30'; });
await new Promise(r=>setTimeout(r,200));
await p.screenshot({ path: path.join(dir,"nightshift-studio.png"), type:"png" });
console.log("wrote nightshift-studio.png"); await b.close();
