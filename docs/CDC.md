# CDC nativ BW600

Pagina `/cdc.html` configurează CDC (ID 7) și monitorizează încărcare → descărcare → încărcare. Disponibil momentan pe profilul `bw600`, nu `bw600-doc` sau BW150 nevalidat.

Setări: curent de descărcare 21, prag descărcare 29, tensiune full 2A, curent de terminare 2B. Toate sunt recitite înainte de Start. Curentul de încărcare este măsurat; nu este reglat prin 2B. Încărcătorul extern se reglează separat. Pauzele rămân cele configurate pe aparat.

Opțiunea implicită trimite două comenzi Start la o secundă distanță: secvența a funcționat pe BW600 2.0.5 cu dialogul de continuare/reset. Nu reprezintă o comandă OK universală; nu șterge explicit contoarele. RUN singur nu este suficient: monitorul așteaptă curentul, cu timeout de 30 s.

Etapele sunt observate prin RUN, curent și sign_flags bit 7. Curent sub 20 mA este clasificat ca așteptare, nu încărcare. Încărcarea cu bit zero este o interpretare experimentală a probelor noastre. Schimbarea fazei nu se comandă din PC.

Se salvează JSON în `data/cdc/<id>.json`, periodic la 3 s și la final. Ah/Wh se integrează separat pentru fiecare etapă, prin trapeze; intervalele peste 2 s se exclud și se numără ca întreruperi. Fereastra API live include ultimele 2000 de puncte, dar fișierul și exportul CSV conțin întreaga sesiune. Datele sunt păstrate în memorie și salvate periodic; o cădere bruscă a PC-ului poate pierde ultimele secunde și nu reia automat testul.

Stop anulează al doilea Start dacă acesta este încă în așteptare, trimite oprirea și cere RUN=0 plus curent sub 20 mA. Lipsa datelor peste 5 s, lipsa curentului după pornire sau tensiunea peste full+20 mV declanșează oprire și rezultat de eroare. Oprirea la pragul full se bazează în primul rând pe firmware-ul aparatului; PC-ul nu este o protecție independentă garantată.

Un test este «finished» numai dacă s-au observat etapele charge/discharge/charge și tensiunea a ajuns în apropierea pragului full. Altfel oprirea aparatului este marcată «incomplete». Raportul poate fi tipărit/salvat PDF din browser și include etapele și curbele; nu este certificat de calibrare și nu declară automat bateria conformă.

API: GET `/api/cdc/status`, `/api/cdc/history`, `/api/cdc/test?id=...`; POST `/api/cdc/start` și `/api/cdc/stop`. Parametri Start: `battery`, `current`, `empty_v`, `full_v`, `end_current`, `double_start`.

Simulatorul modelează secvența pentru verificarea programului, nu terminarea electrochimică sau temporizările reale. Validare hardware efectuată anterior: selectare CDC, praguri, Start dublu, măsurare curent și Stop. Pagina integrată trebuie verificată separat pe hardware înainte de utilizare nesupravegheată.
