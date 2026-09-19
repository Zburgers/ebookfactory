# Tailscale and local access audit

Date: 2026-09-19

Observed on Razor Crest:

- Tailscale `1.102.2`, backend `Running`.
- MagicDNS hostname: `razor-crest.tail4792a2.ts.net`.
- Tailscale IPv4: `100.87.104.100`.
- LAN IPv4: `192.168.29.14`.
- Ebook Factory listens on port `6969` on loopback, LAN and Tailscale;
  systemd user services are enabled and active.
- Current certificate is self-signed with IP SANs for the Tailscale and LAN
  addresses, so the requested raw-IP URL works through a trust exception.

`tailscale cert` can issue a publicly trusted certificate for the MagicDNS
hostname, which would validate:

`https://razor-crest.tail4792a2.ts.net:6969`

It cannot issue a certificate for `100.87.104.100` or `192.168.29.14`. The
current IP-SAN certificate is therefore retained so the owner's requested
`<tailscale-ip>:6969` path remains usable. No Tailscale Funnel route targets
port 6969; access remains bounded to Tailscale, LAN and loopback.
