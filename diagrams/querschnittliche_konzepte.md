## 8. Querschnittliche Konzepte

Dieses Kapitel beschreibt Konzepte, die nicht nur einen einzelnen Baustein
betreffen, sondern über mehrere Teile des Systems hinweg gelten.

### 8.1 Konfiguration

Die Anwendung wird über die Datei `config.ini` im Projektverzeichnis
konfiguriert. Beim Start liest `puzzle_orchestrator.config` diese Datei ein und
wandelt die Werte in typisierte Konfigurationsobjekte um.

Über die Konfiguration werden insbesondere folgende Aspekte gesteuert:

- Logging-Level
- Kamera-Transport (`gopro` oder `mock`)
- Pfad zum Mock-Bild
- Microcontroller-Transport (`uart` oder `stub`)
- UART-Port, Baudrate und Timeouts
- Solver-Algorithmus
- Segmentierungsparameter wie Mindestfläche und Threshold
- Skalierung und Offsets für die Koordinatentransformation

Damit können Entwicklungs-, Test- und Zielbetrieb ohne Codeänderungen
umgeschaltet werden.

### 8.2 Ports und Adapter

Das System trennt fachliche Ablaufsteuerung von konkreten technischen
Implementierungen. Der `PuzzleOrchestrator` verwendet nur die Schnittstellen aus
`puzzle_models.ports`:

- `CameraPort`
- `PuzzleSolverPort`
- `CoordinateMapperPort`
- `MicrocontrollerPort`

Konkrete Adapter werden erst beim Programmstart erzeugt. Beispiele sind
`CameraController` für die GoPro, `MockCameraController` für lokale Bilder,
`UartMicrocontrollerInterface` für UART und `MicrocontrollerInterface` als Stub.

Dieses Konzept reduziert Kopplung und erlaubt Tests ohne reale Hardware.

### 8.3 Gemeinsame Datenmodelle

Die Bausteine tauschen keine implementierungsspezifischen Objekte aus, sondern
gemeinsame Datenmodelle aus `puzzle_models.placements`:

- `SolverPlacement` beschreibt die vom Solver berechnete Position eines
  Puzzleteils.
- `MachinePlacement` beschreibt dieselbe Bewegung nach der Transformation in
  Maschinenkoordinaten.

Beide Modelle enthalten `piece_id`, `start`, `end` und `rotation`. Dadurch ist
die Schnittstelle zwischen Solver, Coordinate Mapper und Microcontroller klar
und stabil.

### 8.4 Bildverarbeitung

Die Bildverarbeitung basiert auf OpenCV. Im Zielbetrieb wird zuerst ein Bild von
der GoPro aufgenommen und lokal gespeichert. Danach wird das Bild über
ArUco-Marker perspektivisch entzerrt.

Für die Puzzle-Erkennung werden folgende Verarbeitungsschritte genutzt:

- Kontrastverbesserung und Glättung
- Grauwert-Thresholding
- Morphologische Operationen
- Konturerkennung
- Filterung nach Mindestfläche
- Speicherung einzelner Teile als Masken

Die Segmentierung ist über `min_area` und `threshold` konfigurierbar, damit sie
an unterschiedliche Lichtverhältnisse und Bildaufnahmen angepasst werden kann.

### 8.5 Geometrische Modellierung

Erkannte Puzzleteile werden als Polygone modelliert. Aus den Konturen werden
Eckpunkte extrahiert, vereinfacht und in `PuzzlePiece`-Objekte überführt.

Für geometrische Berechnungen werden zwei Ebenen verwendet:

- eigene einfache Modelle wie `Point`, `Edge`, `OuterEdge`, `Polygon` und
  `PuzzlePiece`
- Shapely für robuste Polygonoperationen wie Flächen- und
  Überlappungsberechnungen

Außenkanten werden aus den Polygonen abgeleitet. Der Solver verwendet diese
Information, um mögliche Ausrichtungen und Anordnungen der Teile zu bewerten.

### 8.6 Koordinatentransformation

