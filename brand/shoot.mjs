import { createRequire } from "node:module";
import path from "node:path";
const require = createRequire("/Users/maxwell/hackathon/film/");
const puppeteer = require("puppeteer-core");
const dir = import.meta.dirname;
const browser = await puppeteer.launch({
  executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: "shell" });
const page = await browser.newPage();
for (const [w,h,name] of [[1200,675,"geminga-cover.png"],[1200,1200,"geminga-square.png"]]) {
  await page.setViewport({ width:w, height:h, deviceScaleFactor:2 });
  await page.goto("file://"+path.join(dir,"cover.html"), { waitUntil:"networkidle0" });
  await page.evaluate((hh)=>{ document.body.style.height=hh+"px"; }, h);
  await new Promise(r=>setTimeout(r,400));
  await page.screenshot({ path: path.join(dir,name), type:"png" });
  console.log("wrote", name, w+"x"+h, "@2x");
}
await browser.close();
