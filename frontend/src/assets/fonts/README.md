# Locally served Latin fonts

The existing Inter and Libre Baskerville families are bundled locally to avoid a
render-blocking third-party stylesheet and extra font-provider connections.
These are the Google Fonts Latin variable WOFF2 files, downloaded 24 November 2026,
with their SIL Open Font License files alongside them. CSS uses font-display: swap.
The existing Noto Naskh Arabic font and Urdu rendering are unchanged.

- Inter v20: https://fonts.gstatic.com/s/inter/v20/UcC73FwrK3iLTeHuS_nVMrMxCp50SjIa1ZL7.woff2
  SHA-256: `3100e775e8616cd2611beecfa23a4263d7037586789b43f035236a2e6fbd4c62`.
- Libre Baskerville v24: https://fonts.gstatic.com/s/librebaskerville/v24/kmKnZrc3Hgbbcjq75U4uslyuy4kn0qNZaxM.woff2
  SHA-256: `22219fb90e3b9bd28debd1825fe8d9a0154a0e31f8b3fa601ac1a0a5aa5e6d1b`.

License sources: Google Fonts repository `ofl/inter/OFL.txt` and
`ofl/librebaskerville/OFL.txt`. Vite emits content-hashed font URLs for safe caching.
