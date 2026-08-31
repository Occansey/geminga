import { chromium } from "playwright"; import path from "node:path";
const dir=import.meta.dirname;
const b=await chromium.launch(); const p=await b.newPage({viewport:{width:2400,height:1600}});
await p.goto("file://"+path.join(dir,"architecture-stairs.html"),{waitUntil:"networkidle"});
await p.waitForTimeout(800);
await p.screenshot({path:path.join(dir,"geminga-architecture-stairs.png")});
console.log("wrote geminga-architecture-stairs.png"); await b.close();
