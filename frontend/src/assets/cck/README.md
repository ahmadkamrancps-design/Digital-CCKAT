# Optimized campus photographs

These WebP files retain the dimensions and composition of the approved PNGs in
`public/assets/cck/`. They were encoded with libwebp 1.5.0 at quality 82, method 6.
The original PNG files and logo are retained.

From the frontend directory, with cwebp installed:

```bash
cwebp -q 82 -m 6 public/assets/cck/login-background.png -o src/assets/cck/login-background.webp
cwebp -q 82 -m 6 public/assets/cck/dashboard-campus.png -o src/assets/cck/dashboard-campus.webp
```

The login background decreases from 4,370,767 bytes to approximately 576 KB and
the campus banner from approximately 2.5 MB to 214 KB. Vite fingerprints these
assets so updates receive new URLs and can be cached safely.
