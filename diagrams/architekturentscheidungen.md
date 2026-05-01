## 9. Architekturentscheidungen

Dieses Kapitel hält zentrale Architekturentscheidungen fest. Es beschreibt nicht
jede Implementierungsentscheidung, sondern Entscheidungen mit langfristiger
Auswirkung auf Struktur, Betrieb, Testbarkeit oder Erweiterbarkeit des Systems.

### 9.1 Raspberry Pi 4 Model B als Zielplattform

**Entscheidung:** Das Programm wird im Zielbetrieb auf einem Raspberry Pi 4
Model B ausgeführt.

**Begründung:** Der Raspberry Pi bietet genügend Rechenleistung für die
Bildverarbeitung und Puzzle-Lösung, kann Python-Anwendungen direkt ausführen und
stellt gleichzeitig die benötigten Schnittstellen für Kameraanbindung,
Dateisystemzugriff und UART-Kommunikation bereit.

**Konsequenzen:**

- Die Software muss unter Linux auf dem Raspberry Pi lauffähig sein.
- OpenCV, Shapely und pyserial müssen auf dem Raspberry Pi installiert werden.
- Die serielle Schnittstelle `/dev/serial0` muss aktiviert und berechtigt sein.
- Rechenintensive Solver-Verfahren müssen zur verfügbaren Leistung passen.

### 9.2 Python als Implementierungssprache

**Entscheidung:** Die zentrale Anwendung wird in Python implementiert.

**Begründung:** Python ermöglicht eine schnelle Entwicklung und bietet gute
Bibliotheken für Bildverarbeitung, Geometrie und Hardwarekommunikation.

**Konsequenzen:**

- OpenCV und Shapely können direkt genutzt werden.
- Die Anwendung bleibt gut test- und anpassbar.
- Für zeitkritische Motorsteuerung ist Python nicht zuständig; diese bleibt beim
  Microcontroller.

### 9.3 Ports-and-Adapters-Architektur

**Entscheidung:** Der `PuzzleOrchestrator` arbeitet gegen abstrakte Ports statt
gegen konkrete Hardwareimplementierungen.

**Begründung:** Kamera, Solver, Coordinate Mapper und Microcontroller haben klar
getrennte Verantwortungen. Durch Ports können reale Adapter und Testadapter
ausgetauscht werden, ohne den Orchestrator zu ändern.

**Konsequenzen:**

- Entwicklung ohne GoPro und Microcontroller ist möglich.
- Hardwaredetails bleiben in Adapterklassen gekapselt.
- Neue Adapter können ergänzt werden, solange sie die bestehenden Ports erfüllen.

### 9.4 Konfiguration über `config.ini`

**Entscheidung:** Betriebsparameter werden über eine zentrale `config.ini`
gesteuert.

**Begründung:** Hardware-, Solver- und Mappingparameter müssen im Projektverlauf
häufig angepasst werden. Eine externe Konfigurationsdatei vermeidet Codeänderungen
für solche Anpassungen.

**Konsequenzen:**

- Zielbetrieb und Entwicklungsbetrieb können über Konfiguration umgeschaltet
  werden.
- Falsche Konfigurationswerte führen früh zu klaren Fehlern.
- Die Datei muss auf dem Raspberry Pi passend zur realen Hardware gepflegt
  werden.

### 9.5 GoPro-Anbindung über HTTP

**Entscheidung:** Die GoPro wird über ihre HTTP-Schnittstellen angesprochen.

**Begründung:** Die Kamera kann damit ohne direkte USB- oder Treiberintegration
ausgelöst werden. Die Anwendung kann Fotos aufnehmen, Medienlisten abrufen und
das zuletzt aufgenommene Bild herunterladen.

**Konsequenzen:**

- Der Raspberry Pi muss die GoPro über das Netzwerk erreichen.
- Fehler wie Timeouts oder leere Medienlisten müssen behandelt werden.
- Die Bildaufnahme ist langsamer als ein direkter Kamerastream, dafür aber
  einfacher zu integrieren.

### 9.6 ArUco-basierte Perspektivkorrektur

**Entscheidung:** Das Kamerabild wird anhand von ArUco-Markern perspektivisch
entzerrt.

