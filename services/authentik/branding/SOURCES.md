# Beach Lab identity sources

Captured and checked on 2026-10-08 from [beachlab.org](https://beachlab.org/).
Use these original assets and tokens for future changes to the login page.
Do not replace the logo with a generated wordmark or introduce a different
palette, typeface or authentication copy.

| Asset | Original source |
| --- | --- |
| `assets/beachlab-logo.svg` | [img/tbl_clear.svg](https://beachlab.org/img/tbl_clear.svg), copied without changes |
| `assets/beachlab-favicon.svg` | [img/favicon.svg](https://beachlab.org/img/favicon.svg), copied without changes |
| `assets/univers-thin.woff2` | [files/univers-thin.woff2](https://beachlab.org/files/univers-thin.woff2), copied without changes |
| `assets/univers-light.woff2` | [files/univers-light.woff2](https://beachlab.org/files/univers-light.woff2), copied without changes |
| `assets/beachlab-caustics.png` | Static 1280 x 720 capture of the original [src/caustics.js](https://beachlab.org/src/caustics.js?v=20261006b), with the site's [shader-settings.json](https://beachlab.org/shader-settings.json?v=20261006b), Three.js 0.164.1 and yellow `#f9e231` |

The water capture used an isolated temporary page containing only the original
canvas effect, without logos or text, and was not edited. Authentication uses
this static frame, avoiding an additional WebGL renderer or animation in the
login flow.
The renderer and settings copied into that temporary page matched their public
HTTP versions byte for byte: renderer SHA-256
`09d3fdd501822eba41234aa7c725e88033edfb49c3b955da5a94c2dd66f32d2b`,
settings SHA-256
`69f3e05bccce34d1edc30474743a0adfcec39885d64827349cd77a60c58feb48`.

The live site's stylesheet is
[css/tailwind.css?v=20260913shade9](https://beachlab.org/css/tailwind.css?v=20260913shade9).
Its source in `/Users/Papi/Repositories/website/src/style.css` defines yellow
`#f9e231`, body ink `#0c0c0c`, black `#1a1a1a`, Univers Thin and Univers Light.
Its header keeps dark ink on yellow even when `prefers-color-scheme` is dark.
The login applies the same decision, with 48 px minimum retry-button height
and a visible focus outline.

Authentik compatibility is tied to
[2026.8 branding](https://version-2026-8.goauthentik.io/customize/branding/),
[file picker paths](https://version-2026-8.goauthentik.io/customize/file-picker/),
[FlowExecutor](https://github.com/goauthentik/authentik/blob/version/2026.8.2/web/src/flow/FlowExecutor.ts)
and [AKElement](https://github.com/goauthentik/authentik/blob/version/2026.8.2/web/src/elements/Base.ts).
The script uses only the native brand PATCH and media file upload API; it does
not alter Authentik source, templates, authentication flows or Nginx.

## Asset SHA-256

```text
7ae079a8298a16c1901a03671f04564a871b27deb8b301a1734218d5456885b3  assets/beachlab-caustics.png
38f0dff0afa0b0c6ed989251e3443dfd2b79a1209d66849c4485419ccdf6118e  assets/beachlab-favicon.svg
8b1247e041efefffba3cf40257bdc240f186538a56b25826b241900dd5c67260  assets/beachlab-logo.svg
466b43875e1b9a3cb7d3eb370311480fe79a011419f863e3907120a39294dfc6  assets/univers-light.woff2
849ccbd020314c84d53ed9c65bb66e7ac6a842dedbfd6939cf8d2f6509854178  assets/univers-thin.woff2
```
