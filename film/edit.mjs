/* Cut the raw capture into an actual film: title cards, and camera moves into the console so
   each beat reads differently. Without this it is one static page for four minutes. */
import { execFileSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import path from "node:path";
const dir = import.meta.dirname, out = path.join(dir, "out"), seg = path.join(out, "seg");
mkdirSync(seg, { recursive: true });
const ff = (a) => execFileSync("ffmpeg", ["-v", "error", "-y", ...a]);
const RAW = path.join(out, "raw.webm");

// crops into the 1920x1080 console: [x, y, w, h]
const HERO   = [80, 60, 1760, 620];     // the money
const ESTATE = [80, 560, 1180, 520];    // the resource list
const LADDER = [1180, 540, 740, 460];   // the authority words
const FULL   = [0, 0, 1920, 1080];

// shot: either a card (png) or a slice of the capture with a crop
const SHOTS = [
  { card: "title",   dur: 7 },
  { at: 6,   dur: 17, crop: FULL,   label: "the gate: what this is" },      // it explains itself now
  { card: "problem", dur: 15 },
  { at: 25,  dur: 8,  crop: FULL,   label: "connecting to Google Cloud" },
  { at: 33,  dur: 16, crop: ESTATE, label: "the estate: VMs, disks, dates" },
  { at: 50,  dur: 14, crop: ESTATE, label: "the human locks" },
  { card: "ladder",  dur: 11 },
  { at: 72,  dur: 15, crop: LADDER, label: "shadow, explained" },
  { at: 100, dur: 20, crop: FULL,   label: "the run, wide" },
  { at: 130, dur: 18, crop: HERO,   label: "first real commit" },
  { at: 130, dur: 12, crop: LADDER, label: "promotion" },
  { card: "fault",   dur: 11 },
  { at: 180, dur: 18, crop: FULL,   label: "the lie, wide" },
  { at: 205, dur: 18, crop: LADDER, label: "demotion" },
  { at: 229, dur: 13, crop: ESTATE, label: "the human lock holds" },
  { card: "arch",    dur: 11 },
  { card: "end",     dur: 11 },
];

const files = [];
SHOTS.forEach((s, i) => {
  const f = path.join(seg, `s${String(i).padStart(2, "0")}.mp4`);
  if (s.card) {
    ff(["-loop", "1", "-t", String(s.dur), "-i", path.join(out, "cards", s.card + ".png"),
        "-vf", "scale=1920:1080,format=yuv420p", "-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", "18", f]);
    console.log(`  card  ${s.card.padEnd(8)} ${s.dur}s`);
  } else {
    const [x, y, w, h] = s.crop;
    // crop then scale back to 1080p — a real push-in, not a static frame
    ff(["-ss", String(s.at), "-t", String(s.dur), "-i", RAW,
        "-vf", `crop=${w}:${h}:${x}:${y},scale=1920:1080:force_original_aspect_ratio=decrease,`
            + `pad=1920:1080:(ow-iw)/2:(oh-ih)/2:0xe9e6dd,format=yuv420p`,
        "-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-an", f]);
    console.log(`  shot  ${String(s.label).padEnd(20)} ${s.at}s +${s.dur}s`);
  }
  files.push(f);
});

const list = path.join(seg, "list.txt");
execFileSync("bash", ["-c", `printf "file '%s'\\n" ${files.map(f => `'${f}'`).join(" ")} > '${list}'`]);
ff(["-f", "concat", "-safe", "0", "-i", list, "-c", "copy", path.join(out, "edit-silent.mp4")]);
const total = SHOTS.reduce((a, s) => a + s.dur, 0);
console.log(`\n  ${SHOTS.length} shots, ${total}s (${Math.floor(total/60)}:${String(total%60).padStart(2,"0")})`);
