# Geminga — recording script

**Hard limits:** 4:00 max · public on YouTube or Vimeo · must show the backend running on
Google Cloud · English (or English subtitles).

**Open:** https://agentic-core-468826425509.us-central1.run.app — full screen, browser URL bar
visible. That URL on screen *is* the Google Cloud deployment proof, so don't hide it.

## Before you hit record — two tabs

**Tab 1 — the title card, your opening shot:**

    https://agentic-core-468826425509.us-central1.run.app/intro

Your name, the mark, what Geminga means and why you built it. Open on this for five seconds
before anything else.

**Tab 2 — the demo, with you in shot:**

    https://agentic-core-468826425509.us-central1.run.app/?presenter=1

The `?presenter=1` puts your webcam in a circular bubble over the console, so one screen
recording captures both you and the demo. Allow the camera prompt. Drag the bubble somewhere it
covers nothing — bottom-right is clear. `P` hides it.

**Reload this tab immediately before you hit record.** The green counter starts from zero on page
load and climbs at about five dollars an hour, so a tab left open for ten minutes already reads
eighty cents. Reloading keeps the number small and keeps what you say about it honest.

**Tab 3 — the architecture, for shot 3:**

    https://agentic-core-468826425509.us-central1.run.app/architecture

Open it now and leave it loaded, so at 0:38 you switch to a ready tab instead of watching it
load on camera.

Full screen, URL bar visible. That `run.app` address on screen *is* the Google Cloud deployment
proof, so do not hide the chrome.

---

Timings below are measured from real read-throughs. Nothing exceeds a calm speaking pace, so you can slow down. **Total speech is about 2:34 inside a 3:52 cut** — the rest is silence
while the demo runs, which is intentional. Do not rush to fill it.

---

## 0 · 0:00–0:36 — hello, and the title card

**On screen:** open on `/intro`. Your name and the mark are already on screen, so say it warmly
rather than formally. Do not read the etymology off the page — let them read it while you talk.

> Hello — my name is Maxwell Occansey, and this is Geminga, my entry for Google's All Things
> Agentic hackathon.
>
> It's named after a pulsar the astronomers in Milan called *gh'è minga* — their dialect for
> "it's not there".
>
> I built it because cloud agents are being handed delete permissions on production, and
> everybody's answer to that risk is the same: never let the agent act. I wanted the harder one.
>
> I had a lot of fun building this. Let me show you.

*Pronunciation: "gay-MING-ah"; the pun is roughly "gh-eh MEEN-ga".*

---

## 1 · 0:36–0:50 — the gate

**On screen:** switch to **tab 2**, the console. You are on the gate: a headline reading **“Your
cloud is burning money on machines nobody dares delete.”**, the paragraph beneath it, and a
**Connect to Google Cloud** button. Cursor still — nothing to point at yet.

> Monday morning, a billing alert. Something has been running since Friday. The engineer on call
> already knows what to delete. That was never the hard part.

## 2 · 0:50–1:07 — why nobody acts

**On screen:** the phrase you are talking about — **“machines nobody dares delete”** — is the
headline itself, already on screen from shot 1. Nothing to scroll to. Just gesture at it, then
scroll slowly down the paragraph beneath it, which lists what the waste actually is: idle VMs,
disks left behind, buckets with no lifecycle rule, forgotten IPs.

> The hard part is blast radius. Delete the wrong thing at nine in the morning and it costs more
> than the bill did. So the ticket gets parked, and the same alert fires next month.

---

## 3 · 1:07–1:49 — the architecture, up front

**On screen:** switch to **tab 3**, the architecture, already loaded. Drag once so it spins — that proves it
is live, not a picture. Let the three floors and the red wall be readable.

> So here is what we built, before I show you it running.
>
> Fifteen agents on three floors, with a hard wall through the middle. Everything on the top
> floor is untrusted, because everything it reads — machine names, labels, descriptions — was
> written by somebody, and in most organisations that somebody is anybody. Nothing up there is
> allowed to decide anything.
>
> The middle floor is seven inspectors that use no model at all. Any one of them can refuse.
> Only the ground floor can change anything, and only after it has re-read the real machines.

---

## 4 · 1:49–2:01 — connect

**On screen:** back to **tab 2**, the console. Click **CONNECT TO GOOGLE CLOUD**. The auth and
inventory lines print, the gate lifts, and the console appears. **Now** the green counter exists,
under the big waste figure — point at it once it is on screen.

> Now watch it meet a real estate.
>
> And that counter is real. That is this estate billing, live, while we talk.

---

## 5 · 2:01–2:29 — the estate, and the trap

**On screen:** stop on **ml-train-01**. Point at `cpu 0.4% (7d avg)` and, in red, `gpu 94% — busy`.

> The most expensive thing here is a GPU node costing two thousand six hundred dollars a month,
> and it has been at nought point four percent CPU for a hundred and seventy-four days.
>
> Every cost tool in the world flags that as idle. Stop it, save the money.
>
> Look at the next number. Ninety-four percent GPU. It is not idle. It is training.

---

## 6 · 2:29–2:47 — the three levels

**On screen:** scroll to SHADOW · PROVISIONAL · LIVE. Hold on each description. Point at the pips.

> Every kind of operation has to climb three levels.
>
> **Shadow.** It rehearses. Predicts what would change, touches nothing. Five correct predictions
> in a row to move up.
>
> **Provisional.** Now it really deletes, and every run is checked against the live machines. Ten
> more clean runs to reach the top.
>
> **Live.** Still really deletes, but checked on a sample, never zero, because a level nobody
> watches cannot fall.
>
> One disagreement at any level and it drops straight back down.

---

## 7 · 2:47–3:03 — click RUN THE LADDER, then stop talking

**On screen:** runs one to five play in shadow. Pips fill. The estate does not change.

> *(silence — about 16 seconds. The agent is working and touching nothing. That is the point.)*

---

## 8 · 3:03–3:19 — promotion, and the first real commit

**On screen:** PROVISIONAL lights. RECLAIMED climbs off zero. A resource changes. The meter slows.

> Five consecutive runs where a verifier that re-derives real state agreed with the prediction.
> Only then does it commit. That is the first money this agent was ever allowed to touch.

---

## 9 · 3:19–3:29 — click MAKE THE TOOL LIE · RUN 6

**On screen:** from run six the tool reports success while changing nothing.

> Now the part every demo skips. From run six the delete tool reports success while changing
> nothing.

---

## 10 · 3:29–3:42 — the catch

**On screen:** the reviewer's line in the run log. The ladder falls back to SHADOW. A pip goes red.

> Verification never asks the tool how it went. It re-reads the environment, sees the gap, and
> takes the authority back. One disagreement, one rung, immediately.

---

## 11 · 3:42–3:54 — close

**On screen:** back to the top so the `run.app` URL is the last thing visible.

> An agent earns the right to act, one operation at a time. And loses it the moment it stops
> being correct.

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
