# ATORCH BW150 / BW600 — documentație tehnică și utilizare

Revizie: 27 octombrie 2026. Document bazat pe firmware-urile furnizate, codul aplicației și verificările USB înregistrate în proiect. Nu reprezintă schema de service a producătorului.

## 1. Aparatele și nivelul de confirmare

| Caracteristică | BW150 | BW600 |
|---|---|---|
| Versiune analizată | 1.1.0 | 2.0.5; există și analiză 2.0.3 |
| Serie cunoscută | 918719 | 968511 |
| Identificare USB | VID 0483, PID 5750 | VID 0483, PID 5750 |
| Controler firmware | JieLi AC632N, q32s | JieLi AC632N, q32s |
| Transport implementat | USB HID | USB HID |
| Modul Wi-Fi fizic | T1-2S/TL, identificat de utilizator | Model fizic neconfirmat |

În acest document, «implementat» înseamnă prezent în cod, «verificat USB» înseamnă că există observații de comunicație, iar «neconfirmat» înseamnă că lipsește proba necesară. Recitirea unei setări nu echivalează cu verificarea comportamentului electric sub sarcină.

## 2. Cum funcționează testarea

Sarcina electronică absoarbe curent din sursa sau bateria conectată și transformă energia în căldură. Controlerul reglează sarcina în funcție de mod și măsoară tensiunea, curentul și temperaturile. Aplicația citește rezultatele și transmite setări; reglajul efectiv se face în aparat.

| Funcție | Principiu și utilizare |
|---|---|
| CC | Curent constant, de exemplu descărcare la 1 A până la pragul de tensiune. |
| CV | Menține tensiunea impusă prin absorbția curentului. Se folosește cu surse adecvate, nu ca test obișnuit de capacitate a bateriei. |
| CR | Rezistență constantă: curentul urmărește aproximativ I = U/R. |
| CP | Putere constantă: curentul urmărește aproximativ I = P/U; crește când tensiunea scade. |
| BRT | Test de rezistență internă a bateriei; formula, secvența exactă și câmpul rezultatului nu sunt încă decodificate complet. |
| PT | Test de sursă/încărcător; selecția este disponibilă, secvența internă nu este documentată complet. |
| CT | Test de cablu; selecția este disponibilă, rezultatele specifice nu sunt încă decodificate complet. |
| CDC | Încărcare → descărcare → încărcare, cu modul extern de control al încărcării. |
| CDCDC | Secvență de încărcare/descărcare în cinci etape, cu modul extern. |
| CDxN | Cicluri repetate, cu modul extern; BW150 expune numărul ciclurilor. |
| BCT | Funcție de capacitate observată în meniul BW600. Aplicația configurează un profil CC; echivalența completă cu BCT nativ nu este confirmată. |
| BAT | Selectarea memoriei de măsurători BW600; nu este un mod electric. |

Capacitatea reprezintă integrala curentului în timp, iar energia integrala puterii. Contoarele citite aparțin aparatului și pot include o măsurătoare anterioară dacă nu au fost resetate.

## 3. Test de baterie în aplicație

1. Selectează aparatul și identifică bateria: chimie, serie, capacitate nominală și praguri permise.
2. Cu sarcina oprită, alege CC sau profilul BCT pentru BW600. Introdu curentul și tensiunea de oprire potrivite bateriei.
3. Dacă dorești o măsurătoare nouă, resetează contoarele aparatului prin acțiunea dedicată; resetarea elimină statisticile existente.
4. Verifică valorile recitite, apoi pornește sarcina. Urmărește tensiunea, curentul, puterea, capacitatea, energia și temperaturile.
5. La oprire, exportă CSV și certificatul prin butonul PDF. Browserul folosește dialogul de tipărire/salvare PDF.

Limitele din aplicație sunt limite software, nu o garanție că toate combinațiile de tensiune, curent și putere sunt admise de aparat. Consultă specificația unității pentru domeniul electric efectiv.

## 4. Protocolul USB HID

Toate numerele de comandă și offseturile notate cu `0x` sunt hexazecimale. Offseturile din tabelele de payload sunt zecimale, calculate după eliminarea antetului de 4 octeți.

Scrierea folosește 65 octeți: report ID zero + raport HID de 64 octeți:

```text
00 | 55 05 TYPE SUB | DATA... | EE FF | completare cu zero
```

În configurația folosită TYPE = 01. Răspunsul acceptat este:

```text
AA 05 01 SUB | PAYLOAD...
```

Codul elimină un eventual report ID zero primit și extrage octeții 4..61. Parserul cere minimum 51 octeți de payload. Constructorul nu calculează checksum pentru aceste comenzi HID. Nu trebuie confundat acest format cu protocolul serial al modulului Wi-Fi.

