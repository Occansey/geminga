"""Regenerate the teleprompter's SHOTS array from RECORDING-SCRIPT.md, and report pacing.

The script is the single source of truth; this exists so the mobile shot list cannot drift
from it. Also prints words-per-minute per shot -- anything much over ~155 is unreadable aloud.
"""
import json, re, sys, pathlib, html

SRC = pathlib.Path("docs/RECORDING-SCRIPT.md")
TP  = pathlib.Path("/private/tmp/claude-502/-Users-maxwell-hackathon/"
                   "7dd02168-65cc-468f-af4e-79091d782d68/scratchpad/teleprompter.html")

def md(t):
    t = html.escape(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<em>\1</em>", t)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", t)

body = SRC.read_text()
blocks = re.split(r"\n## (?=\d+ ·)", body)[1:]
shots = []
for b in blocks:
    head, rest = b.split("\n", 1)
    m = re.match(r"(\d+) · (\d+):(\d+)–(\d+):(\d+) — (.+)", head.strip())
    if not m: continue
    n, am, asec, bm, bsec, what = m.groups()
    a, bb = int(am)*60+int(asec), int(bm)*60+int(bsec)
    rest = rest.split("\n---")[0]
    do = ""
    act = ""
    amm = re.search(r"\*\*ACTION:\*\*(.+)", rest)
    if amm: act = md(" ".join(amm.group(1).split()))
    dm = re.search(r"\*\*On screen:\*\*(.+?)(?=\n\n)", rest, re.S)
    if dm: do = md(" ".join(dm.group(1).split()))
    say = [md(" ".join(p.split())) for p in
           re.findall(r"(?:^|\n)((?:> .*\n?)+)", rest)
           for p in [re.sub(r"(?m)^> ?", "", p).strip()] if p]
    shots.append({"n": int(n), "a": a, "b": bb, "what": what.strip(), "do": do, "act": act, "say": say})

# pacing
print(f"  {'shot':<5}{'window':<12}{'words':<7}wpm")
bad = 0
for s in shots:
    w = len(re.sub(r"<[^>]+>", " ", " ".join(s["say"])).split())
    dur = s["b"] - s["a"]
    wpm = round(w / dur * 60) if dur else 0
    flag = "  <-- too fast" if wpm > 155 else ""
    if wpm > 155: bad += 1
    print(f"  {s['n']:<5}{s['a']//60}:{s['a']%60:02d}-{s['b']//60}:{s['b']%60:02d}   {w:<7}{wpm}{flag}")
end = shots[-1]["b"]
print(f"\n  ends {end//60}:{end%60:02d}  ({240-end}s headroom before the 4:00 cut)  shots over 155 wpm: {bad}")

t = TP.read_text()
i = t.index("const SHOTS = ["); j = t.index("\n  ];", i)
TP.write_text(t[:i] + "const SHOTS = " + json.dumps(shots, indent=2, ensure_ascii=False)
              .replace("\n", "\n  ") + ";" + t[j+5:])
print(f"  teleprompter synced: {len(shots)} shots")

def rebalance(total=234):
    """Give each shot a window proportional to its word count, so every shot lands at the
    same speaking pace. Shot boundaries carry meaning (a click, a tab switch), but their
    *lengths* are free -- and an 18s window holding 78 words is not recordable."""
    body = SRC.read_text()
    heads = re.findall(r"(?m)^## (\d+) · (\d+):(\d+)–(\d+):(\d+) — (.+)$", body)
    words = []
    for n, *_ in heads:
        blk = re.split(rf"(?m)^## {n} · ", body)[1]
        blk = re.split(r"(?m)^## \d+ · ", blk)[0].split("\n---")[0]
        say = re.findall(r"(?:^|\n)((?:> .*\n?)+)", blk)
        w = len(re.sub(r"[*`>_]", " ", " ".join(say)).split())
        words.append(w)
    tot = sum(words)
    durs = [max(8, round(w / tot * total)) for w in words]
    drift = total - sum(durs)
    durs[words.index(max(words))] += drift          # absorb rounding in the longest shot
    t = 0
    spans = {}
    for (n, *_), d in zip(heads, durs):
        spans[n] = (t, t + d); t += d

    def restamp(m):
        a, b = spans[m.group(1)]
        return f"## {m.group(1)} · {a//60}:{a%60:02d}–{b//60}:{b%60:02d} — {m.group(6)}"
    body = re.sub(r"(?m)^## (\d+) · (\d+):(\d+)–(\d+):(\d+) — (.+)$", restamp, body)
    SRC.write_text(body)
    print(f"  rebalanced: uniform {round(tot/total*60)} wpm, ends {t//60}:{t%60:02d}")

if "--rebalance" in sys.argv: rebalance()
