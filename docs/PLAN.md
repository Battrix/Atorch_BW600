# Plan de lucru

## Arhitectură

- Nucleu **Python 3.10+** (Windows, Linux x86, Raspberry Pi / ARM).
- Interfață web locală (frontend static), tip instrument de laborator.
- Un contract API comun, ca același frontend să poată vorbi fie cu serviciul Python (PC/RPi), fie cu firmware-ul ESP (`bw150.local`).
- Prioritate conexiune în interfață: Wi-Fi → Bluetooth → USB.

## Module

| # | Modul | Director | Stare |
|---|---|---|---|
| 1 | Nucleu de protocol (BW150, BW600) | `src/atorch/protocol` | de făcut |
| 2 | Transport USB HID | `src/atorch/transports/usb` | de făcut |
| 3 | Transport Wi-Fi (Tuya local BW600-DK; BW150 după cercetare) | `src/atorch/transports/wifi` | de făcut |
| 4 | Transport Bluetooth (BLE) | `src/atorch/transports/ble` | de făcut |
| 5 | Serviciu de aparat (coadă, verificare, reconectare, capabilități) | `src/atorch/service` | de făcut |
| 6 | Înregistrare date (sesiuni, SQLite, CSV) | `src/atorch/recorder` | de făcut |
| 7 | Interfață de laborator | `ui/` | de făcut |
| 8 | Rapoarte / certificate PDF | `src/atorch/reports` | de făcut |
| 9 | Pachetare (Windows, Linux, Raspberry Pi) și documentație | `packaging/` | de făcut |
| 10 | Validare pe aparate reale | `tests/hardware` | de făcut |
| 11 | Captură UART BW150 (baud, framing, comenzi) | `docs/uart` | de făcut |
| 12 | Firmware ESP32-C3 (punte UART, server web, mDNS, OTA) | `firmware/esp32c3` | de făcut |
| 13 | Ghid hardware de înlocuire modul Wi-Fi | `docs/hardware` | de făcut |
| 14 | Documentație continuă | `docs/` | continuu |

## Ordine propusă

1. Nucleu protocol + USB pe BW600-DK → serviciu → interfață (produs funcțional pe USB).
2. Wi-Fi Tuya pe BW600-DK.
3. Bluetooth.
4. Captură UART BW150 → firmware ESP32-C3 → test de înlocuire.
5. Înregistrare, rapoarte, pachetare, validare.

## To-do / idei

- [ ] Înlocuire modul Wi-Fi Tuya cu **ESP32-C3 SuperMini**, documentat complet; test pe **BW150** (BW600-DK rămâne cu Tuya ca referință).
- [ ] Interfața găzduită pe ESP, accesată de pe PC prin IP local sau `bw600.local` / `bw150.local` (mDNS).
- [ ] Captură UART pe BW150 înainte de orice lipire. Măsurat: capacitatea sursei de 3,3 V a plăcii.
- [ ] Opțional mai târziu: ESP32-S3 (USB host) ca dongle pentru acces complet la comenzi.
- [ ] Rezolvat contradicțiile din `SOURCES.md` pe aparat real.

## Limitări cunoscute

- ESP32-C3 nu poate fi USB host. Prin UART-ul Tuya probabil trec doar datapoint-urile Tuya (fără alarme curent/putere, calibrare, cicluri).
- BW150 Wi-Fi: protocolul serial nu este capturat; risc ridicat.
- Bluetooth: neverificat pe aparat.