La deschidere, serviciul trimite subcomanda 04 cu date `00 00 00 00` pentru TYPE 1..10. Este secvența de inițializare existentă, nu o dovadă că toate tipurile reprezintă modele identificate.

Citirea periodică execută 05 pentru măsurători și 03 pentru configurație. Intervalul nominal este o secundă, la care se adaugă timpul de comunicație. Fiecare cerere are termen de răspuns de aproximativ 800 ms.

## 5. Tabela comenzilor — echivalentul registrelor de control

Aceste aparate folosesc subcomenzi, nu o hartă Modbus identificată. «Registru» înseamnă aici câmp sau comandă a protocolului proprietar.

| Comandă | Funcție | Date |
|---|---|---|
| 03 | Citire configurație | cerere implicită `0B 00 8C` în implementare |
| 04 | Inițializare | patru octeți zero |
| 05 | Citire măsurători | cerere implicită `0B 00 8C` |
| 21 | Setpoint al modului | float32 big-endian |
| 22 | Luminozitate | `00 00 00 nivel` |
| 23 | Luminozitate în repaus | `00 00 00 nivel` |
| 24 | Întârziere repaus, secunde | `00 00 00 secunde` |
| 25 | Start/Stop sarcină | `01 00 00 00` / `00 00 00 00` |
| 29 | Tensiune oprire descărcare | float32 big-endian |
| 2A | Prag tensiune maximă | float32 big-endian |
| 2C | Alarmă curent | float32 big-endian |
| 2D | Alarmă putere | float32 big-endian |
| 2E | Alarmă temperatură externă | float32 big-endian |
| 2F | Alarmă temperatură MOSFET | float32 big-endian |
| 31 BW150 / 32 BW600 | Timer | `ore 00 00 01`, apoi `minute 00 00 02` |
| 34 BW150 / 35 BW600 | Reset măsurători | patru octeți zero |
| 35 BW150 | Număr cicluri | `număr 00 00 00` |
| 36 BW600 | Selectare BAT | `număr 00 00 00` |

Diferența comenzii 35 este esențială: pe BW150 configurează ciclurile, pe BW600 resetează măsurătorile. Nu se reutilizează comenzile între modele fără profilul corect.

| Mod | Comandă | ID raportat |
|---|---|---|
| CC | 47 | 0 |
| CV | 48 | 1 |
| CR | 49 | 2 |
| CP | 4A | 3 |
| BRT | 4B | 4 |
| PT | 4C | 5 |
| CT | 4D | 6 |
| CDC | 4E | 7 |
| CDCDC | 4F | 8 |
| CDxN | 50 | 9 |

Selecția trimite patru octeți zero. Pe BW150 există jurnal de verificare a tuturor celor zece moduri, fără pornire. Pentru BW600 s-a corectat deplasarea greșită cu +1 pe baza observațiilor display-ului. ID-urile suplimentare BW600 11/12 sunt asociate ecranelor statistici/BAT în notele de analiză; nu sunt tratate ca moduri pornibile.

## 6. Payload 03 — configurație, comun în parserul actual

| Offset | Lungime | Format | Conținut |
|---|---|---|---|
| 0 | 4 | float32 BE | setpoint |
| 4..15 | 12 | nedecodificat aici | câmpuri neexpuse |
| 16 | 4 | float32 BE | cutoff |
| 20 | 4 | float32 BE | prag tensiune maximă |
| 24 | 4 | neconfirmat | neexpus |
| 28 | 4 | float32 BE | alarmă curent |
| 32 | 4 | float32 BE | alarmă putere |
| 36 | 4 | float32 BE | alarmă temperatură externă |
| 40 | 4 | float32 BE | alarmă MOSFET |
| 44 | 1 | uint8 | ID mod |
| 45 | 1 | neconfirmat | neexpus |
| 46 | 1 | uint8 | luminozitate |
| 47 | 1 | uint8 | luminozitate repaus |
| 48 | 1 | uint8 | întârziere repaus |
| 49 | 1 | uint8 | ore timer |
| 50 | 1 | uint8 | minute timer |

## 7. Payload 05 — măsurători, diferențe între modele

U32LE înseamnă întreg fără semn pe 32 biți, little-endian. Divizorii sunt cei din parserul aplicației, nu validări metrologice independente.

