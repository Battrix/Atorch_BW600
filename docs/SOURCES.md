# Surse și referințe

## Surse primare

1. **docs/DOCUMENTATIE-BW150-BW600.md** (rev. 27 octombrie 2026) — protocol USB HID, comenzi, payload-uri, firmware, Wi-Fi/UART. Notă: unele elemente sunt marcate „neconfirmat" în document.
2. **https://github.com/sq6emm/bw600** — aplicație Linux GUI/CLI pentru BW600/BW600-DK (USB-HID, Python). Referință pentru protocol, Wi-Fi Tuya local (tinytuya, DP 101–122), dezasamblarea firmware-ului. Doar referință; nu copiem interfața.
3. **https://github.com/1RandomDev/atorch-bw150-esphome** — pistă externă pentru protocolul serial BW150 / conversie locală cu ESP. Neverificată pe unitățile noastre.

## Date de bază

| | BW150 | BW600 / BW600-DK |
|---|---|---|
| USB | VID 0483, PID 5750 | VID 0483, PID 5750 |
| Firmware analizat | 1.1.0 | 2.0.5 (și 2.0.3) |
| Cadru comandă | `55 05 01 CMD d0..d3 EE FF` (64 B) | idem |
| Răspuns | `AA 05 01 TYPE ...` | idem |
| Wi-Fi | modul T1-2S/TL, protocol neidentificat | modul Tuya, control local cu tinytuya |
| Bluetooth | necunoscut | probabil același protocol `55 05` (neverificat); note anterioare: BLE FF55, serviciu AE30, caracteristica AE01 |

## Contradicții de rezolvat prin test pe aparat

- Offseturile payload-ului 05 și ordinea câmpurilor diferă între documentația noastră și repo-ul sq6emm. Se decide cu măsurători pe BW600-DK real.
- Comanda 35: pe BW150 = număr cicluri, pe BW600 = reset (în doc.); în sq6emm comenzile 32/33/34 = clear/factory reset/zero. Profilul fiecărui aparat se verifică separat.
- Atenție: comanda `02` cu adresa `09` pornește bootloader-ul — nu se trimite niciodată.
