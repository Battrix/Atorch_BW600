# Teste pe aparate reale

## 2026-10-27 — BW600-DK, USB, doar citire (`tools/probe_read.py`)

Aparat: `ATORCH BW600 V2.0.5`, serie 968511, USB HID 0483:5750. Windows 11, Python 3.14.3, hidapi 0.15.0.
Conditii: sarcina oprita, nimic conectat la intrare.

**Rezultat: citirea 03 (configuratie) si 05 (masuratori) functioneaza.**

Configuratia citita are valori coerente (mod=1/CV, cutoff 14.8 V, full 30 V, OCP 52 A, OPP 610 W,
NTC-OTP 75 C, MOS-OTP 120 C, luminozitate 9). Layout-ul payload-ului 03 din ambele surse este confirmat.

Payload 05 brut:
```
00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 77 96 98 00 00 00 00 00 f4 01 00 00 60 6d 00 00
b7 88 00 00 b9 61 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 20 00
```

Interpretare pe offset (in payload):
| Offset | Brut | Valoare | Interpretare |
|---|---|---|---|
| 16 | 0x00989677 | 9999.991 | rezistenta (circuit deschis) — **confirma layout sq6emm** |
| 24 | 0x01F4 | 0.500 | capacitate mAh (contor) |
| 28 | 0x6D60 | 28.000 | temperatura CPU C |
| 32 | 0x88B7 | 34.999 | temperatura sonda C |
| 36 | 0x61B9 | 25.017 | temperatura MOSFET C |

**Concluzie:** profilul `bw600` (layout sq6emm) este corect pentru masuratori. Profilul `bw600-doc` este
infirmat (ar fi dat 9999.991 Wh la 16, imposibil). Documentatia `DOCUMENTATIE-BW150-BW600.md` trebuie
corectata la sectiunea 7, coloana BW600.

**Inca neverificat:** scara tensiunii/curentului/puterii si a energiei sub sarcina reala; comenzile de
scriere; ventilatorul (0 in repaus); BW150.

## 2026-10-27 — BW600-DK, USB, citire cu celula de 3.2 V conectata (sarcina oprita)

Multimetru: 3.299 V. Aparat (profil `bw600`): 3.294 V (payload offset 4 = 0x0CDE = 3294, scara /1000).
Diferenta 0.15% — in toleranta (contact, fire). **Scara tensiunii confirmata.**
Curent/putere = 0 (sarcina oprita), rezistenta ramane 9999.991 (afisata la circuit deschis).
Neverificat: scara curentului si a puterii (necesita sarcina pornita — comenzi de scriere).
