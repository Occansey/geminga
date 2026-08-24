# Geminga — the 4-minute demo film

**Hard requirements (All Things Agentic):** no longer than 4 minutes · publicly visible on
YouTube or Vimeo · must demonstrate **the backend running on Google Cloud** · English or
English subtitles.

**Judged on:** does it show live functionality, and is the pitch clear. So this is a *screen
recording of the real console*, not motion graphics. Every frame is the deployed Cloud Run
service at `agentic-core-468826425509.us-central1.run.app`, driven by Playwright so the run is
deterministic and reshootable.

## The spine

The film has one job: prove that an agent can **earn** the right to act and **lose it the moment
it stops being correct** — and that the loss is caught by re-derived state, not by asking the
agent how it went. Everything else is set dressing.

## Shot list (3:50 target, 10s headroom)

| # | t | on screen | narration |
|---|---|---|---|
| 1 | 0:00–0:22 | Live console, cold. `$3,583.20` monthly waste counts up. URL bar visible. | Monday morning, a billing alert. Something has been running since Friday. The engineer on call already knows what to delete. That was never the hard part. |
| 2 | 0:22–0:45 | Scroll the estate: `ml-train-01 $2,632`, the `HUMAN` locks. | The hard part is blast radius. Delete the wrong disk at 9am and you cost more than the bill. So the ticket gets parked, and the same alert fires next month. |
| 3 | 0:45–1:05 | Authority ladder, SHADOW lit. | Every agent aimed at this lands on the same answer: never let it act. That doesn't fix anything. It just leaves a person to be brave before coffee. |
| 4 | 1:05–1:50 | Click **Run the ladder**. Runs 1–4 in SHADOW: rehearsals, estate untouched, pips filling. | So Geminga asks a different question. Not how do we make the agent confident, but how does it earn the right to act. Every operation starts in rehearsal. It predicts a delta and commits nothing. |
| 5 | 1:50–2:15 | Promotion to **PROVISIONAL**. First real commit. `staging-web-3` goes stopped, RECLAIMED climbs off zero. | Five consecutive runs where a verifier that re-derives real state agrees with the prediction. Only then does it commit. That is the first money this agent was ever allowed to touch. |
| 6 | 2:15–2:55 | Click **Make the tool lie · run 6**. Tool reports success, changes nothing. | Now the interesting part. From run six the tool reports success while changing nothing. This is the failure every agent demo skips. |
| 7 | 2:55–3:20 | Verification catches it. Log shows the reviewer's reason. Ladder **demotes**, pip turns red. | Verification does not ask the actuator how it went. It re-derives state from the environment, sees the gap, and takes the authority back. One disagreement, one rung, immediately. |
| 8 | 3:18–3:36 | `delete_unattached_disk` row with the `HUMAN` lock held. | Irreversible operations stay behind a human at every rung, forever. The ladder governs doubt. It does not govern consequence. |
| 9 | 3:36–3:56 | Cloud Run URL in the address bar; cut to GCP console showing the service **live**. | An agent earns the right to act, one operation at a time. And loses it the moment it stops being correct. |

## Disclosure, on screen

The console's footer already states the estate is a demo fixture. Shot 2 holds long enough to
read it. We say it rather than let a judge find it: the live path is the same code, the account
we could point at is empty, and a console of `$0.00` demonstrates nothing.

## Capture

`node film/shoot.mjs` — Playwright drives the deployed console at 1920×1080 and writes
`out/raw.webm`. Deterministic: same clicks, same waits, reshootable after any change.

`node film/assemble.mjs` — ffmpeg trims to the shot list, crossfades, muxes narration, burns
subtitles, exports `out/geminga.mp4` (H.264, ≤4:00).

Narration uses the same two Gemini TTS voices as the other films, so the set sounds like one hand.
