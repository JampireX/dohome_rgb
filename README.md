<p align="center">
    <img src="./custom_components/dohome_rgb/brand/icon@2x.png" width="120" />
    <h3 align="center">DoHome</h3>
    <p align="center">Home Assistant integration</p>
    <p align="center">
        <a href="https://github.com/JampireX/dohome_rgb/actions/workflows/release.yml">
            <img src="https://github.com/JampireX/dohome_rgb/actions/workflows/release.yml/badge.svg" />
        </a>
        <a href="https://github.com/hacs/integration">
            <img src="https://img.shields.io/badge/HACS-Custom-orange.svg" />
        </a>
        <a href="https://github.com/JampireX/dohome_rgb/releases">
            <img src="https://img.shields.io/github/v/release/JampireX/dohome_rgb?sort=semver" />
        </a>
    </p>
</p>

---

Control **DoHome** Wi-Fi lights from Home Assistant entirely over your **local
network** — no cloud account, no DoHome app, no internet required. The
integration talks to each device directly over TCP, so it keeps working even
when your internet is down.

## Supported devices

DoHome / DOIT Wi-Fi lights based on the local DoHome protocol:

* **RGBW bulbs** (`DT-WYRGB`)
* **White / tunable-white bulbs** (`DT-WY`)
* **LED strips** (`STRIPE`)

## Features

* **RGB color** and **white color temperature** (3000–6400 K)
* **Brightness** control
* **27 built-in hardware effects** — gradients, jumps and strobes (e.g. *RGB
  Gradient*, *Seven Jump*, *Red Strobe*), selectable from the light's effect list
* **Automatic discovery** — devices on your network show up on their own as
  ready-to-add **"discovered device" cards** in *Settings → Devices & services*
* **Network scan with multi-select** — add several lights at once without typing
  a single IP address
* **Manual add** by IP address / hostname for full control
* **Reconfigure** — change a device's address later without deleting and
  re-adding it (and a device that changes IP via DHCP is updated automatically
  when re-discovered)
* **Resilient** — local state tracking with automatic reconnection after the
  device or network drops out
* **Group control** via standard Home Assistant light groups
* **Localized UI** — English, Russian, German, French, Spanish, Italian, Polish

## Installation

### HACS (custom repository)

1. In HACS, add this repository as a
   [custom repository](https://hacs.xyz/docs/faq/custom_repositories):
   `https://github.com/JampireX/dohome_rgb` (category: **Integration**).
2. Find **DoHome** in the list and click **Download**.
3. Restart Home Assistant.

### Manual

Copy the `custom_components/dohome_rgb` folder into your
`<config>/custom_components` directory and restart Home Assistant.

## Adding devices

Everything is configured from the UI — there is no YAML setup.

**Automatic (recommended).** Once the integration is loaded, it scans the local
network every minute and shows each not-yet-added light as a **discovered
device card** in *Settings → Devices & services*. Just click **Add**.

**Add several at once.** *Add integration → DoHome*, leave the address field
**empty**, and the integration scans the network and lets you **pick multiple
devices** to add in one go.

**Add one by address.** *Add integration → DoHome*, enter the device's **IP
address or hostname**.

> Tip: give your bulbs static IPs (or DHCP reservations). If an address does
> change, use **Reconfigure** on the device, or let background discovery pick up
> the new address automatically.

## Using effects

Each light exposes the 27 firmware effects through Home Assistant's standard
**effect** control (in the more-info dialog or via `light.turn_on` with the
`effect` attribute). Selecting a normal color or color temperature turns the
effect off again.

## How it works

The integration is **local polling**: it has no cloud or push channel, so it
queries each device directly over TCP (port 5555) and discovers devices via UDP
broadcast (port 6091). All device protocol handling lives in the external
[`dohome-api`](https://pypi.org/project/dohome-api/) library.

## Credits

* **Rave** — the original
  [DoHome HASS component](https://github.com/SmartArduino/DoHome/tree/master/DoHome_HassAssistant_Component).
* **[Mikhael Khrustik (@mishamyrt)](https://github.com/mishamyrt)** — the Home
  Assistant integration this project is based on.
* **[Jampire (@JampireX)](https://github.com/JampireX)** — current maintainer
  (migration to current Home Assistant, network discovery, multi-device setup,
  light effects, localization).
