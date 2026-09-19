# Network reconciliation evidence

Date: 2026-09-19 (Asia/Kolkata)

The owner reported `ERR_CERT_AUTHORITY_INVALID` while opening the raw private
LAN IP. The transport policy was changed so the explicitly requested trusted
LAN path is plain HTTP, while the Tailscale path remains HTTPS. The launcher
also has a focused regression test proving that TLS is applied to the Tailscale
address, omitted from private LAN and loopback by default, and re-enabled for
private LAN only with `EBOOK_FACTORY_PRIVATE_TLS=true`.

Use this exact URL from a LAN device:

```text
http://192.168.29.14:6969
```

Do not use `https://192.168.29.14:6969`; that is a different protocol and will
still produce a certificate error. The LAN HTTP choice means credentials are
not encrypted from other observers on the trusted LAN. Use the Tailscale HTTPS
listener outside that boundary.

Checks:

- `bash scripts/tests/test_serve_api_transport.sh` passed.
- `bash scripts/tests/test_serve_api_tls.sh` passed.
- `bash -n scripts/serve-api.sh` passed.
