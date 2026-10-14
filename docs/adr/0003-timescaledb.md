# 0003 · TimescaleDB für Zeitreihen

**Status:** angenommen

## Kontext
Rund 9 Messwerte pro Sekunde, Abfragen über 15 Minuten bis 7 Tage, dazu relationale Daten (Zustände, Alarme,
Zuordnungen). Ein Betrieb hat meist schon PostgreSQL-Wissen.

## Entscheidung
TimescaleDB (eine PostgreSQL-Erweiterung) statt einer separaten Zeitreihendatenbank:
- `telemetry` im Langformat (Maschine, Signal, Zeit, Wert) als Hypertable mit Tages-Chunks; Kompression nach 2 Tagen
  (segmentiert nach Maschine und Signal), Löschung nach 14 Tagen.
- `telemetry_1m` als Continuous Aggregate (Mittel, Minimum, Maximum je Minute), auch für die noch nicht
  materialisierten letzten Minuten (`materialized_only = false`). Diagramme über 8 h/24 h/7 Tage lesen daraus und
  zeigen den Mittelwert mit der Spanne.
- Zustände, Teile und Alarme sind normale bzw. Hypertables in derselben Datenbank – OEE und Pareto sind SQL plus
  reine Python-Funktionen.
- Migrationen als nummerierte SQL-Dateien, einmal ausgeführt (wie Flyway), mit Advisory Lock gegen parallele Starts.

## Konsequenzen
+ Eine Datenbank, SQL für alles, Joins zwischen Messwerten und Stammdaten.
− Kompression und Continuous Aggregates sind Funktionen der Timescale-Lizenz (für Selbstbetrieb frei).