**Begründung:** Die Puzzle-Erkennung benötigt eine möglichst stabile Draufsicht
auf den Arbeitsbereich. ArUco-Marker liefern reproduzierbare Referenzpunkte für
die Transformation.

**Konsequenzen:**

- Der Arbeitsbereich muss mit den erwarteten Markern ausgestattet sein.
- Fehlende oder falsch erkannte Marker brechen den Verarbeitungslauf ab.
- Die nachgelagerte Segmentierung wird robuster gegenüber Kameraperspektive.

### 9.7 OpenCV und Shapely für Bild- und Geometrieverarbeitung

**Entscheidung:** OpenCV wird für Bildverarbeitung verwendet, Shapely für robuste
geometrische Operationen.

**Begründung:** OpenCV deckt Kamera-, Threshold-, Kontur- und ArUco-Funktionen
ab. Shapely eignet sich für Polygonflächen, Überschneidungen und Layoutbewertung.

**Konsequenzen:**

- Die Lösung nutzt erprobte Bibliotheken statt eigener Bild- und
  Polygonalgorithmen.
- Die Zielplattform muss diese Bibliotheken zuverlässig installieren können.
- Geometrische Spezialfälle können robuster behandelt werden.

### 9.8 Solver als austauschbare Strategie

**Entscheidung:** Der Solver unterstützt mehrere Varianten wie `fast`, `greedy`
und `brute_force`.

**Begründung:** Die Erkennungs- und Lösungsqualität kann je nach Bildqualität und
Puzzleteilanzahl variieren. Eine konfigurierbare Solver-Strategie erlaubt
Vergleiche und Anpassungen ohne Änderung des Orchestrators.

**Konsequenzen:**

- Der Solver kann weiterentwickelt werden, ohne die restliche Pipeline zu ändern.
- Der Brute-Force-Ansatz ist wegen der kleinen Teileanzahl praktikabel.
- Unterschiedliche Solver können verschiedene Laufzeiten und Ergebnisqualitäten
  haben.

### 9.9 UART-Kommunikation mit ACK/DONE-Handshake

**Entscheidung:** Die Kommunikation mit dem Microcontroller erfolgt über UART mit
einem expliziten `ACK`/`DONE`-Handshake.

**Begründung:** Die Mechanik darf keine Folgekommandos erhalten, bevor ein
vorheriges Kommando angenommen und abgeschlossen wurde.

**Konsequenzen:**

- Die Anwendung sendet Kommandos synchron und kontrolliert.
- Timeouts, Fehler- und Invalid-Signale führen zu einem Abbruch.
- Die Gesamtausführung ist langsamer, aber sicherer und nachvollziehbarer.

### 9.10 Ein Orchestrierungsdurchlauf pro Programmstart

**Entscheidung:** Das Programm führt aktuell einen einzelnen Puzzle-Durchlauf pro
Start aus.

**Begründung:** Ein einzelner Durchlauf ist einfacher zu verstehen, zu testen und
bei Fehlern kontrolliert abzubrechen. Wiederholte Läufe können später über eine
äußere Schleife oder einen Prozessmanager ergänzt werden.

**Konsequenzen:**

- Der Einstiegspunkt bleibt einfach.
- Fehlerzustände müssen nicht innerhalb einer Endlosschleife zurückgesetzt
  werden.
- Für Dauerbetrieb ist eine Erweiterung erforderlich.

### 9.11 Debug-Artefakte im Dateisystem

**Entscheidung:** Zwischenergebnisse der Bildverarbeitung und Solver-Ausgaben
werden als Dateien gespeichert.

**Begründung:** Die Bildverarbeitung ist stark von realen Licht-, Kamera- und
Puzzlebedingungen abhängig. Persistente Debug-Artefakte erleichtern Analyse,
Kalibrierung und Vergleich verschiedener Solver- oder Threshold-Einstellungen.

**Konsequenzen:**

- Fehler können anhand gespeicherter Masken, Eckpunkte und Layoutbilder
  nachvollzogen werden.
- Das Dateisystem benötigt Schreibrechte und ausreichend Speicherplatz.
- Alte Debug-Ausgaben werden beim Solverlauf bereinigt.
