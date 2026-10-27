# Atorch_BW600

Interfață PC tehnică (stil instrument de laborator) pentru sarcinile electronice / testerele de baterii **ATORCH BW600 / BW600-DK** și **ATORCH BW150**.

Proiect Battrix Energy.

## Obiective

- Conexiune prin **Wi-Fi** (preferat), **Bluetooth** și **USB** — toate trei funcționale.
- Rulează pe orice PC x86 (Windows, Linux) și pe Raspberry Pi / dispozitive ARM.
- Interfață proprie, nu o copie a aplicațiilor existente.
- Direcție ulterioară: înlocuirea modulului Wi-Fi Tuya cu un ESP32-C3 SuperMini, interfața accesibilă la `bw600.local` / `bw150.local`.

## Pornire rapidă

```
py -m pip install -e .[usb]        # o singură dată (Windows); pe Linux: python3 -m pip ...
py -m atorch --usb                 # aparat real, USB
py -m atorch --sim                 # aparat simulat, fără hardware
```

Se deschide interfața la `http://127.0.0.1:8787/`. Implicit serverul ascultă doar local.
Opțiuni: `--port`, `--host 0.0.0.0` (accesibil din rețea, fără autentificare), `--profile bw150`.

Teste automate: `py -m pip install -e .[dev]` apoi `py -m pytest -q`.
Teste pe aparat: `tools/probe_read.py` (doar citire), `tools/probe_load.py` (pornește sarcina scurt).

## Stare

Funcțional pe USB (BW600-DK verificat): protocol, transport USB, serviciu de aparat, interfață web.
În lucru: Wi-Fi, Bluetooth, BW150, înregistrare sesiuni, rapoarte. Vezi [docs/PLAN.md](docs/PLAN.md) și
[docs/TESTS-HARDWARE.md](docs/TESTS-HARDWARE.md).

## Documentație

- [docs/PLAN.md](docs/PLAN.md) — module, ordine de lucru, to-do
- [docs/SOURCES.md](docs/SOURCES.md) — surse și referințe
- [docs/DOCUMENTATIE-BW150-BW600.md](docs/DOCUMENTATIE-BW150-BW600.md) — documentația tehnică de bază (protocol USB HID, comenzi, firmware)

## Test de capacitate baterie (BCT) + certificat PDF
Vezi `docs/BCT.md`. Instalare: `py -m pip install -e .[usb,report]`, apoi pornești interfața și deschizi „Test baterie (BCT)”.
