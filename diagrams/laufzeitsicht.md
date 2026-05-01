## 6. Laufzeitsicht

Die Anwendung wird als einzelner Orchestrierungsdurchlauf gestartet. Der
`PuzzleOrchestrator` koordiniert dabei alle Verarbeitungsschritte synchron
nacheinander. Die konkreten Adapter für Kamera und Microcontroller werden beim
Start anhand der `config.ini` ausgewählt.

### 6.1 Hauptszenario: Puzzle lösen und Bewegungen ausgeben

```mermaid
sequenceDiagram
    participant User as Start der Anwendung
    participant Main as puzzle_orchestrator.__main__
    participant Orchestrator as PuzzleOrchestrator
    participant MCU as MicrocontrollerPort
    participant Camera as CameraPort
    participant Solver as PuzzleSolverPort
    participant Mapper as CoordinateMapperPort

    User ->> Main: python -m puzzle_orchestrator
    Main ->> Main: load_config()
    Main ->> Main: Adapter anhand config.ini erzeugen
    Main ->> Orchestrator: run_once()

    Orchestrator ->> MCU: wait_for_start_command()
    MCU -->> Orchestrator: Start freigegeben

    Orchestrator ->> Camera: capture_frame()
    Camera -->> Orchestrator: Bildpfad

    Orchestrator ->> Solver: solve(frame)
    Solver -->> Orchestrator: SolverPlacement[]

    Orchestrator ->> Mapper: map_to_machine(placements)
    Mapper -->> Orchestrator: MachinePlacement[]

    Orchestrator ->> MCU: send_path(machine_path)
    MCU -->> Orchestrator: Ergebnisstatus

    Orchestrator -->> Main: Ergebnisstatus
    Main -->> User: Ausgabe des Ergebnisses
```

### 6.2 Ablauf der Bildaufnahme

Im Mock-Betrieb liefert die Kamera direkt den konfigurierten Bildpfad zurück. Im
GoPro-Betrieb wird die Kamera über HTTP angesprochen.

```mermaid
sequenceDiagram
    participant Orchestrator as PuzzleOrchestrator
    participant Camera as CameraController
    participant GoPro as GoPro
    participant FS as Dateisystem

    Orchestrator ->> Camera: capture_frame()
    Camera ->> GoPro: Fotomodus setzen
    Camera ->> GoPro: Shutter auslösen (Bildaufnahme)
    Camera ->> Camera: Wartezeit für Medienbereitstellung
    Camera ->> GoPro: Medienliste abrufen
    Camera ->> GoPro: Neuestes Bild herunterladen
    Camera ->> FS: Bild speichern
    Camera ->> Camera: ArUco-Marker erkennen
    Camera ->> Camera: Perspektive entzerren
    Camera ->> FS: entzerrtes Bild speichern
    Camera -->> Orchestrator: Pfad zum entzerrten Bild
```

### 6.3 Ablauf der Puzzle-Lösung

Der Solver verarbeitet das entzerrte Bild zu geometrischen Puzzleteilen und
berechnet daraus eine Zielanordnung.

```mermaid
sequenceDiagram
    participant Orchestrator as PuzzleOrchestrator
    participant Solver as PuzzleSolver
    participant CV as OpenCV/Shapely
    participant Output as Debug-Ausgabe

    Orchestrator ->> Solver: solve(frame)
    Solver ->> Solver: Output-Verzeichnis vorbereiten
    Solver ->> CV: Bild laden
    Solver ->> CV: Vordergrund segmentieren
    Solver ->> CV: einzelne Puzzleteile extrahieren
    Solver ->> Output: Masken speichern
    Solver ->> CV: Ecken und Polygone erkennen
    Solver ->> Output: Eckpunkt-Debugbilder speichern
    Solver ->> Solver: PuzzlePiece-Modelle erzeugen
    Solver ->> Solver: Solver-Variante ausführen
    Solver ->> Solver: Zielpositionen normalisieren
    Solver ->> Output: gelöstes Layout speichern
    Solver -->> Orchestrator: Liste von SolverPlacement
```

### 6.4 Ablauf der Microcontroller-Kommunikation

Bei UART-Betrieb wird jede Bewegung beziehungsweise jeder einfache Befehl erst
nach Bestätigung durch den Microcontroller abgeschlossen. Dadurch wird
verhindert, dass Folgekommandos gesendet werden, bevor die Mechanik bereit ist.

```mermaid
sequenceDiagram
    participant Orchestrator as PuzzleOrchestrator
    participant UART as UartMicrocontrollerInterface
    participant Session as UART-Session
    participant TinyK22 as Microcontroller

    Orchestrator ->> UART: send_path(machine_path)

    loop für jedes Puzzleteil
        UART ->> Session: Move zur Startposition
        Session ->> TinyK22: M
        TinyK22 -->> Session: ACK
        TinyK22 -->> Session: DONE

        UART ->> Session: LOWER
        Session ->> TinyK22: l
        TinyK22 -->> Session: ACK
        TinyK22 -->> Session: DONE

        UART ->> Session: HOLD_ON
        Session ->> TinyK22: H
        TinyK22 -->> Session: ACK
        TinyK22 -->> Session: DONE

        UART ->> Session: LIFT
        Session ->> TinyK22: L
        TinyK22 -->> Session: ACK
        TinyK22 -->> Session: DONE

        UART ->> Session: Move zur Zielposition
        Session ->> TinyK22: M
        TinyK22 -->> Session: ACK
        TinyK22 -->> Session: DONE

        UART ->> Session: LOWER
        Session ->> TinyK22: l
        TinyK22 -->> Session: ACK
        TinyK22 -->> Session: DONE

        UART ->> Session: HOLD_OFF
        Session ->> TinyK22: h
        TinyK22 -->> Session: ACK
        TinyK22 -->> Session: DONE

        UART ->> Session: LIFT
        Session ->> TinyK22: L
        TinyK22 -->> Session: ACK
        TinyK22 -->> Session: DONE
    end

    UART -->> Orchestrator: Ergebnisstatus
```

### 6.5 Fehlerfälle

Während des Durchlaufs brechen Fehler den aktuellen Lauf ab. Der Einstiegspunkt
protokolliert die Exception und reicht sie weiter.

Typische Fehlerfälle sind:

- Die Konfigurationsdatei fehlt oder enthält ungültige Werte.
- Das Mock-Bild oder Kamerabild kann nicht gelesen werden.
- Die GoPro ist nicht erreichbar oder liefert kein neues Bild.
- ArUco-Marker werden nicht vollständig erkannt.
- Die Segmentierung findet nicht die erwartete Anzahl von Puzzleteilen.
- Der Solver findet keine gültige Anordnung.
- UART liefert kein `ACK`, kein `DONE`, ein `ERROR` oder ein ungültiges Kommando.

Das Programm führt aktuell einen einzelnen Orchestrierungszyklus aus. Wiederholte
Puzzleläufe müssten durch eine äußere Schleife oder einen Prozessmanager ergänzt
werden.
