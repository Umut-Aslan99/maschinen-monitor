// Guided tour of the Maschinen-Monitor – texts here, mechanics in site-tour.js (shared by all demos of umut-aslan.dev).
import { startTours } from '/site-tour.js';

startTours([{
  id: 'monitor',
  steps: [
    {
      title: 'Hallo! Kurz zum Problem',
      mood: 'worried',
      text: `In vielen Fertigungshallen fällt ein Stillstand erst auf, **wenn jemand vorbeiläuft**.
Warum die Maschine stand, weiß später keiner mehr genau.

Die Kennzahlen kommen als Excel-Auswertung **am Monatsende** – zu spät, um noch zu reagieren.`,
      nextLabel: 'Zeig mir die Lösung',
    },
    {
      path: '/',
      target: '[data-tour="hall-kpis"]',
      title: 'Die ganze Halle auf einen Blick',
      text: `Die **OEE** der laufenden Schicht: Wie viel der geplanten Zeit wurden wirklich gute Teile produziert?
Daneben: Maschinen in Produktion, offene Alarme und Stillstände ohne Grund.

Alles live – nicht am Monatsende.`,
    },
    {
      target: '[data-tour="machines"]',
      title: 'Jede Karte ist eine Maschine',
      text: `Sechs simulierte Maschinen senden alle 2 Sekunden Messwerte per **MQTT**, wie echte Steuerungen.

- **Zustand** mit Grund und Dauer – Farbe, Symbol und Text
- **OEE** mit Verfügbarkeit, Leistung und Qualität
- der wichtigste **Messwert** der letzten 30 Minuten`,
    },
    {
      target: '[data-tour="problem-machine"]',
      title: 'Das Sorgenkind',
      mood: 'curious',
      text: `Bei der Spritzgießmaschine wird das **Hydrauliköl regelmäßig zu heiß**.
Der Monitor warnt, sobald der Grenzwert überschritten ist – meist **Minuten bevor** die Maschine ausfällt.`,
    },
    {
      path: '/maschine/SGM-01',
      target: '[data-tour="fault"]',
      interactive: true,
      title: 'Probieren Sie es selbst',
      text: `Lösen Sie hier eine **Störung** aus: Sie erscheint sofort – auf dieser Seite, in der Hallenübersicht und
bei allen anderen Besuchern, die gerade zuschauen (WebSocket).`,
    },
    {
      target: '[data-tour="signals"]',
      title: 'Messwerte mit Geschichte',
      text: `Live alle 2 Sekunden, Grenzwerte als Linien, darüber der Zustandsverlauf.

Für 8 Stunden, 24 Stunden oder 7 Tage liest das Dashboard aus vorberechneten Minutenwerten der **TimescaleDB** –
deshalb geht das auch bei Millionen Messwerten schnell.`,
    },
    {
      target: '[data-tour="losses"]',
      title: 'Wohin ist die Schichtzeit gegangen?',
      text: `Von der geplanten Zeit über Stillstände, langsamere Takte und Ausschuss bis zur **wertschöpfenden Zeit**.
So sieht man, wo sich Verbesserung lohnt.`,
    },
    {
      path: '/stillstaende',
      target: '[data-tour="pareto"]',
      title: 'Warum stehen die Maschinen?',
      text: `Stillstandszeit nach Grund, **größter Verlust zuerst** (Pareto). Filter für Schicht, 24 Stunden, 7 Tage und
einzelne Maschinen.`,
    },
    {
      target: '[data-tour="unclassified"]',
      title: 'Gründe statt Bauchgefühl',
      text: `Viele Stopps kann die Maschine nicht erklären. Der Bediener ordnet hier nachträglich einen **Grund** zu –
erst dann taugen die Zahlen für Entscheidungen.`,
    },
    {
      path: '/alarme',
      target: '[data-tour="alarms"]',
      title: 'Alarme – auch aufs Handy',
      text: `Alarme der Maschinen und der Grenzwertüberwachung. **Quittieren** zeigt allen: Jemand kümmert sich.

Kritische Alarme kommen auf Wunsch als **Push-Nachricht** aufs Handy.`,
    },
    {
      title: 'Warum das hilft',
      mood: 'celebrate',
      text: `- Stillstände fallen in **Sekunden** auf, nicht beim nächsten Rundgang
- **Gründe** statt Vermutungen – der Pareto zeigt, wo es sich lohnt
- **Frühwarnung**, bevor eine Maschine ausfällt

Gebaut mit Vue 3, Python FastAPI, MQTT und TimescaleDB, abgesichert durch 75 automatisierte Tests.
Über den runden Knopf unten links starten Sie diese Tour jederzeit neu.`,
      nextLabel: 'Selbst ausprobieren',
    },
  ],
}]);
