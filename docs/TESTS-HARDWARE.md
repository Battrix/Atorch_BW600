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

## 2026-10-27 — BW600-DK, USB, primul test cu scriere: CC 0.5 A, cutoff 3.1 V, 6 s (`tools/probe_load.py`)

Celula LiFePO4 3.2 V / 300 Ah, 3.245 V la start. Rezultat script: OK (oprire confirmata, setari restaurate).

- **Scrierile functioneaza**: mod CC (0x47), setpoint (0x21), cutoff (0x29), run (0x25) — toate confirmate prin recitire.
- Flag-ul de rulare (offset 48) devine 1 imediat dupa RUN; curentul porneste cu intarziere si creste in ~3.5 s (soft-start), apoi se stabilizeaza.
- Curent stabilizat: ~0.516 A la setpoint 0.500 A (+3%). Puterea citita = V x I (3.235 x 0.516 = 1.669 W, confirmat) — scara puterii consistenta cu cea a tensiunii si curentului.
- Tensiunea scade usor sub sarcina: 3.248 -> 3.235 V.
- Setarile dinaintea testului erau mod=0 (CC), setpoint=1.0, cutoff=14.8 (diferite de prima citire, schimbate de utilizator intre timp); au fost restaurate exact.

Neverificat: acuratetea curentului fata de un ampermetru extern (diferenta de 3% poate veni din calibrare:
cal_current=0.919 pe aparat), ventilatorul sub sarcina, energia/capacitatea acumulate, comenzile de timer/cicluri.
Pentru UI: curentul NU urmeaza instant setpoint-ul; afisarea trebuie sa tolereze ~4 s de rampa.

## 2026-10-27 — Fotografii ale ecranului BW600-DK (fw V2.0.5)

**Ecranul BCT** (Battery Cap_Test): este un ecran de tip CC cu indicator de baterie. Afiseaza `Model: CC`,
`Is: 10.000A` (curentul setat), `Full Voltage 030.00V`, `Zero Voltage 002.80V`, `Bat: 01`, `Run 000:00:52`,
mAh, Wh, V, A, W, `Mos.T`, `ETS.T`. Procentul = (V - Zero) / (Full - Zero): (3.24 - 2.80) / (30 - 2.80) = 1.6% -> afisat 001%.
Concluzie: Full Voltage = comanda 0x2A, Zero Voltage = cutoff (0x29), Is = setpoint (0x21). Profilul CC al aplicatiei e corect in esenta.

**Meniul principal** are doua pagini:
- Pagina 1: Settings, CC, CV, CR, CP, BRT (Battery Res_Test), PT (Power Tester), CT (Cable_res Tester), CDC (Charge-discharge-3), CDCDC (-5), CDxn (-n), CC cu unda.
- Pagina 2: variante cu pictograma de unda (CV, CR, CP, CDC, CDCDC), BCT, Dynamic load, "Developing" (loc rezervat).
Modurile peste ID 9 (variantele cu unda, BCT, Dynamic load) nu sunt in sursele noastre. De aflat prin observare pasiva (`tools/probe_modes.py`).

**ETS.T: Wait..** = senzorul extern de temperatura nu este conectat. Valoarea "sonda" citita (~35 C) este probabil nevalida cand senzorul lipseste.
**HID** in bara de sus = conexiunea USB HID activa. **Run 000:00:52** = timp de rulare afisat pe aparat (nedecodificat in 05 inca).
