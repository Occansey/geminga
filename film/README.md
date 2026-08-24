# The film

A screen recording of the **deployed** console, not motion graphics. The rules require showing
the backend running on Google Cloud, and judges reward live functionality — so every frame is
`agentic-core-468826425509.us-central1.run.app`, driven by Playwright so the run is
deterministic and reshootable after any change.

    npm install && npx playwright install chromium
    node shoot.mjs        # drives the live console -> out/*.webm  (~4 min, real time)
    # then trim the page-load head and encode:
    ffmpeg -ss 11.5 -t 234 -i out/raw.webm -c:v libx264 -preset slow -crf 19 \
           -pix_fmt yuv420p -r 30 -movflags +faststart -an -y out/geminga-silent.mp4

Shot list and narration: [`../docs/FILM.md`](../docs/FILM.md).

Why not Remotion: it renders a *depiction* of the product. Here the product itself is the
strongest asset, and a judge can tell the difference.
