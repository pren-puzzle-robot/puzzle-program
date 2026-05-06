## Brute-Force-Algorithmus

Der Brute-Force-Solver sucht nicht mehr beliebige Positionen für die
Puzzleteile. Stattdessen sucht er zuerst eine plausible Außenkontur und platziert
die Teile danach entlang dieser Kontur.

### Grundidee

Jedes Puzzleteil besitzt mehrere erkannte `possible_outer_edges`. Der Solver
prüft Kombinationen dieser Außenkanten und bewertet, ob sie zusammen eine
geschlossene rechteckige Kontur bilden können.

Das Ziel ist ein Rechteck mit einem Seitenverhältnis von ungefähr
`1:sqrt(2)`. Intern wird dafür das Verhältnis

```python
TARGET_ASPECT_RATIO = 1.0 / math.sqrt(2.0)
```

verwendet. Bewertet wird also `kurze_seite / lange_seite`, mit einem Zielwert
von ungefähr `0.707`.

### Ablauf

1. Für jedes Puzzleteil erzeugt `_build_boundary_candidates()` mögliche
   Außenkanten-Kandidaten. Da die erkannten `possible_outer_edges`
   gegen den Uhrzeigersinn vorliegen, wird jede Außenkante einmal in die
   Uhrzeigersinn-Richtung der Rechteckkontur normalisiert. Die Gegenrichtung
   wird nicht zusätzlich ausprobiert.

2. Die Suche startet bei `(0, 0)` und läuft zuerst nach rechts.

3. `_extend_state()` versucht, jeweils ein noch nicht verwendetes Teil an die
   aktuelle Außenkontur anzuhängen. Dabei darf die Kontur geradeaus weiterlaufen
   oder um 90 Grad nach links beziehungsweise rechts abbiegen.

4. `_trace_candidate_path()` verfolgt die Segmente der ausgewählten Außenkante.
   Jedes Segment wird auf eine horizontale oder vertikale Achse gelegt. Ist ein
   Segment zu weit von diesen Achsen entfernt, wird der Kandidat verworfen.

5. Der Solver erlaubt nur eine konsistente Drehrichtung. Die Kontur muss also
   entweder vollständig im Uhrzeigersinn oder vollständig gegen den Uhrzeigersinn
   um das Rechteck laufen.

6. Wenn alle Teile verwendet wurden, prüft `_finalize_rectangle_state()`, ob die
   Kontur wieder nahe beim Startpunkt `(0, 0)` endet und genau vier 90-Grad-Ecken
   enthält. Zusätzlich muss der Mittelpunkt jedes platzierten Puzzleteils
   innerhalb des gefundenen Rechtecks liegen.

7. `_final_score()` bewertet die fertigen Rechteckkandidaten. Strafpunkte gibt
   es unter anderem für:

   - Abweichung vom Zielverhältnis `1:sqrt(2)`
   - nicht sauber geschlossene Kontur
   - unterschiedlich lange gegenüberliegende Seiten
   - überlappende Puzzleteile
   - ungenutzte Fläche in der Bounding Box
   - Geometrie, die über die gefundene Außenkontur hinausragt

   Kandidaten, bei denen ein Teilemittelpunkt außerhalb des Rechtecks liegt,
   werden nicht nur schlechter bewertet, sondern vollständig verworfen.

8. `_apply_solution()` rotiert und verschiebt anschließend die echten
   `PuzzlePiece`-Objekte so, dass ihre gewählten Außenkanten auf der gefundenen
   Rechteckkontur liegen.

### Unterschied zum alten Ansatz

Der frühere Brute-Force-Ansatz platzierte Teile über lose Ankerpositionen um
bereits gelegte Teile herum. Dadurch konnte zwar ein kompaktes Layout entstehen,
aber nicht zwingend eine sinnvolle rechteckige Puzzle-Außenform.

Der neue Ansatz sucht zuerst die Außenkontur. Die Positionen der Teile ergeben
sich danach aus der gewählten Kantenkombination. Dadurch wird die Lösung auf ein
rechteckiges Layout mit ungefähr `1:sqrt(2)` beschränkt.
