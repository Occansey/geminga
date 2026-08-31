# Geminga — recording script

**Hard limits:** 4:00 max · public on YouTube or Vimeo · must show the backend running on
Google Cloud · English (or English subtitles).

**Open:** https://agentic-core-468826425509.us-central1.run.app — full screen, browser URL bar
visible. That URL on screen *is* the Google Cloud deployment proof, so don't hide it.

## Before you hit record — two tabs

**Tab 1 — the demo, with you in shot:**

    https://agentic-core-468826425509.us-central1.run.app/?presenter=1

The `?presenter=1` puts your webcam in a circular bubble over the console, so one screen
recording captures both you and the demo. Allow the camera prompt. Drag the bubble somewhere it
covers nothing — bottom-right is clear. `P` hides it.

**Tab 2 — the architecture, for shot 10:**

    https://agentic-core-468826425509.us-central1.run.app/architecture

Open it now and leave it loaded, so at 3:20 you switch to a ready tab instead of watching it
load on camera.

Full screen, URL bar visible. That `run.app` address on screen *is* the Google Cloud deployment
proof, so do not hide the chrome.

---

Timings below are measured from real read-throughs. Every line sits between 47 and 84 words per
minute, so you can speak slowly. **Total speech is 1:43 inside a 3:55 cut** — the rest is silence
while the demo runs, which is intentional. Do not rush to fill it.

---

## 1 · 0:00–0:20 — the gate, before you click anything

**On screen:** the landing page. Let it sit. Cursor still.

> Monday morning, a billing alert. Something has been running since Friday. The engineer on call
> already knows what to delete. That was never the hard part.

**Optional, and strong:** point at the green counter under the headline.

> That counter is real. While I have been talking, this estate has burned another few cents.

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

## 4 · 1:00–1:26 — the estate, and the trap

**On screen:** scroll the list. Stop on **ml-train-01** at the top and stay there. Point at the
two numbers on its detail line: `cpu 0.4% (7d avg)` and, in red, `gpu 94% — busy`.

> These are real machines. The most expensive thing here is a GPU node costing two thousand six
> hundred dollars a month, and it has been sitting at nought point four percent CPU for a
> hundred and seventy-four days.
>
> Every cost tool in the world flags that as idle. Stop it and save the money.
>
> Look at the next number. Ninety-four percent GPU. It is not idle. It is training.

## 5 · 1:26–1:56 — the three levels (say each one)

**On screen:** scroll to SHADOW · PROVISIONAL · LIVE. Hold long enough for each description to be
read. Point at the row of pips underneath.

> So Geminga asks a different question. Not how do we make the agent more confident, but how does
> an agent earn the right to act.
>
> There are three levels, and every kind of operation has to climb them.
>
> **Shadow.** It rehearses. It predicts what would change and touches nothing. Five correct
> predictions in a row to move up.
>
> **Provisional.** Now it really deletes, and every single run is checked against the live
> machines. Ten more clean runs to reach the top.
>
> **Live.** It still really deletes, but now it is checked on a sample, never zero, because a
> level nobody watches cannot fall.
>
> One disagreement at any level and it drops straight back down.

---

## 6 · 1:56–2:20 — click RUN THE LADDER

**On screen:** click it and **stop talking**. Let runs 1–5 play in SHADOW. The pips fill. Nothing
in the estate changes. This silence is the point: the agent is working and touching nothing.

> *(silence — roughly 18 seconds. Let it run. This is the agent working and touching nothing.)*

---

## 7 · 2:20–2:40 — promotion and the first real commit

**On screen:** PROVISIONAL lights up. RECLAIMED climbs off zero. A resource changes.

> Five consecutive runs where a verifier that re-derives real state agreed with the prediction.
> Only then does it commit. That is the first money this agent was ever allowed to touch.

---

## 8 · 2:40–3:02 — click MAKE THE TOOL LIE · RUN 6

**On screen:** click it. From run six the tool reports success while changing nothing.

> Now the interesting part. From run six the tool reports success while changing nothing. This is
> the failure every agent demo skips.

---

## 9 · 3:02–3:20 — the catch and the demotion

**On screen:** the run log line where the reviewer explains itself. The ladder falls back to
SHADOW. A pip turns red.

> Verification does not ask the actuator how it went. It re-derives state from the environment,
> sees the gap, and takes the authority back. One disagreement, one rung, immediately.

---

## 10 · 3:20–3:36 — the architecture, and the gate that caught it

**On screen:** switch to the pre-loaded architecture tab. Drag once so it spins. Then click the
**"Stop the idle-looking GPU node"** button and let the Metrologist light up.

> That is not one function. It is fifteen agents on three floors with a hard wall between them,
> and the one that saved us here is the Metrologist.
>
> Every other gate said yes. It was in the inventory. It was an instance. No data destroyed.
> Stopping is reversible. The shape had been rehearsed five times cleanly.
>
> And rehearsal could never have caught it, because stopping a busy machine works. It stops. The
> verifier confirms it stopped. Nobody was wrong except about what idle means.

## 11 · 3:36–3:50 — close

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

## Worth knowing while you say it

This is not a hypothetical you are dramatising. `tests/test_liveness.py` opens with it: on the
deployed service the agent stopped ml-train-01 three separate times, and every gate said yes. The
Metrologist exists because that happened. If a judge asks, that is the answer.

## One honesty note to keep in

The demo runs a **fixture estate**, not a live project, because the account available to point at
is empty and a console of $0.00 demonstrates nothing. The console says so on screen and the
Devpost story says so. If you want to say it aloud, one line at the end of shot 4 does it:
*"This is a demo fixture at real Google Cloud list prices; the live path is the same code."*
