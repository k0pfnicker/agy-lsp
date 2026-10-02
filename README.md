# agy-lsp — Language Server Protocol MCP Bridge for Antigravity CLI

[![Tests](https://img.shields.io/badge/tests-37%20passed-brightgreen.svg)]()
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-blue.svg)]()
[![MCP](https://img.shields.io/badge/MCP-2.0%20%2F%201.0-orange.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**agy-lsp** ist ein produktionsreifes, professionelles Plugin für das **Google Antigravity CLI (`agy`)**. Es verbindet den KI-Agenten über das standardisierte **Model Context Protocol (MCP)** mit nativen **Language Servern (LSP)** für C#, C/C++, TypeScript/JavaScript und Python.

---

## Inhaltsverzeichnis

1. [Zweck und Nutzen](#zweck-und-nutzen)
2. [Architektur](#architektur)
3. [MCP-Tools im Überblick](#mcp-tools-im-%C3%BCberblick)
4. [Unterstützte Sprachen & Language Server](#unterst%C3%BCtzte-sprachen--language-server)
5. [Voraussetzungen](#voraussetzungen)
6. [Installation & Schnellstart](#installation--schnellstart)
   - [Windows](#windows)
   - [Linux / macOS](#linux--macos)
7. [Einrichtung in Antigravity CLI](#einrichtung-in-antigravity-cli)
8. [Installation der Language Server](#installation-der-language-server)
9. [Konfiguration (`agy-lsp.json`)](#konfiguration-agy-lspjson)
10. [Token-Effizienz & Kontext-Optimierung](#token-effizienz--kontext-optimierung)
11. [Sicherheitsmodell](#sicherheitsmodell)
12. [Troubleshooting & Diagnose](#troubleshooting--diagnose)
13. [Entwicklung, Tests & Qualitätssicherung](#entwicklung-tests--qualit%C3%A4tssicherung)
14. [Erweiterung um neue Sprachen](#erweiterung-um-neue-sprachen)
15. [Bekannte Einschränkungen](#bekannte-einschr%C3%A4nkungen)

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
| `go_to_definition` | Springt von einer Position zur Deklaration/Definition | `file_path`, `line`, `character`, `include_snippet` | Zieldatei, Zeilenbereich, optionaler kompakter Code-Ausschnitt. |
| `find_references` | Findet alle Verwendungsstellen eines Symbols | `file_path`, `line`, `character`, `include_declaration`, `limit` | Liste aller Referenzen im Workspace. |
| `rename_symbol` | Führt ein symbolweites Umbenennen via LSP durch | `file_path`, `line`, `character`, `new_name`, `apply` | **Preview-Diff** aller betroffenen Dateien. Schreiben auf Festplatte erfordert `apply=True` und `writeChanges=True`. |
| `document_symbols` | Liefert hierarchische Gliederung (Klassen, Methoden, Felder) | `file_path`, `query` | Symbolbaum mit Art, Zeilenbereich und Bezeichnern. |
| `workspace_symbols` | Durchsucht das gesamte Projekt nach Symbolen | `query`, `limit` | Trefferliste mit Name, Symbol-Art, Datei und Position. |
| `hover` | Zeigt Signaturen, Typen und Docstrings | `file_path`, `line`, `character` | Markdown-formatiertes Hover-Ergebnis. |
| `prepare_call_hierarchy` | Prüft Unterstützung und liefert Call-Hierarchy-Item | `file_path`, `line`, `character` | Vorbereitetes Symbol für den Aufrufbaum. |
| `call_hierarchy` | Ermittelt Aufrufer (`incoming`) oder aufgerufene Methoden (`outgoing`) | `file_path`, `line`, `character`, `direction` | Liste der Aufrufer bzw. Unterfunktionen. |
| `get_type_hierarchy` | Liefert Basistypen (`supertypes`) oder Subklassen (`subtypes`) | `file_path`, `line`, `character`, `direction` | Vererbungshierarchie des Typs. |
| `lsp_status` | Status aller Server, Workspace-Root und Fehler | *keine* | JSON-Übersicht mit Server-Zustand (`RUNNING`, `AVAILABLE`, `NOT_INSTALLED`, `CRASHED`), PID und Pfad. |

*Hinweis:* Zeilen- und Spaltenangaben in allen Tool-Parametern und Rückgaben sind **1-basiert** für eine intuitive Interaktion mit dem Agenten.

---

## 4. Unterstützte Sprachen & Language Server

| Sprache | Primärer Server | Erkannte Dateiendungen | Projekt-Erkennungsmarker |
| :--- | :--- | :--- | :--- |
| **Python** | `pyright-langserver` *(Fallback: `pylsp`, `pyright`)* | `.py`, `.pyi` | `pyproject.toml`, `setup.py`, `requirements.txt` |
| **C#** | `csharp-ls` *(Fallback: `roslyn-language-server`)* | `.cs` | `*.sln`, `*.csproj` |
| **C / C++** | `clangd` *(Fallback: `ccls`)* | `.c`, `.cpp`, `.cc`, `.cxx`, `.h`, `.hpp`, `.hxx` | `CMakeLists.txt`, `compile_commands.json` |
| **TypeScript / JS**| `typescript-language-server` *(Fallback: `vtsls`)* | `.ts`, `.tsx`, `.js`, `.jsx`, `.mjs`, `.cjs` | `package.json`, `tsconfig.json` |

---

## 5. Voraussetzungen

- **Betriebssystem:** Windows 10/11, macOS oder Linux.
- **Python:** Python 3.9 oder neuer (Python 3.14+ vollständig unterstützt).
- **Antigravity CLI:** `agy` installiert.
- Der jeweilige Language Server für die zu bearbeitende Sprache (z. B. `pylsp` oder `pyright` für Python, `clangd` für C++, etc.).

---

## 6. Installation & Schnellstart

### Windows

```powershell
# 1. In das Plugin-Verzeichnis wechseln
cd path/to/agy-lsp

# 2. Virtuelle Umgebung anlegen und Abhängigkeiten installieren
python -m venv .venv
.\.venv\Scripts\pip.exe install -e .

# 3. Optional: Python-LSP-Server für sofortige Python-Unterstützung installieren
.\.venv\Scripts\pip.exe install python-lsp-server
```

### Linux / macOS

```bash
cd /path/to/AG_LSP_Plugin
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install python-lsp-server
```

---

## 7. Einrichtung in Antigravity CLI

Es gibt zwei einfache Möglichkeiten, das Plugin in Antigravity CLI zu registrieren:

### Option A: Als Workspace- oder Globales Plugin (Empfohlen)

Das Plugin erfüllt die offizielle Manifest-Spezifikation (`plugin.json` und `mcp_config.json`).

Kopieren oder verlinken Sie das Verzeichnis in Ihren Antigravity-Plugin-Ordner:
- **Global:** `~/.gemini/config/plugins/agy-lsp`
- **Projekt-spezifisch:** `.agents/plugins/agy-lsp`

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

### Option B: Über die `agy mcp`-Befehlszeile

Sie können den MCP-Server auch direkt registrieren:
```bash
agy mcp add agy-lsp -- command="python" args=["/path/to/agy-lsp/run_server.py"]
```

---

## 8. Installation der Language Server

Sollte ein Language Server nicht auf Ihrem System vorhanden sein, liefert das Plugin eine klare, strukturierte Meldung mit der exakten Installationsanweisung:

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

### Test-Suite ausführen

Die gesamte Testsuite umfasst 37 automatisierte Unit-, Integrations- und End-to-End-Tests:

```powershell
# Alle Tests ausführen
.\.venv\Scripts\pytest.exe -v

# Spezifischen E2E-Test gegen einen echten Language Server ausführen
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