Der Solver arbeitet in Bild- beziehungsweise Solver-Koordinaten. Vor der
Ausgabe an die Maschine werden diese Koordinaten durch den `CoordinateMapper` in
Maschinenkoordinaten umgerechnet.

Die Transformation verwendet getrennte Offsets für Start- und Zielpositionen
sowie gemeinsame Skalierungsfaktoren:

```text
machine_x = x_min + solver_x * scale_x
machine_y = y_min + solver_y * scale_y
```

Die Parameter werden über `config.ini` gesetzt. Dadurch kann das System an die
tatsächliche Mechanik und deren Koordinatenraum angepasst werden.

### 8.7 Hardwarekommunikation

Die Kommunikation mit dem Microcontroller ist als austauschbarer Adapter
gekapselt. Im Zielbetrieb wird UART verwendet, im Testbetrieb ein Stub.

Im UART-Betrieb gilt ein einfaches Handshake-Konzept:

- Jeder gesendete Befehl muss mit `ACK` bestätigt werden.
- Danach wartet die Anwendung auf `DONE`, bevor der nächste Befehl gesendet wird.
- `ERROR` oder ungültige Kommandos brechen den aktuellen Ablauf ab.

Für jedes Puzzleteil wird eine Pick-and-Place-Sequenz ausgeführt:

1. zur Startposition fahren
2. Greifer senken
3. Teil halten
4. Greifer heben
5. zur Zielposition fahren
6. Greifer senken
7. Teil loslassen
8. Greifer heben

### 8.8 Logging und Nachvollziehbarkeit

Die Anwendung verwendet das Python-Logging-Modul. Das Logging-Level ist
konfigurierbar. Zentrale Verarbeitungsschritte werden protokolliert, zum Beispiel
Bildaufnahme, Anzahl erkannter Puzzleteile, Solver-Ergebnis,
Koordinatentransformation und UART-Kommunikation.

Zusätzlich erzeugt der Solver Debug-Artefakte im Output-Verzeichnis:

- extrahierte Masken der Puzzleteile
- erkannte Eckpunkte
- JSON-Dateien mit Kontur- und Eckpunktinformationen
- Debug-Bilder des gelösten Layouts

Diese Artefakte unterstützen Fehlersuche und Kalibrierung.

### 8.9 Fehlerbehandlung

Fehler werden überwiegend durch Exceptions signalisiert. Der Einstiegspunkt
protokolliert fehlgeschlagene Durchläufe und reicht die Exception weiter.

Typische geprüfte Fehlerbedingungen sind:

- fehlende Konfigurationsdatei
- ungültige Konfigurationswerte
- nicht lesbare Bilddateien
- fehlende ArUco-Marker
- unerwartete Anzahl erkannter Puzzleteile
- fehlgeschlagene Solver-Suche
- UART-Timeouts
- Fehler- oder Invalid-Signale des Microcontrollers

Das System bevorzugt damit einen kontrollierten Abbruch gegenüber einer
unsicheren Weiterfahrt der Mechanik.

### 8.10 Betriebsmodi

Das System unterstützt zwei grundlegende Betriebsarten:

| Betriebsart | Kamera | Microcontroller | Zweck |
| --- | --- | --- | --- |
| Zielbetrieb | GoPro | UART | Ausführung auf dem Raspberry Pi mit realer Hardware. |
| Entwicklungsbetrieb | Mock-Bild | Stub | Entwicklung und Fehlersuche ohne Kamera und Microcontroller. |

Die Umschaltung erfolgt ausschließlich über `config.ini`.

### 8.11 Abhängigkeiten

Die wichtigsten externen Abhängigkeiten sind:

- OpenCV für Bildverarbeitung und ArUco-Erkennung
- Shapely für geometrische Operationen
- pyserial für UART-Kommunikation im Zielbetrieb

Die Projektmetadaten liegen in `pyproject.toml`. Hardwareabhängige Pakete müssen
auf dem Raspberry Pi passend zur Zielumgebung installiert werden.
