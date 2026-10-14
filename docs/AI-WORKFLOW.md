# Wie KI in diesem Projekt eingesetzt wurde

Gebaut mit einem KI-Coding-Agenten (Claude Code). Vorgegeben waren Problem (Stillstände und OEE erst am Monatsende),
Zielgruppe (Fertigung im Mittelstand), Stack (Vue 3 + Python FastAPI + MQTT + TimescaleDB) und Gestaltung
(wie umut-aslan.dev).

Arbeitsweise: Domäne zuerst und ohne Infrastruktur testbar (Schichtkalender, Simulation, OEE, Grenzwertregeln) →
Integrationstests gegen echte TimescaleDB und Mosquitto → Oberfläche → End-to-End-Tests → Auslieferung erst, wenn alles
grün ist. Diagrammfarben wurden mit einem Prüfskript gegen beide Hintergründe validiert, nicht nach Gefühl gewählt.

**Was Tests und Prüfungen gefunden haben:**
- **Lückenfüller füllte nur die erste Maschine:** Während er lief, kamen schon Live-Daten der anderen Maschinen an,
  und deren Lücke sah dadurch geschlossen aus. Gefunden beim ersten Start des kompletten Stacks; jetzt wird bis zum
  Startzeitpunkt gemessen, ein Regressionstest sichert das ab.
- **Deadlock beim Start:** Lückenfüller und Live-Empfang schrieben gleichzeitig dieselben jüngsten Zeilen; PostgreSQL
  brach den Lückenfüller ab, die Historie blieb leer – aber nur bei ungünstigem Timing. Gefunden, weil ein
  End-to-End-Test beim zweiten Deployment fehlschlug (das Deployment wurde dadurch automatisch gestoppt), bestätigt im
  Datenbank-Log. Lösung: keine gemeinsamen Zeilen mehr (30 s Abstand zur Live-Kante), Wiederholung bei Deadlock,
  und eigene Log-Ausgabe – der Fehler war vorher in der Konsole nicht zu sehen.
- **Schriften von der Sicherheitsrichtlinie blockiert:** Vite bettete kleine Schriftdateien als `data:`-URL ein, die
  CSP erlaubt nur Dateien vom eigenen Server. Gefunden über die Browserkonsole; der End-to-End-Test „keine
  CSP-Verletzung“ prüft das seitdem.
- **Diagramm-Test zu früh:** Der Test lief, bevor die Historie fertig war. Statt den Test zu verlängern, meldet
  `/api/health` jetzt, ob die Historie bereit ist, und die Oberfläche zeigt einen Hinweis.
- **Sorgenkind nicht eindeutig:** In der Wochenauswertung lag die Hydraulikstörung von SGM-01 nur knapp vor dem Rüsten –
  die Simulation wurde so angepasst, dass die Geschichte der Demo stabil erzählt wird.

Strenge Werkzeuge: `mypy --strict`, `ruff`, TypeScript strict mit `noUncheckedIndexedAccess`.
Jede Änderung wird gelesen und verstanden, bevor sie bleibt.
