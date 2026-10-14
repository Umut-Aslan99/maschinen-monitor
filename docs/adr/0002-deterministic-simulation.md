# 0002 · Deterministische Simulation, idempotentes Speichern, Lücken auffüllen

**Status:** angenommen

## Kontext
Die Demo soll bei Nichtbenutzung schlafen dürfen (Arbeitsspeicher des Servers) und trotzdem jederzeit eine
glaubwürdige Historie der letzten Tage zeigen. Außerdem stellt MQTT mit QoS 1 Nachrichten gelegentlich doppelt zu.

## Entscheidung
- Das Verhalten jeder Maschine ist eine **Funktion der Zeit**: Die Abfolge aus Lauf, Störung, Rüsten und Pause einer
  Schicht kommt aus einem Zufallsgenerator mit dem Startwert (Maschine, Schichtbeginn); Messwerte und Teile werden daraus
  berechnet. Derselbe Zeitpunkt liefert immer dieselben Daten.
- Beim Start füllt das Backend fehlende Zeiträume aus demselben Modell auf (letzte 24 h alle 10 s, davor minütlich).
  Die Lücke wird bis zum **Startzeitpunkt** gemessen – Live-Daten, die währenddessen eintreffen, dürfen die Lücke nicht
  als geschlossen erscheinen lassen (ein Test sichert genau das ab). Die Berechnung läuft in einem Thread, damit der
  Live-Empfang weiterläuft.
- Alle Tabellen haben eindeutige Schlüssel (Maschine + Zeit); Einfügen mit `ON CONFLICT DO NOTHING`. Doppelte
  Zustellung, Überlappung von Live- und Fülldaten und erneutes Füllen sind dadurch harmlos.
- Von Besuchern ausgelöste Störungen überlagern den Plan für drei Minuten; danach läuft der Plan weiter.

## In einer echten Anlage
Würde das Edge-Gateway puffern und nachsenden (Store and Forward). Die Idempotenz des Backends bleibt gleich wichtig.

## Konsequenzen
+ Historie ist nach jedem Aufwachen vollständig; Tests können das Modell gegen die Datenbank prüfen
  (OEE aus der Datenbank = OEE aus dem Modell).
− Während einer Ruhephase ausgelöste Störungen gibt es nicht – es war ja niemand da.
