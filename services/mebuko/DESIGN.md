# Mebuko launch page

Brief, 14 October 2026: multilingual bookkeeping for self-employed people in
Germany, including Freiberufler and Gewerbe. Planned launch 1 January 2027;
collect email addresses for one launch notice. The owner then requested vivid
multicolour Apple-advertising-like art direction and MacBook, iPad and iPhone
product previews. No Apple endorsement or tax-submission capability is claimed.

## Reference and assets

`design-reference.png` is the complete desktop concept, generated before the
frontend with the built-in Imagegen tool, at 1536 × 1024. It supersedes the initial
green concept. The generation brief asked for a pure-white page, dark system
type, rainbow headline/wordmark, left signup, right three-device studio image,
German terms next to translations, the exact launch date, and an unselected
consent checkbox. The brief prohibited testimonials, prices, fabricated metrics,
certification badges and private financial data.

`public/assets/devices.webp` is the separate Imagegen product-mockup asset.
The extraction brief preserved the silver MacBook / front-left iPad /
front-right iPhone composition, requested real transparency and crisp example
bookkeeping screens, and changed the illustrative account name to `Demo`.
Only fictitious `Musterkunde` and example transactions appear. The transparent
PNG was encoded losslessly with cwebp. No private accounting screenshot was
published. The site text, language controls, animated translation words, form,
consent, feedback and links are native HTML/CSS/JS.

## Design system and content inventory

Canvas `#fff`; ink `#0c1118`; supporting text `#576477`; thin borders `#c8cfd9`;
black primary action `#11171e`; rainbow red/orange/yellow/green/cyan/blue/violet.
System font; 4% desktop / 6% mobile gutters; open two-column desktop composition;
6–7px form corners. No font provider or analytics request. On mobile, copy is
followed by devices and then the signup form. Reduced motion stops animation.

Allowed German first-view copy:

- `mebuko`; `DE ES EN FR IT PT`
- `Deine Buchhaltung.` / `In deiner Sprache.`
- `Für Selbstständige in Deutschland.` / `Für Freiberufler und Gewerbe.`
- `Geplanter Start: 01.01.2027`
- `E-Mail-Adresse`; `deine@email.de`; `Zum Start benachrichtigen`
- `Ich möchte eine E-Mail zum Start von Mebuko erhalten.`
- `Informationen zu deinen Daten: Datenschutz.`
- `Bitte bestätige anschließend deine E-Mail-Adresse.`
- `Buchhaltung`, `Contabilidad`, `Accounting`, `Comptabilité`
- `Interface-Vorschau mit Beispieldaten`
- Copyright, Impressum, Datenschutz, Kontakt and the owner's requested footer data.

The catalog in `public/app.js` owns the six language variants and email/action
feedback. Legal copy is available in German and Spanish. Other language choices
on legal pages display the German text rather than an unverified translation.

## Fidelity and interaction checks

Desktop and 390px CSS mobile layouts were inspected in the Codex in-app browser.
The browser has a 110% scale: the ordinary screenshot API cropped the emulated
desktop panel. CUA's documented CDP capture was used for complete image evidence,
without changing the page content. Reference and browser captures were viewed
with `view_image`. Temporary screenshots remain outside Git.

| Comparison | Implementation and correction |
| --- | --- |
| Copy and date | German headline, audience, date, consent and CTA retained verbatim |
| White canvas and rainbow | Removed the green treatment; corrected gradient sizing to retain red through violet |
| Three devices | Separate transparent product asset; corrected excessive top gap and the original right-edge capture crop |
| Native signup | Real required email field, unchecked consent, working API feedback; black full-width action |
| Typography and spacing | Deliberate heading/body/control sizes; open layout and shared gutters; adjusted device/form balance |
| Mobile | All three devices stay visible; signup follows the preview; document width equals viewport width at 390px |
| Motion | Subtle translation-word movement; disabled by `prefers-reduced-motion` |
| Footer | Added the explicitly requested address/contact/VAT row; linked legal pages remain reachable |

Above-the-fold copy inventory matches the concept. Intentional differences:
complete usual owner footer; `Demo` account in the product image; locally
rendered system-font metrics and functional validation/confirmation states.
The product image is a labelled preview, not an interactive accounting app.
