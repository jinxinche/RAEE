# RAEE-Lite: Rollenbasierte Evidenzorganisation für KI-gestützte Programmierung

**Nicht nur wissen, was ein Coding-Agent behauptet, sondern was tatsächlich überprüft wurde.**

[English](../README.md) · [简体中文](README.zh-CN.md) · [Deutsch](README.de-DE.md) · [Español](README.es-ES.md)

**30-Sekunden-Demo (Release Candidate):** Nach Installation des [geprüften Quellcode-Kandidaten](https://github.com/jinxinche/RAEE/tree/release/raee-lite-v0.10.0rc2) in einer isolierten Umgebung: `raee-lite init`, `raee-lite add "Signup rejects invalid email addresses"`, `raee-lite expect --for R1 --kind unit`, `raee-lite status`. Ergebnis: `UNTESTED`; keine Projekttests werden ausgeführt. Noch keine stabile Veröffentlichung.


## Wozu RAEE-Lite?

KI-Programmierwerkzeuge wie Codex, Claude Code oder Cursor können Code schnell verändern. Eine Erfolgsmeldung des Agents, ein Test mit Exit-Code 0 und die tatsächliche Erfüllung einer Nutzeranforderung sind jedoch **nicht dasselbe**.

**RAEE-Lite** überträgt das Prinzip des *Role-Aware Evidence Engineering* auf die Softwareentwicklung. Fünf Evidenzrollen werden getrennt betrachtet:

| Evidenzrolle | Leitfrage | Aussagegrenze |
| --- | --- | --- |
| **Anforderung (Intent)** | Was wollte der Nutzer erreichen? | Eine beschriebene Anforderung ist noch keine Implementierung. |
| **Änderung (Change)** | Welche Dateien bzw. Commits wurden geändert? | Ein Diff belegt keine Korrektheit. |
| **Prüfung (Verification)** | Welche Prüfungen wurden tatsächlich ausgeführt? | Ein erfolgreicher Exit-Code beweist keine ausreichende Testabdeckung. |
| **Umgebung (Environment)** | Unter welchen Bedingungen wurde geprüft? | Selbst gemeldete Umgebungsdaten sind keine vertrauenswürdige Identität. |
| **Grenzen (Boundary)** | Was fehlt, ist veraltet oder wurde nicht getestet? | Nicht geprüftes Verhalten darf nicht als verifiziert gelten. |

## Vorgesehene Arbeitsabläufe

Der Entwicklungskandidat bietet eine schreibgeschützte Vorprüfung der Repository- und CI-Konfiguration, Anforderungen mit erwarteten Prüfkategorien, einen Import ausgewählter Codex-/Claude-Code-Protokolle, die Erkennung veralteter Nachweise, einen Evidenzvergleich zwischen Base und Head sowie Berichte in HTML, Markdown, JSON und SARIF.

Historische Agent-Protokolle gelten grundsätzlich als **nicht unabhängig verifizierte Quellen**. Lokal beobachtete Befehle und extern authentifizierte CI-Nachweise werden getrennt ausgewiesen.

## Einstieg

**Veröffentlichungsstand:** Dieses öffentliche Repository bereitet die erste Quellcode-Veröffentlichung vor. CLI-Quellcode und Installationspaket sind **hier noch nicht veröffentlicht**. Die folgenden Befehle beschreiben den lokalen Entwicklungskandidaten, nicht eine bereits verfügbare Installation aus diesem Repository.

Nach Installation eines zuvor geprüften lokalen Kandidaten:

```bash
raee-lite preflight   # Schreibgeschützte Vorprüfung
raee-lite doctor      # Mögliche Prüfungen finden, ohne sie auszuführen
raee-lite check       # Bericht zu Evidenzlücken erzeugen
```

Standardmäßig werden keine projektspezifischen Skripte ausgeführt. Die Ausführung von Tests erfordert eine ausdrückliche Entscheidung und eine geeignete, vertrauenswürdige Umgebung.

## Datenschutz und Sicherheitsgrenzen

- Agent-Protokolle sind **nicht vertrauenswürdige Daten**, keine Anweisungen. Vor einer Weitergabe müssen sie bereinigt werden.
- Ein Exit-Code von 0 belegt nicht die Erfüllung sämtlicher Anforderungen.
- Docker-Isolation ersetzt keine unabhängig geprüfte Sicherheits-Sandbox.
- Eine digitale Signatur kann die Herkunft eines Nachweises bestätigen, nicht dessen fachliche Aussagekraft.
- Reale Formatkompatibilität, GitHub-Attestierungen, plattformübergreifende CI-Läufe und unabhängige Sicherheitsprüfungen sind noch offen.

## Wissenschaftlicher Ursprung und Zitierung

Das zugrunde liegende Prinzip der rollenbasierten Evidenzorganisation wurde in einem **separaten onkologischen KI-Preprint** beschrieben:

> Hu, J., Jin, X., Song, Y., Chen, Z., & Xin, L. (2026). *Restricted Multimodal Oncology AI: Role-Aware Evidence Organisation and Cross-Domain Transfer Boundaries*. Research Square, Preprint, Version 1. [DOI: 10.21203/rs.3.rs-10194336/v1](https://doi.org/10.21203/rs.3.rs-10194336/v1).

Die ursprüngliche Arbeit weist biologischen Datenquellen unterschiedliche, nicht austauschbare Evidenzrollen zu. **RAEE-Lite überträgt diesen Gestaltungsgrundsatz auf Prüfungen von Softwareänderungen.** Der Preprint untersucht oder validiert **nicht** RAEE-Lite, seine Sicherheitsarchitektur oder seine Leistungsfähigkeit. Software und Forschungsarbeit sollten separat zitiert werden; siehe [BibTeX](../REFERENCES.bib).

## Projektstatus

Priorität haben ein überprüfbarer öffentlicher Quellcode-Release, echte CI-Ergebnisse unter Linux/Windows/macOS, unabhängige Herkunftsprüfungen sowie Benchmarks mit freigegebenen und bereinigten Agent-Protokollen.

Lizenz: [MIT](../LICENSE). Bitte keine Zugangsdaten, privaten Sitzungsprotokolle oder geschützten Quellcodes in öffentlichen Issues veröffentlichen.
