# CCK image assets

Available image filenames:

- `logo.png`: approved CCK logo with a transparent background.
- `login-background.png`: approved login artwork or photograph.
- `dashboard-campus.png`: approved photograph of the actual campus.

All three PNG images are present in this directory.
`CCKLogo` loads `/assets/cck/logo.png` directly and accepts an optional `size` prop
(default 52 pixels). The login page uses `login-background.png` and the candidate
dashboard banner uses `dashboard-campus.png`.

Files under `public/` are publicly accessible. Do not put secrets, candidate data,
exam exports, or answer keys here. The URL prefix is `/assets/cck/`, not `/public/`.