| Offset | BW150 | BW600 2.0.5 |
|---|---|---|
| 0..3 | neexpus | neexpus |
| 4 | U32LE /1000, V | U32LE /1000, V |
| 8 | U32LE /1000, A | U32LE /1000, A |
| 12 | neexpus; puterea calculată U×I | U32LE /1000, W |
| 16 | neexpus | U32LE /1000, Wh |
| 20 | U32LE /1000, Wh | U32LE /1000, capacitate afișată mAh |
| 24 | U32LE /1000, capacitate afișată mAh | contor brut U32LE |
| 28 | contor brut U32LE | U32LE /1000, temperatură externă °C |
| 32 | U32LE /1000, température externă °C | U32LE /1000, température MOSFET °C |
| 36 | U32LE /1000, température MOSFET °C | U32LE /1000, température auxiliaire, semnificație neconfirmată |
| 40 | floor(U32LE /1000), ventilator RPM | idem |
| 44 | neexpus | stare sarcină, 1 = activă |
| 48 | stare sarcină, 1 = activă | neexpus |
| 49 | număr cicluri uint8 | neexpus |
| 50 | index ciclu uint8 | neexpus |

Scara capacității și a energiei trebuie verificată printr-un test de durată cunoscută, comparând display-ul și instrumentul etalon. Valorile neobișnuite nu trebuie transformate automat în rezultate de certificat. `rawCounter28` este doar numele intern din cod; pe BW600 provine din offset 24. Timpul acumulat al aparatului rămâne `null`, fiindcă interpretarea veche nu a fost justificată.

## 8. Exemple de codificare

```js
const {packet}=require('./bw150');
// Selectare CC; nu pornește sarcina:
const selectCC=packet(0x47, Buffer.alloc(4));
// Setpoint 1 A în CC: float32 BE = 3F 80 00 00.
const oneAmp=packet(0x21, Buffer.from([0x3f,0x80,0,0]));
// Cutoff 3 V: float32 BE = 40 40 00 00.
const cutoff=packet(0x29, Buffer.from([0x40,0x40,0,0]));
// Oprire:
const stop=packet(0x25, Buffer.alloc(4));
```

Exemplele construiesc doar pachete; nu deschid aparatul. Confirmarea se face prin recitirea 03/05, nu presupunând că o scriere HID reușită înseamnă comandă executată.

## 9. Limitele setărilor din aplicație

| Parametru | BW150 | BW600 |
|---|---|---|
| CC / curent cicluri | 0,01..25 A | 0,01..50 A |
| CP | 0,01..150 W | 0,01..600 W |
| CV | 1..200 V | 1..200 V |
| CR | 0,1..10000 Ω, limită locală | idem |
| Cutoff / prag tensiune | 0..200 V | 0..200 V |
| Alarmă curent | 0,01..25 A | 0,01..60 A |
| Alarmă putere | 1..150 W | 1..650 W |
| Alarmă externă | 1..100 °C | 1..100 °C |
| Alarmă MOSFET | 1..100 °C | 1..150 °C |
| Luminozitate | 1..9 | 1..9 |
| Repaus | 10..255 s | 10..255 s |
| Timer | 0..99 h și 0..59 min | idem |
| Cicluri / BAT | cicluri 1..99 | BAT 1..99 |

## 10. BCT și BAT: ce știm efectiv

BCT nativ este prezent în meniul BW600 conform observației utilizatorului. Comenzile candidate 51 și 08 nu au schimbat modul raportat la probele făcute. Implementarea actuală selectează CC, scrie curentul prin 21, empty prin 29 și full prin 2A. Recitirea confirmă aceste câmpuri. Nu este demonstrat că 2A are toate efectele parametrului «full charged» din BCT nativ.

BAT este trimis prin 36. Aplicația reține local numărul selectat, fără o decodificare independentă a slotului în răspuns. Resetarea și selectarea BAT nu au avut un test de integrare documentat asupra statisticilor existente. Interfața nu trebuie prezentată ca implementare complet validată a întregului meniu BW600.

## 11. Wi-Fi, UART și înlocuirea modulului

Configurația `isd_config.ini` include UTTX=PA05, UTRX=PP00 și RESET=PB01_08_0. Acestea sunt denumiri din configurația firmware; nu dovedesc singure conexiunea la modulul Wi-Fi. Pot reprezenta și interfețe de boot/debug. Este necesară urmărirea traseelor și capturarea semnalelor pentru identificarea UART-ului de aplicație.

Pentru BW600, nota existentă indică UTBD=0x00420F40. Octeții BW150 observați sunt diferiți (`40 42 0F 00`); nu presupunem același baud rate pentru ambele. Baud rate-ul serial de aplicație nu a fost măsurat.

Pinout-ul T1-2S furnizat de utilizator: 1=3V3, 3=GND, 5=RX1/P10, 7=TX1/P11, 10=CEN. Pe placa gazdă, padul fostului RX al modulului primește TX de la controler; aici se conectează RX-ul ESP. Padul fostului TX al modulului merge către RX-ul controlerului; aici se conectează TX-ul ESP. Numerotarea trebuie verificată pe orientarea fizică a modulului.

