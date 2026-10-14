# 0005 · Live-Updates per WebSocket, eine Berechnung für alle Clients

**Status:** angenommen

## Kontext
Viele Clients schauen auf dieselben Daten; Messwerte kommen alle 2 Sekunden je Maschine, Zustände und Alarme sofort.

## Entscheidung
- Ein WebSocket `/api/live`. Beim Verbinden ein Schnappschuss (`hello`), danach Ereignisse: `telemetry`, `state`,
  `alarm`, `classified` und alle 5 Sekunden eine frisch berechnete Hallenübersicht – **einmal** berechnet, an alle
  gesendet, und nur, wenn jemand verbunden ist.
- Jeder Client hat eine begrenzte Warteschlange (500 Nachrichten); ein langsamer Client verliert alte Nachrichten,
  statt die anderen aufzuhalten.
- Das Frontend verbindet sich mit wachsender Wartezeit neu und lädt bei Zustands-/Alarmereignissen gezielt nach.

## Abgrenzung zu Lager-Scan (angular.umut-aslan.dev)
Dort reichen Server-Sent Events: wenige, seltene Ereignisse pro Lager. Hier ist der Datenstrom dichter und bewusst
als WebSocket umgesetzt; SSE wäre ebenfalls möglich gewesen – die Entscheidung ist austauschbar, weil das Frontend nur
den Live-Store kennt.

## Konsequenzen
+ Konstante Last unabhängig von der Zahl der Zuschauer.
− Bei mehreren API-Instanzen bräuchte es einen Verteiler (z. B. MQTT selbst oder PostgreSQL `LISTEN/NOTIFY`).
