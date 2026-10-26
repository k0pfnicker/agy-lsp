# agy-lsp — Language Server Protocol MCP Bridge for Antigravity CLI

[![Version](https://img.shields.io/badge/version-1.1.0-purple.svg)](#13-entwicklung-tests--qualitätssicherung)
[![Tests](https://img.shields.io/badge/tests-46%20passed-brightgreen.svg)](#13-entwicklung-tests--qualitätssicherung)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-blue.svg)](#13-entwicklung-tests--qualitätssicherung)
[![MCP](https://img.shields.io/badge/MCP-2.0%20%2F%201.0-orange.svg)](https://modelcontextprotocol.io)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

*Dieses Dokument in anderen Sprachen: [English](README.md) | [Deutsch](README.de.md)*

**agy-lsp** ist ein produktionsreifes, professionelles Plugin für das **Google Antigravity CLI (`agy`)**. Es verbindet den KI-Agenten über das standardisierte **Model Context Protocol (MCP)** mit nativen **Language Servern (LSP)** für C#, C/C++, TypeScript/JavaScript, Python, Rust und Go.

> **Companion-Plugin:** Kombiniere `agy-lsp` (statische Code-Navigation & Diagnosen) mit [**agy-dap**](https://github.com/k0pfnicker/agy-dap) (hypothesengetriebenes Laufzeit-Debugging via DAP).

---

## Inhaltsverzeichnis

1. [Zweck und Nutzen](#1-zweck-und-nutzen)
   - [Empirische Benchmarks & Testergebnisse](#empirische-benchmarks--testergebnisse)
2. [Architektur](#2-architektur)
3. [MCP-Tools im Überblick](#3-mcp-tools-im-%C3%BCberblick)
4. [Unterstützte Sprachen & Language Server](#4-unterst%C3%BCtzte-sprachen--language-server)
5. [Voraussetzungen](#5-voraussetzungen)
6. [Installation & Schnellstart](#6-installation--schnellstart)
   - [Windows](#windows-powershell)
   - [Linux / macOS](#linux--macos)
7. [Einrichtung in Antigravity CLI](#7-einrichtung-in-antigravity-cli)
8. [Installation der Language Server](#8-installation-der-language-server)
9. [Konfiguration (`agy-lsp.json`)](#9-konfiguration-agy-lspjson)
10. [Token-Effizienz & Kontext-Optimierung](#10-token-effizienz--kontext-optimierung)
11. [Sicherheitsmodell](#11-sicherheitsmodell)
12. [Troubleshooting & Diagnose](#12-troubleshooting--diagnose)
13. [Entwicklung, Tests & Qualitätssicherung](#13-entwicklung-tests--qualit%C3%A4tssicherung)
14. [Erweiterung um neue Sprachen](#14-erweiterung-um-neue-sprachen)
15. [Bekannte Einschränkungen](#15-bekannte-einschr%C3%A4nkungen)

---

## 1. Zweck und Nutzen

Große Sprachmodelle (LLMs) scheitern in Softwareprojekten häufig an zwei Hürden:
1. **Unpräzise Suche:** Volltextsuche und das Lesen ganzer Dateien verbrauchen tausende Kontext-Token und übersehen oft semantische Zusammenhänge (z. B. Überladungen, Vererbung oder Namespaces).
2. **Fehlendes Feedback:** Nach Code-Modifikationen bemerkt der Agent Syntax-, Typprüfungs- oder Importfehler oft erst spät oder gar nicht.

**agy-lsp** löst dieses Problem, indem es dem Antigravity-Agenten direkte Compiler- und Typintelligenz über standardisierte MCP-Tools bereitstellt:
- **Präzise Symbol-Navigation:** Definitionen und Referenzen ohne Raten anspringen.
- **Automatisierte Qualitätskontrolle:** Compiler-Diagnosen (Errors, Warnings) direkt nach Dateiänderungen abfragen.
- **Sicheres Refactoring:** Symbol-Umbenennungen werden standardmäßig als Unified-Diff-Vorschau berechnet, bevor Dateien modifiziert werden.
- **Geringer Tokenverbrauch:** Kompakte Snippets, Dokument-Outlines und strikte Treffer-Limits.

### Empirische Benchmarks & Testergebnisse

Alle nachfolgenden Messwerte werden automatisiert durch unsere Benchmark- und E2E-Testsuite ([`tests/test_benchmarks_and_value.py`](tests/test_benchmarks_and_value.py) sowie [`tests/test_e2e_real_lsp.py`](tests/test_e2e_real_lsp.py)) gegen echte `clangd`- (C/C++) und `pylsp`-Prozesse (Python) verifiziert:

| Test-Szenario | Ohne `agy-lsp` (Grep / File-Read / Raw LSP) | Mit `agy-lsp` (Smart MCP Bridge) | Gemessener Mehrwert |
| :--- | :--- | :--- | :--- |
| **1. Dokument-Gliederung (`document_symbols`)**<br>*C-Header mit 3 Structs/Enums (65 Felder) & 4 Funktionen* | **18.979 Bytes** (`~4.745 Tokens`) Raw-LSP-JSON<br>**8.155 Bytes** (`~2.039 Tokens`) mit allen Einzelfeldern | **1.647 Bytes** (`~412 Tokens`)<br>Faltet Struct-/Enum-Felder automatisch in `fields_count` | **-91,3 % Tokens** ggü. Raw LSP<br>**-79,8 % Tokens** ggü. Voll-Baum |
| **2. Ungenaue LLM-Spaltenangaben (`go_to_definition`)**<br>*10 ungenaue Aufrufe: Spalte 1, Keywords (`int`, `const`), Zeilenende, ±1 Zeile* | **0 / 10 aufgelöst (0 % Trefferquote)**<br>Raw LSP liefert `null` bei Leerzeichen oder Schlüsselwörtern | **10 / 10 aufgelöst (100 % Trefferquote)**<br>Auto-Snapping auf Bezeichner & `symbol_name`-Suche (±2 Zeilen) | **0 % → 100 % Trefferquote** ohne teure LLM-Retry-Schleifen |
| **3. Semantische Navigation vs. Text-Grep (`find_references` & `go_to_definition`)**<br>*Suche nach `execute_step` mit Kommentar- & String-Fallen* | **8 Grep-Treffer (5 False Positives = 62,5 % Rauschen)**<br>Erfordert Lesen ganzer Dateien (**3.975 Bytes / ~994 Tokens**) | **3 AST-verifizierte Referenzen (0 % False Positives)**<br>Definition + 3-Zeilen-Snippet in **449 Bytes (~112 Tokens)** | **100 % Präzision** (0 False Positives)<br>**-88,7 % Kontext-Tokens** |
| **4. Echtzeit-Compiler-Diagnose & Kaskaden-Filter (`get_diagnostics`)**<br>*C-Typ-/Identifier-Fehler & 120-Fehler-Template-Kaskade* | Kein Feedback ohne kompletten Build-Lauf;<br>Raw-Kaskade: **145.680 Bytes (~36.420 Tokens)** | **2 Fehler in ~198 ms erkannt** (Event-gesteuertes `didOpen`);<br>Dedupliziert & gekürzt: **27.912 Bytes (~6.978 Tokens)** | **< 200 ms** Sofort-Feedback<br>**-80,8 % Diagnose-Rauschen** |
| **5. Sicheres dateiübergreifendes Refactoring (`rename_symbol`)**<br>*Umbenennung `execute_step` → `dispatch_op` in `engine.h` & `engine.c`* | Suchen & Ersetzen beschädigt String-Literale (`"execute_step"`) und Kommentare direkt auf der Festplatte | **2 Dateien als Diff-Vorschau (`applied: false`)**<br>Aktualisiert Prototyp, Definition & Aufrufe; Strings/Kommentare unberührt | **0 beschädigte Dateien**<br>100 % AST-sicherer Unified-Diff |
| **6. Aufrufbaum ohne Dateilesen (`call_hierarchy`)**<br>*Aufrufer & Unterfunktionen von `execute_step` ermitteln* | Erfordert mehrfaches `grep` und Einlesen aller Kandidaten-Dateien | 1 Tool-Aufruf liefert Aufrufer (`run_program`) & Callees (`clamp_register`) direkt aus dem AST | **1 Tool-Aufruf** statt Multi-File-Analyse |

#### Warum diese Ergebnisse das Plugin in der Praxis so wertvoll machen

1. **Drastische Einsparung von Kontext-Tokens (-80 % bis -91 %):** In C/C++-, C#- und TypeScript-Projekten besitzen Datenstrukturen und Enums oft dutzende Felder. Während ein ungefilterter LSP-Dump tausende Zeilen JSON-Koordinaten in das Kontextfenster spült, komprimiert `agy-lsp` Blatt-Felder standardmäßig auf `"fields_count": 34` und erhält dabei 100 % der Typ-, Klassen- und Funktionssignaturen.
2. **Robustheit gegen fehlerhafte Spaltenzählung von LLMs (0 % → 100 % Trefferquote):** Sprachmodelle schätzen 1-basierte Zeichenspalten häufig falsch ein – sie übergeben oft `character=1` (Einrückung am Zeilenanfang) oder landen auf Schlüsselwörtern wie `static`, `int`, `const` oder `def`. Ein Standard-LSP-Server bricht hier ergebnislos ab. `agy-lsp` rastet automatisch auf dem nächstgelegenen echten Symbolbezeichner der Zeile ein (oder sucht `symbol_name` im Radius von ±2 Zeilen) und prüft bei Bedarf weitere Bezeichner derselben Zeile.
3. **Null False Positives bei Navigation & Refactoring:** Während `grep` im Benchmark **62,5 % Fehlalarme** in Kommentaren und Strings lieferte, nutzt `agy-lsp` den echten Compiler-AST (`clangd`, `pylsp`, `pyright`, `csharp-ls`, `tsserver`). Beim Umbenennen bleiben Strings und Kommentare garantiert unangetastet, und alle Änderungen werden zuerst als sicherer Unified-Diff präsentiert.
4. **Compiler-Feedback in unter 200 ms ohne Build-Prozess:** Durch die ereignisgesteuerte `textDocument/publishDiagnostics`-Synchronisation (`asyncio.Event`) erhält der Agent sofort nach dem Öffnen oder Ändern einer Datei exakte Compiler-Fehlermeldungen – ohne Wartezeit durch statische Timeouts oder manuelle Kompilierläufe.

---

## 2. Architektur

```text
┌─────────────────────────────────────────────────────────────┐
│                    Antigravity CLI (agy)                    │
│                                                             │
│   Agent Turn / Reasoning ◄──► Skills / AGENTS.md Rules      │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              │ Stdio Transport (JSON-RPC)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  agy-lsp (MCP-Server)                       │
│                                                             │
│  ├── Tool Schemas (get_diagnostics, go_to_definition, ...)  │
│  ├── Document Sync (didOpen, didChange, didClose, Cache)    │
│  ├── Token Reducer (Snippet-Schnitt, Deduplizierung, Limit) │
│  └── Workspace Confinement Security Check                   │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              │ Async Process I/O (Content-Length Framing)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Language Server (LSP)                     │
│                                                             │
│   [Python]       [C#]             [C / C++]      [TS / JS]  │
│   pyright /      csharp-ls /      clangd         typescript-│
│   pylsp          Roslyn Server                   language-  │
│                                                  server     │
└─────────────────────────────────────────────────────────────┘
```

Die Bridge startet Language-Server-Prozesse **bedarfsgesteuert (Lazy-Loading)** erst dann, wenn ein Tool eine Datei der entsprechenden Sprache anfragt. Laufende Prozesse werden über die gesamte Session wiederverwendet und bei Abstürzen mit begrenzter Retry-Anzahl automatisch wiederhergestellt.

---

## 3. MCP-Tools im Überblick

Das Plugin registriert 11 performante MCP-Tools:

| Tool | Zweck | Wichtige Parameter | Rückgabewert |
| :--- | :--- | :--- | :--- |
| `get_diagnostics` | Fehler, Warnungen und Hinweise für eine Datei oder das gesamte Projekt abfragen | `file_path`, `line_start`, `line_end`, `severity`, `limit` | Liste deduplizierter Diagnosen mit Datei, Zeile, Spalte, Code und Nachricht. |
| `go_to_definition` | Springt von einer Position zur Deklaration/Definition | `file_path`, `line`, `character`, `symbol_name`, `include_snippet` | Zieldatei, Zeilenbereich, optionaler kompakter Code-Ausschnitt. |
| `find_references` | Findet alle Verwendungsstellen eines Symbols | `file_path`, `line`, `character`, `symbol_name`, `include_declaration`, `limit` | Liste aller Referenzen im Workspace. |
| `rename_symbol` | Führt ein symbolweites Umbenennen via LSP durch | `file_path`, `line`, `character`, `new_name`, `apply`, `symbol_name` | **Preview-Diff** aller betroffenen Dateien. Schreiben auf Festplatte erfordert `apply=True` und `writeChanges=True`. |
| `document_symbols` | Liefert hierarchische Gliederung (Klassen, Methoden, Funktionen) | `file_path`, `query`, `include_fields`, `max_depth` | Symbolbaum mit Art, Zeilenbereich und Bezeichnern (Struct-Felder/Enum-Member standardmäßig als `fields_count` komprimiert). |
| `workspace_symbols` | Durchsucht das gesamte Projekt nach Symbolen | `query`, `limit` | Trefferliste mit Name, Symbol-Art, Datei und Position. |
| `hover` | Zeigt Signaturen, Typen und Docstrings | `file_path`, `line`, `character`, `symbol_name` | Markdown-formatiertes Hover-Ergebnis. |
| `prepare_call_hierarchy` | Prüft Unterstützung und liefert Call-Hierarchy-Item | `file_path`, `line`, `character`, `symbol_name` | Vorbereitetes Symbol für den Aufrufbaum. |
| `call_hierarchy` | Ermittelt Aufrufer (`incoming`) oder aufgerufene Methoden (`outgoing`) | `file_path`, `line`, `character`, `direction`, `symbol_name` | Liste der Aufrufer bzw. Unterfunktionen. |
| `get_type_hierarchy` | Liefert Basistypen (`supertypes`) oder Subklassen (`subtypes`) | `file_path`, `line`, `character`, `direction`, `symbol_name` | Vererbungshierarchie des Typs. |
| `lsp_status` | Status aller Server, Workspace-Root und Fehler | *keine* | JSON-Übersicht mit Server-Zustand (`RUNNING`, `AVAILABLE`, `NOT_INSTALLED`, `CRASHED`), PID und Pfad. |

*Hinweis:* Zeilen- und Spaltenangaben in allen Tool-Parametern und Rückgaben sind **1-basiert**. Positionsbasierte Tools korrigieren ungenaue Spaltenangaben (`character`) oder einen optionalen `symbol_name`-Parameter automatisch auf den Bezeichner in der jeweiligen Zeile.

---

## 4. Unterstützte Sprachen & Language Server

| Sprache | Primärer Server | Erkannte Dateiendungen | Projekt-Erkennungsmarker |
| :--- | :--- | :--- | :--- |
| **Python** | `pyright-langserver` *(Fallback: `basedpyright-langserver`, `pylsp`, `pyright`)* | `.py`, `.pyi` | `pyproject.toml`, `setup.py`, `requirements.txt` |
| **C#** | `csharp-ls` *(Fallback: `roslyn-language-server`)* | `.cs` | `*.sln`, `*.slnx`, `*.csproj` |
| **C / C++** | `clangd` *(Fallback: `ccls`)* | `.c`, `.cpp`, `.cc`, `.cxx`, `.h`, `.hpp`, `.hxx` | `CMakeLists.txt`, `compile_commands.json`, `*.vcxproj` |
| **TypeScript / JS**| `typescript-language-server` *(Fallback: `vtsls`)* | `.ts`, `.tsx`, `.js`, `.jsx`, `.mjs`, `.cjs` | `package.json`, `tsconfig.json` |
| **Rust** | `rust-analyzer` | `.rs` | `Cargo.toml` |
| **Go** | `gopls` | `.go` | `go.mod` |

---

## 5. Voraussetzungen

- **Betriebssystem:** Windows 10/11, macOS oder Linux.
- **Python:** Python 3.9 oder neuer (Python 3.14+ vollständig unterstützt).
- **Antigravity CLI:** `agy` installiert.
- Der jeweilige Language Server für die zu bearbeitende Sprache (z. B. `pylsp` oder `pyright` für Python, `clangd` für C++, etc.).

---

## 6. Installation & Schnellstart

### Windows (PowerShell)

```powershell
# 1. Repository klonen und in das Verzeichnis wechseln
git clone https://github.com/k0pfnicker/agy-lsp.git
cd agy-lsp

# 2. Virtuelle Umgebung anlegen und Abhängigkeiten installieren (Anführungszeichen um ".[dev]" in PowerShell beachten)
python -m venv .venv
.\.venv\Scripts\pip.exe install -e ".[dev]"

# 3. Optional: Python- & C/C++-Language-Server direkt in .venv installieren (keine Admin-Rechte nötig)
.\.venv\Scripts\pip.exe install python-lsp-server clangd

# 4. Ein-Schritt-Setup für Workspace & MCP ausführen
.\.venv\Scripts\python.exe setup_agy.py --workspace D:\DeinProjekt
```

### Linux / macOS

```bash
cd /path/to/agy-lsp
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pip install python-lsp-server clangd
python setup_agy.py --workspace /path/to/your/project
```

---

## 7. Einrichtung in Antigravity CLI

### Option A: Automatisiertes Setup über `setup_agy.py` (Empfohlen)

Der Aufruf `python setup_agy.py --workspace <pfad>` erledigt alles in einem Schritt:
1. Ermittelt den absoluten Pfad zu `.venv/Scripts/agy-lsp` und `.venv/Scripts` (sodass in `.venv` installierte Language Server wie `pylsp` und `clangd` ohne Änderung des globalen System-`PATH` sofort gefunden werden).
2. Trägt `agy-lsp` in `~/.gemini/config/mcp_config.json` ein.
3. Kopiert `SKILL.md` nach `<workspace>/.agents/skills/agy-lsp/SKILL.md` und verhindert doppelte MCP-Server-Einträge (`agy-lsp` + `agy-lsp_agy-lsp`).

### Option B: Als Workspace- oder Globales Plugin

Das Plugin erfüllt die offizielle Manifest-Spezifikation (`plugin.json` und `mcp_config.json`).
*(Hinweis: Registrieren Sie nicht gleichzeitig `~/.gemini/config/mcp_config.json` und `.agents/plugins/agy-lsp/mcp_config.json`, da Antigravity sonst zwei identische Server-Instanzen anlegt.)*

Überprüfen Sie die Gültigkeit mit dem offiziellen CLI-Befehl:
```bash
agy plugin validate .
```
Ausgabe:
```text
  [ok]    .
          ✔ skills      : 1 processed
          ✔ mcpServers  : 1 processed
```

---

## 8. Installation der Language Server

Sollte ein Language Server nicht auf Ihrem System vorhanden sein, liefert das Plugin eine klare, strukturierte Meldung mit der exakten Installationsanweisung. Im selben `.venv` installierte Binaries werden automatisch erkannt:

### Python
```bash
# Option 1: python-lsp-server (reines Python, keine Node-Abhängigkeit)
pip install python-lsp-server

# Option 2: Pyright
npm install -g pyright
```

### C# (.NET)
```bash
dotnet tool install -g csharp-ls
```

### C / C++
- **Python-Wheel (Windows / Linux / macOS, ohne Admin-Rechte):** `pip install clangd`
- **Windows:** `scoop install llvm` oder `winget install LLVM.LLVM`
- **macOS:** `brew install llvm`
- **Linux (Debian/Ubuntu):** `sudo apt-get install clangd`

### TypeScript / JavaScript
```bash
npm install -g typescript-language-server typescript
```

---

## 9. Konfiguration (`agy-lsp.json`)

Das Plugin funktioniert ohne Konfigurationsdatei mit sicheren Standardwerten. Bei Bedarf kann im Projektstamm oder unter `~/.gemini/config/agy-lsp.json` eine eigene Konfiguration hinterlegt werden:

```json
{
  "defaultLanguage": "auto",
  "workspaceRoot": null,
  "maxResults": 50,
  "includeCodeSnippets": false,
  "snippetContextLines": 3,
  "allowOutsideWorkspace": false,
  "writeChanges": false,
  "serverStartupTimeoutMs": 15000,
  "requestTimeoutMs": 10000,
  "maxRestartAttempts": 2,
  "servers": {
    "csharp": {
      "command": "csharp-ls",
      "args": []
    },
    "cpp": {
      "command": "clangd",
      "args": ["--background-index"]
    },
    "typescript": {
      "command": "typescript-language-server",
      "args": ["--stdio"]
    },
    "python": {
      "command": "pyright-langserver",
      "args": ["--stdio"],
      "fallbacks": [
        { "command": "pylsp", "args": [] }
      ]
    }
  }
}
```

### Konfigurationsparameter im Detail

| Schlüssel | Typ | Standard | Beschreibung |
| :--- | :--- | :--- | :--- |
| `defaultLanguage` | `string` | `"auto"` | Sprache bei unbekannter Dateiendung (`"auto"`, `"python"`, etc.). |
| `workspaceRoot` | `string \| null` | `null` | Expliziter Workspace-Pfad. Wenn `null`, wird er anhand von `.git`, `.sln` oder `pyproject.toml` ermittelt. |
| `maxResults` | `integer` | `50` | Maximale Trefferanzahl für Symbollisten, Referenzen und Diagnosen. |
| `includeCodeSnippets` | `boolean` | `false` | Ob bei Definitionen und Referenzen kurze Code-Kontexte mitgeliefert werden. |
| `snippetContextLines` | `integer` | `3` | Anzahl der Zeilen vor/nach der Zielposition im Snippet. |
| `allowOutsideWorkspace` | `boolean` | `false` | **Sicherheitsbarriere:** Verbietet standardmäßig das Öffnen von Pfaden außerhalb des Workspace. |
| `writeChanges` | `boolean` | `false` | **Schreibschutz:** Erlaubt tatsächliches Schreiben von Änderungen auf die Festplatte (z. B. bei Rename). |
| `serverStartupTimeoutMs`| `integer` | `15000` | Zeitlimit für den Handshake (`initialize`) des Language Servers. |
| `requestTimeoutMs` | `integer` | `10000` | Timeout für einzelne JSON-RPC-Anfragen. |
| `maxRestartAttempts` | `integer` | `2` | Maximale Anzahl automatischer Neustarts bei Absturz des Serverprozesses. |

---

## 10. Token-Effizienz & Kontext-Optimierung

Damit der KI-Agent nicht mit riesigen JSON-Nutzlasten überflutet wird, implementiert die Bridge mehrere Token-Schutzmechanismen:

1. **Kein Ausgeben vollständiger Dateien:** Es werden immer nur exakte Positionen oder kleine Kontextfenster (Standard: 3 Zeilen) zurückgegeben.
2. **Deduplizierung von Diagnosen:** Wiederholte Fehlermeldungen an derselben Code-Stelle werden zusammengefasst.
3. **Meldungskürzung:** Übermäßig lange Fehlermeldungen von Compilern werden nach 400 Zeichen gekürzt (`... [truncated]`).
4. **Ergebnisbegrenzung & Paginierung:** Listen von Referenzen oder Workspace-Symbolen sind auf `maxResults` begrenzt und enthalten ein `truncated: true`-Flag mit der Gesamtzahl der Treffer.
5. **Kompakte Struktur:** Leere optionale Felder (wie `children` ohne Unterelemente) werden weggelassen.

---

## 11. Sicherheitsmodell

- **Workspace Confinement:** Alle Pfadangaben in Tool-Aufrufen werden kanonisiert (`resolve()`). Pfade außerhalb des Projektstamms (`workspaceRoot`) werden sofort abgelehnt, es sei denn, `allowOutsideWorkspace: true` wurde explizit gesetzt. Traversal-Attacken (`../../`) werden zuverlässig blockiert.
- **Keine Shell-Ausführung:** Alle Subprozesse werden direkt über `asyncio.create_subprocess_exec` ohne Shell (`shell=False`) gestartet.
- **Sichere Allowlist / Konfiguration:** Serverbefehle stammen ausschließlich aus der statischen Konfiguration und niemals aus Parametern des Agenten.
- **Keine Secrets im Log:** Ein benutzerdefinierter Logger filtert Passwörter, Bearer-Tokens und API-Keys aus Protokollmeldungen.
- **Stderr-Isolation:** Sämtliche Status- und Debuginformationen fließen ausschließlich über `sys.stderr`, um den Standard-Input/Output für das MCP-Protokoll nicht zu stören.

---

## 12. Troubleshooting & Diagnose

### Server-Status überprüfen
Rufen Sie im Agenten oder per MCP das Tool `lsp_status` auf:
```json
{
  "name": "lsp_status",
  "arguments": {}
}
```
Die Antwort zeigt:
- Welcher Server für welche Sprache aktiv ist (`RUNNING`),
- Ob ein Server fehlt (`NOT_INSTALLED`) samt Installationsbefehl,
- Den aktuellen Workspace-Root und PID des Prozesses.

### Fehlermeldung: "Language server command '...' was not found"
Installieren Sie den jeweiligen Server gemäß Abschnitt 8 oder tragen Sie den absoluten Pfad zur ausführbaren Datei in `agy-lsp.json` ein:
```json
{
  "servers": {
    "csharp": {
      "command": "C:/Users/<User>/.dotnet/tools/csharp-ls.exe"
    }
  }
}
```

---

## 13. Entwicklung, Tests & Qualitätssicherung

### Test-Suite & Empirische Benchmarks ausführen

Die gesamte Testsuite umfasst **45 automatisierte Unit-, Integrations-, Benchmark- und End-to-End-Tests** (`pylsp` & `clangd`):

```powershell
# Alle 45 Tests ausführen
.\.venv\Scripts\pytest.exe -v

# Empirische Benchmarks mit detaillierter Metrik-Ausgabe ausführen
.\.venv\Scripts\pytest.exe tests/test_benchmarks_and_value.py -v -s

# Spezifische E2E-Tests gegen echte Language Server (Python pylsp & C/C++ clangd) ausführen
.\.venv\Scripts\pytest.exe tests/test_e2e_real_lsp.py -v
```

### Linter & Formatter prüfen
```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
```

### Plugin-Validierung
```powershell
agy plugin validate .
```

---

## 14. Erweiterung um neue Sprachen

Um eine neue Sprache (z. B. Rust mit `rust-analyzer` oder Go mit `gopls`) hinzuzufügen:

1. **Dateiendung mappen:** In [`paths.py`](src/agy_lsp/utils/paths.py) in `EXTENSION_LANGUAGE_MAP`:
   ```python
   ".rs": "rust",
   ".go": "go",
   ```
2. **Server-Befehl registrieren:** In [`config.py`](src/agy_lsp/config.py) unter `DEFAULT_SERVERS`:
   ```python
   "rust": ServerConfig(command="rust-analyzer", args=[]),
   "go": ServerConfig(command="gopls", args=["serve"]),
   ```
3. **Installationshinweis ergänzen:** In [`adapters.py`](src/agy_lsp/lsp/adapters.py) in `INSTALL_HINTS`.

Alternativ kann jede Sprache auch rein deklarativ in der Projektdatei `agy-lsp.json` ohne Codeänderung eingetragen werden!

---

## 15. Bekannte Einschränkungen

- **C# Roslyn:** Auf modernen .NET 10 Preview Runtimes kann `dotnet tool install -g csharp-ls` aufgrund veralteter Paketmanifeste scheitern. In diesem Fall kann der offizielle `Microsoft.CodeAnalysis.LanguageServer` in `agy-lsp.json` hinterlegt werden.
- **Mehrere Workspace-Ordner:** Derzeit unterstützt die Bridge einen primären Workspace-Root pro Session. Submodule und Unterverzeichnisse innerhalb des Workspace-Roots werden nahtlos unterstützt.
- **Semantische Makro-Expansion in C/C++:** `clangd` benötigt für optimale Ergebnisse eine `compile_commands.json` (z. B. generiert durch `cmake -DCMAKE_EXPORT_COMPILE_COMMANDS=ON`).

---

## Lizenz

Dieses Projekt ist unter der [MIT License](LICENSE) lizenziert.
