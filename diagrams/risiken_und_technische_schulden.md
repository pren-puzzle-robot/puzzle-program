## 11. Risiken und technische Schulden

Dieses Kapitel beschreibt architekturrelevante Risiken und bereits erkennbare
technische Schulden. Der Fokus liegt auf Punkten, die Betrieb, Integration,
Wartbarkeit oder die Zuverlässigkeit des Gesamtsystems spürbar beeinflussen
können.

### 11.1 Technische Risiken

| Risiko | Beschreibung | Auswirkung | Umgang |
| --- | --- | --- | --- |
| Abhängigkeit von realer Hardware | Zielbetrieb setzt Raspberry Pi, GoPro, UART und Mechanik gleichzeitig voraus. | Integration und Fehlersuche werden erschwert, weil Fehler oft nur im Gesamtsystem sichtbar werden. | Mock-Kamera und Stub-Microcontroller weiter pflegen und Integrationsläufe mit echter Hardware frühzeitig einplanen. |
| Empfindlichkeit der Bildverarbeitung | Segmentierung, Perspektivkorrektur und Eckenerkennung hängen von Licht, Marker-Sichtbarkeit und Kameraposition ab. | Falsch erkannte oder fehlende Puzzleteile führen zu Abbrüchen oder fehlerhaften Solver-Eingaben. | Kalibrierung, reproduzierbarer Aufbau und gespeicherte Debug-Artefakte konsequent nutzen. |
| Konfigurationsabhängige Mechanik | Mapping-Parameter wie `scale_x`, `scale_y`, `x_min` und `y_min` müssen exakt zur Mechanik passen. | Falsche Werte führen zu ungenauen oder potenziell gefährlichen Fahrbefehlen. | Konfigurationswerte dokumentieren, messen und nach Änderungen an Kamera oder Mechanik erneut validieren. |
| Kommunikationsstörungen über UART | Timeouts, Signalverlust oder unerwartete Antworten des Microcontrollers können jederzeit auftreten. | Der Orchestrator bricht Läufe ab oder bleibt auf Antwortsignale angewiesen. | `ACK`/`DONE`-Handshake beibehalten, Timeouts konservativ wählen und Fehlerfälle gezielt testen. |
| Solver-Grenzen bei Randfällen | Der Solver arbeitet für kleine Teilezahlen gut, kann aber bei ungewöhnlichen Konturen oder schlechten Eingabedaten scheitern. | Es wird keine gültige Lösung gefunden oder die berechnete Anordnung ist instabil. | Solver-Varianten vergleichbar halten und Testdaten mit schwierigen Fällen erweitern. |

### 11.2 Technische Schulden

| Schuld | Beschreibung | Folge |
| --- | --- | --- |
| Starke Steuerung über Konfigurationswerte | Wichtige Systemannahmen zu Kamera, Mapping und Solver liegen in `config.ini` statt in validierten Domänenobjekten oder Kalibrierungsartefakten. | Fehlkonfigurationen werden erst zur Laufzeit sichtbar und sind nur begrenzt abgesichert. |
| Begrenzte automatisierte End-to-End-Absicherung | Viele kritische Szenarien betreffen das Zusammenspiel von Bildverarbeitung, Solver, Mapping und UART. | Regressionen in Integrationspfaden können trotz funktionierender Einzelkomponenten unentdeckt bleiben. |
| Enger Zuschnitt auf aktuelles Zielsystem | Netzwerkadressen, Schnittstellen und Betriebsannahmen sind stark auf Raspberry Pi, GoPro und den aktuellen Microcontroller zugeschnitten. | Ein Wechsel von Kamera, Mechanik oder Kommunikationsweg erzeugt Anpassungsaufwand in Konfiguration und Adaptern. |
| Manuelle Kalibrierung und Parametertuning | Thresholds, Mindestflächen und Koordinatenparameter werden aktuell manuell bestimmt und angepasst. | Wiederholbarkeit und Übergabe an andere Teammitglieder sind erschwert. |
| Einzeldurchlauf statt robuster Dauerbetrieb | Die Anwendung ist auf einen kontrollierten Einzelstart ausgelegt und setzt Fehler eher durch Abbruch als durch Recovery um. | Für längeren autonomen Betrieb fehlen Reset-, Retry- und Wiederanlaufstrategien. |

### 11.3 Priorisierte Abbau- und Minderungsmaßnahmen

| Priorität | Maßnahme | Ziel |
| --- | --- | --- |
| Hoch | Reproduzierbare Kalibrierung für Kamera- und Mappingparameter dokumentieren und versionieren. | Risiko fehlerhafter Maschinenkoordinaten und instabiler Bildverarbeitung senken. |
| Hoch | Integrationsszenarien mit repräsentativen Testbildern und Microcontroller-Stubs automatisieren. | Regressionen in der Gesamtpipeline früher erkennen. |
| Hoch | Kritische UART- und Fehlerpfade systematisch testen, insbesondere Timeout-, `ERROR`- und Invalid-Fälle. | Betriebssicherheit der Mechanik erhöhen. |
| Mittel | Solver-Randfälle mit zusätzlichem Bildmaterial und Referenzlayouts absichern. | Ausfallrisiko bei schwierigen Puzzlegeometrien reduzieren. |
| Mittel | Betriebswissen zu Raspberry Pi, GoPro und Schnittstellen in klaren Setup-Schritten bündeln. | Technische Schulden bei Übergabe, Reproduktion und Hardwarewechsel verringern. |
