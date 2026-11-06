# Editable Thai motion hook

Silent five-second visual demo:1080x1920,30fps. Edit config.json for text/color and src/index.jsx for layout/timing. Fonts include their license. Dependencies are pinned in package-lock.json; node_modules is intentionally excluded.

Run from this folder, after checking that /usr/bin/chromium exists:

    npm ci --cache /tmp/ben-motion-npm-cache --no-audit --no-fund
    mkdir -p exports
    ./node_modules/.bin/remotion render src/index.jsx BenHook exports/preview.mp4 --browser-executable=/usr/bin/chromium --concurrency=1 --codec=h264 --crf=18 --props=config.json --image-format=jpeg

Requires Node.js, npm, Chromium/Chrome and sufficient disk space. Change the browser path for the actual machine. Reuse dependencies and source/config for revisions. This sample does not contain narration or prove audio/caption synchronization. Remotion license: https://www.remotion.dev/docs/license
