# Optimized campus photographs

These WebP files are generated from the approved PNGs in `public/assets/cck/`.
The updated login photograph is resized proportionally from 6144 × 4608 to
1920 × 1440 and encoded at quality 82, method 6 with libwebp 1.5.0. The colour
crest is resized to 256 pixels wide and encoded losslessly, preserving
its transparency. The original PNG files are retained.

From the frontend directory, with cwebp installed:

```bash
cwebp -resize 1920 0 -q 82 -m 6 public/assets/cck/login-background.png -o src/assets/cck/login-background.webp
cwebp -resize 256 0 -lossless -exact -m 6 public/assets/cck/logo.png -o src/assets/cck/logo.webp
cwebp -q 82 -m 6 public/assets/cck/dashboard-campus.png -o src/assets/cck/dashboard-campus.webp
```

The campus banner is approximately 214 KB. Vite fingerprints the background,
banner and logo so updated artwork receives new URLs and can be cached safely.
The logo component displays the colour crest without an added background or padding.

Container builds exclude the full-resolution background and campus source PNGs
through the root `.dockerignore`; the optimized WebP assets are bundled instead.
