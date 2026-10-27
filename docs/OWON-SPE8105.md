# OWON SPE8105 în CDC

Instalare Windows: `py -m pip install -e .[usb,charger]`.

Închide conexiunea din aplicația OWON înainte de conectarea din pagina CDC: un port USB serial poate fi folosit de o singură aplicație. Alege portul sursei și apasă Conectare. Conectarea citește identificarea și valorile; nu activează ieșirea. Portul nu este reconectat automat după o întrerupere.

Pentru control automat, bifează „Controlează încărcătorul OWON” și introdu curentul de încărcare. Tensiunea sursei folosește valoarea „Tensiune full”. Curentul de terminare BW600 este separat de limita de curent a sursei și trebuie să fie mai mic decât aceasta.

La Start CDC, aplicația configurează programul nativ BW600, oprește ieșirea OWON, setează modul CCCV, tensiunea și curentul, citește valorile pentru confirmare, apoi activează sursa și pornește BW600. Sursa rămâne activată pe durata ciclului: modulul de încărcare ATORCH comută fizic conexiunea la baterie în etapele native charge/discharge. Nu conecta sursa direct în paralel cu bateria pentru această secvență.

La Stop, final de ciclu sau eroare, aplicația cere oprirea ambelor aparate și consemnează dacă oprirea sursei a fost confirmată. Pierderea comunicației sau citirile mai vechi de 5 secunde întrerup testul; o comandă OFF fără răspuns este raportată ca oprire neconfirmată. Oprirea aplicației sau pierderea USB nu garantează oprirea fizică a unei surse care nu mai comunică.

Panoul afișează măsurătorile proprii OWON V/A/W, separat de cele BW600. Aceste date sunt salvate pe fiecare eșantion CDC și incluse în grafice, CSV și raportul de tipărire/PDF. Butoanele manuale de configurare și pornire sunt blocate în timpul testelor.

## Protocol verificat

USB serial CH340, 115200 baud, 8N1, comenzi ASCII terminate cu LF. Identificarea trebuie să fie exact producător OWON, model SPE8105.

| Operație | Comandă |
|---|---|
| Identificare | `*IDN?` |
| Citire setări | `VOLT?`, `CURR?` |
| Stare ieșire | `OUTP?` |
| Măsurători | `MEAS:VOLT?`, `MEAS:CURR?`, `MEAS:POW?` |
| Reglare | `CONF:OUTP:MODE CCCV`, `VOLT 4.10`, `CURR 1.000` |
| Pornire / oprire | `OUTP ON`, `OUTP OFF` |

Limite software: valori finite pozitive, maximum 80 V, 10 A și 500 W. Setările sunt citite înapoi înainte de activare.

## Nivelul validării

Citire pe aparatul real: COM14, `OWON,SPE8105,24420629,FV:V1.1.0`; setări 4.200 V / 1.070 A, ieșire OFF, măsurători zero. Acestea sunt observații inițiale, nu valori configurate automat de aplicație.

Testele automate verifică identificarea, limitele, confirmarea setărilor, comanda ieșirii, oprirea la anulare și integrarea API. Ciclul complet cu OWON și baterie reală rămâne de verificat; nu a fost pornită încărcarea reală pentru dezvoltarea integrării.

Comenzile au fost extrase din programul OWON SP Series V1.0.0 furnizat de utilizator și citirile au fost confirmate pe USB. Programul proprietar nu este distribuit în acest repository. Referință producător: [SPE Series](https://owon.com.hk/products_owon_spe_series_dc_power_supply?FormType=ly).
