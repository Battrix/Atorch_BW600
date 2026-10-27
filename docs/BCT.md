# Test de capacitate (BCT) construit în PC

BCT-ul nativ al aparatului (ID de mod 11) nu poate fi selectat prin USB (vezi `TESTS-HARDWARE.md`), așa că îl construim
în PC, peste modul **CC** al aparatului. Funcționează identic pe orice transport.

## Flux
1. În pagina **Test baterie (BCT)** (`/bct.html`) alegi bateria din baza de date sau o introduci: model, chimie,
   elemente în serie, capacitate declarată. Butonul *Calculează* completează tensiunile (nominală, full, descărcată)
   și curentul 0,2C; toate se pot modifica.
2. Se pot seta: pragul de acceptare (implicit **80 %** din capacitatea declarată) și, opțional, rezistența internă maximă.
3. **Start test**: PC-ul setează aparatul pe CC, tensiunea de oprire = tensiunea descărcată, curentul ales, pornește sarcina.
   Aparatul însuși oprește sarcina la tensiunea de descărcat; PC-ul verifică în plus (3 eșantioane sub prag → Stop).
4. Se înregistrează la ~1 Hz: V, A, W, temperaturi. Capacitatea (Ah) și energia (Wh) se integrează din curentul măsurat.
5. **Rezistența internă DC** = (tensiune în repaus la start − tensiune sub sarcină) / curent, luată când curentul s-a
   stabilizat (±5 %). Include cablurile și contactele.
6. Rezultat: **POZITIV** (capacitate ≥ prag și, dacă e setată, Ri ≤ limită), **NEGATIV**, sau **NEFINALIZAT**
   (oprit de operator/de pe aparat înainte de tensiunea de descărcat, conexiune pierdută, eroare).
7. **Certificat PDF** (buton): antet Battrix Energy, model, tensiuni, valori măsurate, durată, dată, 4 grafice, rezultat.

## Date pe disc (folderul `data/`, ignorat de git; se poate schimba cu variabila `ATORCH_DATA`)
- `batteries.json` — baza de baterii (modele, tensiuni, capacitate, prag, Ri max = valori de referință).
- `tests/<id>.json` — fiecare test, cu eșantioane și rezultat.
- `workshop.json` — datele atelierului pentru antetul certificatului (creat automat; îl poți edita).

## Siguranță
- Se refuză pornirea dacă: aparat neconectat, sarcina rulează deja, curent/putere peste limitele aparatului,
  bateria e la sau sub tensiunea de descărcat, sau peste ~108 % din tensiunea full.
- Dacă PC-ul pierde conexiunea, aparatul își oprește singur sarcina la tensiunea de oprire.
- Stop (sus, mereu vizibil) oprește testul și sarcina.

## Dependențe
`py -m pip install -e .[usb,report]` (sau `launchers\Instaleaza-Dependinte.bat`). Certificatul folosește `reportlab` și
fonturile DejaVu incluse (diacritice românești).

## Limitări cunoscute
- Capacitatea de pe ecranul aparatului nu este folosită; se calculează din curentul măsurat.
- Rezistența internă la curenți mari include rezistența cablurilor; de preferat cabluri scurte, groase.
- Neverificat încă pe aparatul real (doar simulator).
