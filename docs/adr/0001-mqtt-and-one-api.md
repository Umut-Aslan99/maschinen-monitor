# 0001 · MQTT zwischen Maschinen und Auswertung, ein API-Container für alles Weitere

**Status:** angenommen

## Kontext
Echte Maschinen sprechen OPC UA, Modbus oder proprietäre Protokolle; ein Edge-Gateway übersetzt meist nach MQTT.
Der Monitor soll so gebaut sein, dass ein echtes Gateway den Simulator ersetzen könnte.

## Entscheidung
- Der Simulator veröffentlicht wie ein Gateway auf `demo-werk/halle-1/<maschine>/<art>` (ISA-95-artiger Namensraum):
  `telemetry` (QoS 0, alle 2 s), `state` (QoS 1, retained – wer sich neu verbindet, kennt sofort den Zustand),
  `part`, `alarm` (QoS 1) und als Gegenrichtung `cmd`.
- Mosquitto ist nur im internen Docker-Netz erreichbar, ohne anonyme Clients; Simulator und Backend haben eigene
  Passwörter, die ACL erlaubt jedem nur seine Themen (das Backend darf keine Messwerte fälschen, der Simulator keine
  Befehle senden).
- FastAPI liefert REST, WebSocket und den Vue-Build aus einem Container (wie bei Lager-Scan und ERP-Cockpit):
  ein Origin, kein CORS. Simulator und API nutzen dasselbe Image mit unterschiedlichem Startbefehl.

## Konsequenzen
+ Austauschbarer Datenlieferant, klare Rechte, wenig Infrastruktur (Broker ~5 MB RAM).
− QoS 1 heißt „mindestens einmal“ – das Backend muss Duplikate verkraften (siehe 0002).
