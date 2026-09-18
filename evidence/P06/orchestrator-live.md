# Durable dashboard orchestrator evidence

Revision `2ad955e` adds the durable dashboard-to-Pi turn path and the enabled
rootless user service `ebook-factory-worker.service`.

Real local, Tailscale, and LAN health checks returned HTTP 200 on port 6969.
A real dashboard message was queued with turn
`a82eaac1-6fea-43a0-a4a0-39dda4425ac0`, claimed by the worker, and completed by
`openai-codex/gpt-5.6-luna`. The assistant response was persisted as
`live worker online`; the usage record reported 1,142 input tokens and 7
output tokens with outcome `succeeded`.

The worker and API units are enabled and active under the `naki` user manager.
This proves durable completion and automatic dashboard refresh after the
completion event. Token-level streaming is not claimed by this evidence.
