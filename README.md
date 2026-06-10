<p align="center">
    <img src="./docs/logo@2x.png" width="120" />
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

Home Assistant integration for DoHome smart lights. Supports DoHome RGB bulbs and
LED strips, controlled locally over your network.

## Features

* RGB color and white color temperature
* Brightness control
* 27 built-in hardware effects (gradients, jumps, strobes)
* Automatic discovery — devices on the network appear as ready-to-add cards
* Manual setup by IP/hostname, or scan and add multiple devices at once
* Reconfigure a device's address without removing it
* Live state updates and automatic reconnection
* Group control

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

## Configuration

Devices are configured through the UI:

1. Go to **Settings → Devices & services → Add integration**.
2. Search for **DoHome**.
3. Either:
   * leave the address field **empty** to scan the network and pick the devices
     you want, or
   * enter a device **IP address / hostname** to add a single device.

Devices found on the network also appear automatically as discovered
"found device" cards in **Settings → Devices & services**.

To change a device's address later, use **Reconfigure** on its entry.

## Credits

* **Rave** — the original
  [DoHome HASS component](https://github.com/SmartArduino/DoHome/tree/master/DoHome_HassAssistant_Component).
* **[Mikhael Khrustik (@mishamyrt)](https://github.com/mishamyrt)** — the Home
  Assistant integration this project is based on.
* **[Jampire (@JampireX)](https://github.com/JampireX)** — current maintainer
  (migration to current Home Assistant, network discovery, light effects).
