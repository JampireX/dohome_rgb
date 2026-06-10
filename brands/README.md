# Brand assets for home-assistant/brands

Staging copy of the DoHome icon for a pull request to
[home-assistant/brands](https://github.com/home-assistant/brands). These files
are **not** used by the integration or by Home Assistant directly — HA shows an
integration's icon only from the brands repository (CDN).

```
custom_integrations/dohome_rgb/
├── icon.png      256×256
└── icon@2x.png   512×512
```

Source: the official **DoHome** app icon (Apple App Store id `1374240531`, by
DOIT/SmartArduino). Trademark of its owner; reused only to identify the matching
hardware in Home Assistant.

## How to submit

1. Fork <https://github.com/home-assistant/brands>.
2. Copy `custom_integrations/dohome_rgb/` from here into the fork (same path).
3. Commit, push, and open a pull request against `home-assistant/brands`.

With the GitHub CLI authenticated (`gh auth login`):

```sh
gh repo fork home-assistant/brands --clone --remote
# copy custom_integrations/dohome_rgb/{icon.png,icon@2x.png} into the clone
gh pr create --repo home-assistant/brands --title "Add dohome_rgb (DoHome)" \
  --body "Brand assets for the DoHome custom integration (https://github.com/JampireX/dohome_rgb)"
```
