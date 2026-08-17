import { createRequire } from "node:module";
import path from "node:path";
const require = createRequire("/Users/maxwell/hackathon/film/");
const puppeteer = require("puppeteer-core");
const dir = import.meta.dirname;
const browser = await puppeteer.launch({
  executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: "shell" });
const page = await browser.newPage();
const jobs = [
  // name,              colour,   tile(bg),  size
  ["geminga-mark-oxide.png", "#C2612F", false, 1024],
  ["geminga-mark-light.png", "#E9EDF1", false, 1024],
  ["geminga-mark-dark.png",  "#0C1016", false, 1024],
  ["geminga-logo-tile.png",  "#C2612F", true,  1024],
  ["geminga-icon-512.png",   "#C2612F", true,   512],
  ["geminga-icon-256.png",   "#C2612F", true,   256],
];
for (const [name, colour, tile, size] of jobs) {
  await page.setViewport({ width:size, height:size, deviceScaleFactor: size >= 1024 ? 2 : 1 });
  await page.goto("file://"+path.join(dir,"mark.html"), { waitUntil:"networkidle0" });
  await page.evaluate(({colour,tile,size}) => {
    document.body.className = tile ? "tile" : "";
    document.documentElement.style.width = document.body.style.width = size+"px";
    document.documentElement.style.height = document.body.style.height = size+"px";
    const b = document.getElementById("box");
    b.style.width = b.style.height = size+"px";
    b.style.color = colour;
  }, {colour, tile, size});
  await new Promise(r=>setTimeout(r,250));
  await page.screenshot({ path: path.join(dir,name), type:"png", omitBackground: !tile });
  console.log("wrote", name, size+"px", tile ? "on slate" : "transparent");
}
await browser.close();
