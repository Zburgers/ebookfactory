# Live browser-close and worker-restart evidence

Date: 2026-09-19 (Asia/Kolkata)

Disposable project `ad697541-ce0b-4e5f-8d7f-7b601792d614` was approved for run
`26edf5c1-075d-44fe-9c27-a529461b776c`. The no-art nonfiction run used the
enabled systemd worker and the local owner API.

1. The production task reached `running` after its outline dependency
   succeeded.
2. Headless Chromium opened `http://127.0.0.1:6969/`; the captured DOM title
   was `Ebook Factory`. The browser process was terminated after the page
   loaded; no worker or job cancellation was requested by that close.
3. The worker main process was then terminated with
   `systemctl --user kill --kill-who=main -s SIGKILL ebook-factory-worker.service`.
   The user service restarted automatically, and the expired lease was
   reclaimed at fencing generation 2.
4. The same run completed after recovery:

   - outline: `succeeded`, generation 1, one attempt
   - production: `succeeded`, generation 2, two attempts
   - final project state: `draft_review`
   - artifact: `26edf5c1-075d-44fe-9c27-a529461b776c/book.md`, 8,861 bytes,
     SHA-256 `f171dc0981c1f3afcc43339a5e1c221d7aadc7a4a76787bb00bc34221295f456`
   - usage: outline `1192` input / `293` output; production `1531` input /
     `1655` output, both `openai-codex/gpt-5.6-luna`

This is direct evidence that a closed browser does not own or cancel the
production job and that worker restart/reclaim preserves the durable run.