Nu există încă o captură UART în proiect care să confirme framing-ul, baud rate-ul sau comenzile. Formatul HID nu se transmite automat pe UART. Capacitatea sursei 3,3 V a plăcii pentru un ESP nu a fost măsurată. Înaintea conectării active trebuie verificate aceste elemente.

Proiectul public https://github.com/1RandomDev/atorch-bw150-esphome este o pistă externă pentru protocolul serial și conversie locală; constatările sale nu reprezintă teste executate pe unitățile noastre. Funcționarea locală cu ESP nu este implementată în aplicația actuală.

## 12. Structura aplicației și API local

`bw150.js` construiește pachetele, definește profilurile și decodează răspunsurile. `server-multi.js` gestionează HID și servește interfața. `public/app.js` afișează valorile, graficele și exporturile. `Start-Atorch.cmd` pornește serviciul pe http://127.0.0.1:8787.

| Rută | Metodă | Rol |
|---|---|---|
| /api/status | GET | identitate, conexiune, sample și profil |
| /api/capabilities | GET | moduri și parametri disponibili |
| /api/device | POST | selectare aparat, `{serial}` |
| /api/mode | POST | `{mode}` |
| /api/settings | POST | `{mode,value,cutoff}` |
| /api/parameter | POST | `{name,value}` |
| /api/timer | POST | `{hours,minutes}` |
| /api/power | POST | `{on:true/false}` |
| /api/battery | POST | `{slot}`, numai BW600 |
| /api/bct | POST | `{fullVoltage,emptyVoltage,current}`, BW600 |
| /api/reset-measurements | POST | `{confirm:"RESET seria"}` |
| /api/network | GET | ultimul rezultat al descoperirii rețelei |

POST cere un Origin identic cu adresa serviciului. Comenzile USB sunt serializate într-o coadă. Configurarea este blocată cât timp sarcina este activă; Start/Stop este permis separat. Cele mai multe setări sunt recitite cu până la patru încercări. BAT și reset au o verificare mai slabă: o citire reușită, fără confirmarea semantică a efectului.

## 13. Grafice și certificate — limite actuale

Graficele live și PDF folosesc cele șase câmpuri principale. Temperatura externă și temperatura auxiliară BW600 nu sunt incluse în lista de grafice actuală. Istoricul este în memoria browserului, limitat la ultimele 30 minute și se pierde la reîncărcare sau schimbarea aparatului.

Certificatul este generat manual prin tipărire în PDF, nu automat la sfârșitul unui test. El folosește istoricul disponibil, care poate include repausul sau mai multe teste. Nu există încă delimitare persistentă start/stop, arhivă de teste, identificator unic verificat sau verdict automat de conformitate. Datele bateriei sunt cerute la export. Pentru un certificat complet al unui test lung trebuie implementată înregistrarea persistentă a întregii sesiuni.

## 14. Firmware și reproducerea analizei

| Element | BW150 1.1.0 | BW600 2.0.5 |
|---|---|---|
| SHA-256 imagine | 009e6b5c344c26e8d4949293248241fa65d9d053f4577ef17e38569fe8ae99ad | 9b2f048759d558fd5d83d4a783d2add3f7af2af6edb3a9aca8fb5d86af5767a2 |
| Entry point | 0x01E00120 | 0x01E00120 |
| Dispatcher USB | 0x01E014B6 | 0x01E01798 |
| Tabelă subcomenzi | 0x01E01506 | 0x01E017EC |

Imaginile originale nu au fost rescrise în aparate în cadrul analizei. Extragerea JLFS este în `vendor/*-unpacked`. Dezasamblarea q32s folosește o descriere incompletă; nu orice cuvânt decodat constituie instrucțiune validată.

Surse locale de urmărit:

- `analysis/PROTOCOL.md`: analiza inițială BW150 și handler-ele modurilor.
- `analysis/BW600-PROTOCOL.md`: diferențe BW600.
- `analysis/hardware-mode-verification.json`: jurnalul selecțiilor BW150.
- `analysis/*disassembly.txt`: dezasamblări și dispatcher BW600.
- `test-bw150.js`: verificări software pentru parser și codificare.
- `probe-bct.js`: proba comenzilor candidate BCT; nu se rulează pentru simpla citire a documentației.

Verificarea software se face cu `npm run check` și `npm test`. Scripturile de probe pot schimba modul aparatului și trebuie citite înainte de executare.

## 15. Ce trebuie încă decodificat sau validat

UART-ul fizic, baud rate-ul și protocolul serial; BCT nativ și sensul exact al tensiunii full; BAT recitit și persistența statisticilor; unitățile contoarelor printr-un test controlat; rezistența internă și rezultatele PT/CT; timpul acumulat; câmpurile neexpuse; calibrarea, limba și comenzile de service. Nu există în proiect o schemă electronică completă BW150/BW600 sau un PCB ESP finalizat.
