# Brand assets (for home-assistant/brands)

Home Assistant shows an integration's icon from the
[home-assistant/brands](https://github.com/home-assistant/brands) repository,
**not** from this integration. These files are staging only — they are not used
by the component at runtime.

`custom_integrations/dohome_rgb/`
- `icon.png` — 256×256
- `icon@2x.png` — 512×512

Source: the official **DoHome** app icon (Apple App Store id `1374240531`,
by DOIT/SmartArduino). It is a trademark of its owner; it is reused here only to
identify the matching hardware in Home Assistant, the same way other vendor
brands are hosted in `home-assistant/brands`.

## How to publish the icon

1. Fork <https://github.com/home-assistant/brands>.
2. Copy this folder's contents to `custom_integrations/dohome_rgb/` in the fork
   (same file names).
3. Commit, push, and open a pull request against `home-assistant/brands`.
4. Once merged, HA shows the icon for the `dohome_rgb` domain (after the next
   brands CDN refresh; may take a little while).

With the GitHub CLI authenticated (`gh auth login`) this can be automated:

```sh
gh repo fork home-assistant/brands --clone --remote
# copy the two PNGs into custom_integrations/dohome_rgb/ in the clone
gh pr create --repo home-assistant/brands --title "Add dohome_rgb" \
  --body "Add icon for the DoHome custom integration"
```

> Note: brands prefers transparent icons, but the DoHome icon is a white mark on
> a solid cyan background (that is the brand). A colored square icon is accepted
> for cases like this.
