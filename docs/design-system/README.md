# Hawlak design system

Shared visual source for the dashboard and the landing page.

## Files

- `Hawlak Identity Kit.dc.html` — **primary source of truth** for the selected open-ring mark, bilingual lockups, typography, spacing, colors, clinical UI, patient UI, and design QA.
- `Hawlak Screens.dc.html` — **primary product-screen reference** for clinical and patient compositions.
- `support.js` — local renderer required by the two `.dc.html` references. Open the `.dc.html` files in a browser with this file beside them.

## Core tokens

| Role | Value |
|---|---|
| Primary blue | `#2B66E4` |
| Supporting teal | `#4A91A7` |
| Rare signal citron | `#D8CA21` |
| Ink | `#111418` |
| Canvas | `#F6F7F7` |
| Border | `#E6E8EB` |
| Muted text | `#717780` |
| Corner radius | `10–14px` |
| Spacing scale | `4 / 8 / 12 / 16 / 24 / 32 / 48 / 64 / 96px` |

Latin text uses Neue Montreal only when licensed and available, then Inter or Helvetica Neue. Arabic uses IBM Plex Sans Arabic when available, then Noto Sans Arabic or Tahoma. Do not add letter spacing to Arabic.

## Dashboard implementation rule

Retaj should start with `Hawlak Identity Kit.dc.html` and `Hawlak Screens.dc.html`, then reuse the tokens and interaction patterns rather than copying the reference HTML as application code. Keep the dashboard white, information-first, bilingual, accessible, and honest about status. Medicine photos are not marked correct until a pharmacist reviews them.
