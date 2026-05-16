# 🏠 HomeRadar MCP

> Cerca immobili in Italia direttamente da Claude — in linguaggio naturale.

HomeRadar è un **MCP server** che permette a Claude di cercare annunci immobiliari su **Immobiliare.it**, **Idealista.it** e **Casa.it** con un semplice messaggio.

---

## ✨ Come funziona

Scrivi a Claude quello che cerchi:

> *"Cercami un trilocale in affitto a Milano Navigli, massimo 1.500€"*

> *"Ci sono bilocali in vendita a Roma Prati sotto i 400.000€ con ascensore?"*

> *"Trova appartamenti a Bologna, almeno 80 mq, con giardino"*

Claude risponde con annunci, prezzi, indirizzi e **link diretti** alle pagine filtrate dei portali.

---

## 🚀 Installazione rapida

### Requisiti
- [Claude Desktop](https://claude.ai/download)
- [Python 3.10+](https://python.org)
- API key Anthropic ([console.anthropic.com](https://console.anthropic.com))

### 1. Clona il repository

```bash
git clone https://github.com/simonedelvecchio93/homeradar-mcp.git
cd homeradar-mcp
```

### 2. Installa le dipendenze

```bash
pip install -r requirements.txt
```

### 3. Configura Claude Desktop

Apri il file di configurazione di Claude Desktop:

- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Mac**: `~/Library/Application Support/Claude/claude_desktop_config.json`

Aggiungi questa sezione (sostituisci il percorso e la tua API key):

```json
{
  "mcpServers": {
    "homeradar": {
      "command": "python",
      "args": ["/percorso/homeradar-mcp/server.py"],
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

### 4. Riavvia Claude Desktop

Chiudi e riapri Claude Desktop. Vedrai l'icona 🔨 attiva nella chat.

---

## 🛠️ Strumenti disponibili

### `homeradar_cerca_immobili`
Cerca annunci con filtri completi e analisi di mercato.

**Parametri:**
| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `zona` | string | Città o quartiere (es. "Milano Navigli") |
| `operazione` | vendita / affitto | Tipo di operazione |
| `tipo` | appartamento, villa, ufficio... | Tipo di immobile |
| `budget` | string | Prezzo massimo in euro |
| `superficie` | string | m² minimi |
| `locali` | monolocale...5+ | Numero locali |
| `ascensore` | bool | Richiede ascensore |
| `garage` | bool | Richiede garage |
| `giardino` | bool | Richiede giardino |
| `animali` | bool | Animali ammessi |
| `note` | string | Preferenze libere |
| `numero_risultati` | 1-10 | Quanti annunci (default 5) |
| `analisi_mercato` | bool | Analisi prezzi zona |
| `formato` | markdown / json | Formato risposta |

### `homeradar_link_portali`
Genera i link filtrati ai portali senza generare annunci.

---

## 📦 Struttura progetto

```
homeradar-mcp/
├── server.py          # MCP server principale
├── requirements.txt   # Dipendenze Python
├── smithery.yaml      # Configurazione Smithery
└── README.md
```

---

## 💶 Costi

HomeRadar usa Claude Haiku (il modello più economico di Anthropic).
Ogni ricerca costa circa **€0,001** — praticamente gratuito.

---

## 📄 Licenza

MIT — libero di usare, modificare e distribuire.

---

## 🙋 Autore

Creato da **Simone Del Vecchio**
