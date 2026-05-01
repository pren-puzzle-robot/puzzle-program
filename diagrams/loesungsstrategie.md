## 4. Lösungsstrategie

Das System wird als modulare, sequenzielle Pipeline realisiert. Ein zentraler
`PuzzleOrchestrator` steuert den Ablauf vom Startsignal über Bildaufnahme und
Puzzle-Lösung bis zur Übergabe der berechneten Bewegungen an die Maschine.

Die Architektur folgt dem Ports-and-Adapters-Prinzip. Die fachliche
Ablaufsteuerung ist von konkreter Hardware getrennt. Kamera, Puzzle-Solver,
Koordinatentransformation und Microcontroller-Kommunikation werden über klar
definierte Schnittstellen angebunden. Dadurch können reale Hardwareadapter im
Zielsystem und Mock-/Stub-Implementierungen in der Entwicklung verwendet werden.

Die Lösung kombiniert Bildverarbeitung, geometrische Modellierung und
maschinennahe Steuerung:

- OpenCV wird für Bildaufnahme, Perspektivkorrektur, Segmentierung und
  Konturerkennung verwendet.
- Die erkannten Puzzleteile werden als geometrische Polygone modelliert.
- Der Solver berechnet aus diesen Modellen eine Zielanordnung mit Positionen
  und Rotationen.
- Ein Coordinate Mapper transformiert Solver-Koordinaten in Maschinenkoordinaten.
- Die Ausgabe an den Microcontroller erfolgt über eine austauschbare
  Schnittstelle.

Wichtige Architekturziele dieser Strategie sind Änderbarkeit, Testbarkeit ohne
Hardware und eine klare Trennung zwischen Bildverarbeitung, Lösungslogik und
Hardwarekommunikation.
