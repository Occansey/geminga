# Geminga — recording script

**Hard limits:** 4:00 max · public on YouTube or Vimeo · must show the backend running on
Google Cloud · English (or English subtitles).

**Open:** https://agentic-core-468826425509.us-central1.run.app — full screen, browser URL bar
visible. That URL on screen *is* the Google Cloud deployment proof, so don't hide it.

Timings below are measured from real read-throughs. Every line sits between 47 and 84 words per
minute, so you can speak slowly. **Total speech is 1:43 inside a 3:55 cut** — the rest is silence
while the demo runs, which is intentional. Do not rush to fill it.

---

## 1 · 0:00–0:20 — the gate, before you click anything

**On screen:** the landing page. Let it sit. Cursor still.

> Monday morning, a billing alert. Something has been running since Friday. The engineer on call
> already knows what to delete. That was never the hard part.

---

## 2 · 0:20–0:40 — still on the gate

**On screen:** slowly scroll the two paragraphs so the viewer can read "nobody dares delete".

> The hard part is blast radius. Deleting the wrong resource at 9am costs more than the bill does.
> So the ticket gets parked, the resource stays up, and the same alert fires next month.

---

## 3 · 0:40–1:00 — click CONNECT TO GOOGLE CLOUD

**On screen:** click it. The auth and inventory lines print themselves. Say nothing over the last
two lines — let "Connected. 7 resources found" land.

> Every agent aimed at this problem lands on the same answer: never let the agent act. It drafts,
> a human approves. That does not fix anything.

---

## 4 · 1:00–1:30 — the estate

**On screen:** scroll the resource list slowly. Hover so the details are readable: machine type,
zone, created date, days running, CPU average. Pause on **pd-ml-scratch — "orphaned by a deleted
VM"** and on a red **HUMAN** badge.

> These are real machines. A GPU node at 0.4% CPU for a hundred and seventy-four days. A two
> terabyte disk orphaned when someone deleted its VM. Every one of them is billing you monthly.

---

## 5 · 1:30–1:50 — the authority column

**On screen:** scroll right/down to SHADOW · PROVISIONAL · LIVE and let the three descriptions
be readable.

> So Geminga asks a different question. Not how do we make the agent more confident, but how does
> an agent earn the right to act. Every operation starts in rehearsal. It predicts a change and
> commits nothing.

---

## 6 · 1:50–2:30 — click RUN THE LADDER

**On screen:** click it and **stop talking**. Let runs 1–5 play in SHADOW. The pips fill. Nothing
in the estate changes. This silence is the point: the agent is working and touching nothing.

> *(silence — roughly 20 seconds)*

---

## 7 · 2:30–2:50 — promotion and the first real commit

**On screen:** PROVISIONAL lights up. RECLAIMED climbs off zero. A resource changes.

> Five consecutive runs where a verifier that re-derives real state agreed with the prediction.
> Only then does it commit. That is the first money this agent was ever allowed to touch.

---

## 8 · 2:50–3:20 — click MAKE THE TOOL LIE · RUN 6

**On screen:** click it. From run six the tool reports success while changing nothing.

> Now the interesting part. From run six the tool reports success while changing nothing. This is
> the failure every agent demo skips.

---

## 9 · 3:20–3:40 — the catch and the demotion

**On screen:** the run log line where the reviewer explains itself. The ladder falls back to
SHADOW. A pip turns red.

> Verification does not ask the actuator how it went. It re-derives state from the environment,
> sees the gap, and takes the authority back. One disagreement, one rung, immediately.

---

## 10 · 3:40–3:55 — close

**On screen:** scroll to a **HUMAN** badge, then back to the top so the Cloud Run URL is the last
thing visible.

> Irreversible operations stay behind a human at every rung. An agent earns the right to act, one
> operation at a time. And loses it the moment it stops being correct.

---

## Checklist before uploading

- Under 4:00. Trim the head where you were setting up.
- The `run.app` URL readable at least once — that is the deployment proof.
- Title: `Geminga — an agent that earns the right to act`
- Description: in `docs/DEVPOST.md` under "Upload checklist"
- Visibility **Public or Unlisted**, never Private. "No" to made-for-kids.
- If your accent is strong on the mic, turn on auto-captions and correct
  "Geminga", "Vertex", "ADK", "provisional".

## One honesty note to keep in

The demo runs a **fixture estate**, not a live project, because the account available to point at
is empty and a console of $0.00 demonstrates nothing. The console says so on screen and the
Devpost story says so. If you want to say it aloud, one line at the end of shot 4 does it:
*"This is a demo fixture at real Google Cloud list prices; the live path is the same code."*
