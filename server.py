#!/usr/bin/env python3
"""
HomeRadar MCP Server

Ricerca immobiliare italiana con AI — cerca su Immobiliare.it, Idealista.it e Casa.it
e restituisce annunci realistici con link diretti alle pagine filtrate dei portali.
"""

import os
import re
import json
import unicodedata
import httpx
from typing import Optional
from enum import Enum
from pydantic import BaseModel, Field, field_validator, ConfigDict
from mcp.server.fastmcp import FastMCP

# ── Inizializzazione server ──────────────────────────────────────────────────
mcp = FastMCP("homeradar_mcp")

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL             = "claude-haiku-4-5-20251001"


# ── Enums ────────────────────────────────────────────────────────────────────
class Operazione(str, Enum):
    VENDITA = "vendita"
    AFFITTO = "affitto"

class TipoImmobile(str, Enum):
    APPARTAMENTO  = "appartamento"
    VILLA         = "villa o casa indipendente"
    UFFICIO       = "ufficio"
    NEGOZIO       = "locale commerciale"
    GARAGE        = "garage o box auto"
    TERRENO       = "terreno edificabile"
    CAPANNONE     = "capannone"

class Locali(str, Enum):
    QUALSIASI    = ""
    MONOLOCALE   = "monolocale"
    BILOCALE     = "bilocale"
    TRILOCALE    = "trilocale"
    QUATTRO_PLUS = "almeno 4 locali"
    CINQUE_PLUS  = "almeno 5 locali"

class FormatoRisposta(str, Enum):
    MARKDOWN = "markdown"
    JSON     = "json"


# ── Input model ──────────────────────────────────────────────────────────────
class CercaImmobiliInput(BaseModel):
    """Parametri di ricerca immobiliare."""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    zona: str = Field(
        ...,
        description="Città o zona da cercare (es. 'Milano Navigli', 'Roma Prati', 'Bologna centro')",
        min_length=2, max_length=100
    )
    operazione: Operazione = Field(
        default=Operazione.VENDITA,
        description="Tipo di operazione: 'vendita' o 'affitto'"
    )
    tipo: TipoImmobile = Field(
        default=TipoImmobile.APPARTAMENTO,
        description="Tipo di immobile da cercare"
    )
    budget: Optional[str] = Field(
        default=None,
        description="Budget massimo in euro (es. '300000' o '300.000' per vendita, '1500' per affitto)"
    )
    superficie: Optional[str] = Field(
        default=None,
        description="Superficie minima in m² (es. '80')"
    )
    locali: Locali = Field(
        default=Locali.QUALSIASI,
        description="Numero minimo di locali"
    )
    ascensore: bool = Field(default=False, description="Richiede ascensore")
    garage:    bool = Field(default=False, description="Richiede garage o posto auto")
    giardino:  bool = Field(default=False, description="Richiede giardino o terrazzo")
    animali:   bool = Field(default=False, description="Animali domestici ammessi")
    note:      Optional[str] = Field(
        default=None,
        description="Preferenze aggiuntive in linguaggio libero (es. 'piano alto, ristrutturato')",
        max_length=200
    )
    numero_risultati: int = Field(
        default=5,
        description="Quanti annunci restituire (da 1 a 10)",
        ge=1, le=10
    )
    analisi_mercato: bool = Field(
        default=False,
        description="Se True include un'analisi del prezzo medio al m² e del trend di mercato della zona"
    )
    formato: FormatoRisposta = Field(
        default=FormatoRisposta.MARKDOWN,
        description="Formato risposta: 'markdown' (leggibile) o 'json' (strutturato)"
    )

    @field_validator("budget")
    @classmethod
    def normalizza_budget(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return re.sub(r"[^\d]", "", v)

    @field_validator("superficie")
    @classmethod
    def normalizza_superficie(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return re.sub(r"[^\d]", "", v)


# ── Utility: costruisce URL portali con filtri ────────────────────────────────
def _slugify(testo: str) -> str:
    """Converte testo in slug URL-safe (rimuove accenti, spazi → trattini)."""
    nfkd = unicodedata.normalize("NFKD", testo)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_str.lower()).strip("-")


def _build_portal_urls(p: CercaImmobiliInput) -> list[dict]:
    """Genera URL filtrati per Immobiliare.it, Idealista.it e Casa.it."""
    zona = _slugify(p.zona)
    op   = p.operazione.value

    # ── Immobiliare.it ──────────────────────────────────
    immo_path_map = {
        TipoImmobile.APPARTAMENTO: f"{op}-case",
        TipoImmobile.VILLA:        f"{op}-ville",
        TipoImmobile.UFFICIO:      f"{op}-uffici",
        TipoImmobile.NEGOZIO:      f"{op}-negozi",
        TipoImmobile.GARAGE:       "vendita-garage",
        TipoImmobile.TERRENO:      "vendita-terreni",
        TipoImmobile.CAPANNONE:    "vendita-capannoni",
    }
    immo_path = immo_path_map.get(p.tipo, f"{op}-case")

    immo_q: dict[str, str] = {}
    if p.budget:     immo_q["prezzoMassimo"]   = p.budget
    if p.superficie: immo_q["superficieMinima"] = p.superficie
    locali_immo = {
        Locali.MONOLOCALE:   ("1", "1"),
        Locali.BILOCALE:     ("2", "2"),
        Locali.TRILOCALE:    ("3", "3"),
        Locali.QUATTRO_PLUS: ("4", None),
        Locali.CINQUE_PLUS:  ("5", None),
    }
    if p.locali in locali_immo:
        mn, mx = locali_immo[p.locali]
        immo_q["localiMinimo"] = mn
        if mx: immo_q["localiMassimo"] = mx
    if p.ascensore: immo_q["ascensore"] = "1"
    if p.garage:    immo_q["box"]       = "1"
    if p.giardino:  immo_q["giardino"]  = "1"
    if p.animali:   immo_q["animaliAmmessi"] = "1"

    immo_qs = ("?" + "&".join(f"{k}={v}" for k, v in immo_q.items())) if immo_q else ""

    # ── Idealista.it ────────────────────────────────────
    idea_type_map = {
        TipoImmobile.APPARTAMENTO: "abitazioni",
        TipoImmobile.VILLA:        "abitazioni",
        TipoImmobile.UFFICIO:      "uffici",
        TipoImmobile.NEGOZIO:      "locali-commerciali",
        TipoImmobile.GARAGE:       "garage-e-box",
        TipoImmobile.TERRENO:      "terreni",
        TipoImmobile.CAPANNONE:    "capannoni",
    }
    idea_type = idea_type_map.get(p.tipo, "abitazioni")
    idea_q: dict[str, str] = {}
    if p.budget:     idea_q["prezzo_massimo"]    = p.budget
    if p.superficie: idea_q["superficie_minima"] = p.superficie
    locali_idea = {
        Locali.MONOLOCALE: "1", Locali.BILOCALE: "2",
        Locali.TRILOCALE:  "3", Locali.QUATTRO_PLUS: "4", Locali.CINQUE_PLUS: "5",
    }
    if p.locali in locali_idea: idea_q["stanze"] = locali_idea[p.locali]
    idea_qs = ("?" + "&".join(f"{k}={v}" for k, v in idea_q.items())) if idea_q else ""

    # ── Casa.it ─────────────────────────────────────────
    casa_type_map = {
        TipoImmobile.APPARTAMENTO: "appartamento",
        TipoImmobile.VILLA:        "villa",
        TipoImmobile.UFFICIO:      "ufficio",
        TipoImmobile.NEGOZIO:      "negozio",
        TipoImmobile.GARAGE:       "garage",
        TipoImmobile.TERRENO:      "terreno",
        TipoImmobile.CAPANNONE:    "capannone",
    }
    casa_type = casa_type_map.get(p.tipo, "appartamento")
    casa_q: dict[str, str] = {}
    if p.budget:     casa_q["prezzo_max"]        = p.budget
    if p.superficie: casa_q["superficie_minima"] = p.superficie
    casa_qs = ("?" + "&".join(f"{k}={v}" for k, v in casa_q.items())) if casa_q else ""

    return [
        {"portale": "Immobiliare.it", "url": f"https://www.immobiliare.it/{immo_path}/{zona}/{immo_qs}"},
        {"portale": "Idealista.it",   "url": f"https://www.idealista.it/{op}-{idea_type}/{zona}/{idea_qs}"},
        {"portale": "Casa.it",        "url": f"https://www.casa.it/{op}/{casa_type}/{zona}/{casa_qs}"},
    ]


def _build_query(p: CercaImmobiliInput) -> str:
    """Costruisce la query in linguaggio naturale per Claude."""
    q = f"Genera {p.numero_risultati} annunci immobiliari realistici di {p.tipo.value} in {p.operazione.value} a {p.zona}"
    if p.budget:     q += f", budget massimo {p.budget} euro"
    if p.superficie: q += f", superficie minima {p.superficie} m²"
    if p.locali.value: q += f", {p.locali.value}"
    if p.ascensore:  q += ", con ascensore"
    if p.garage:     q += ", con garage o posto auto"
    if p.giardino:   q += ", con giardino o terrazzo"
    if p.animali:    q += ", animali ammessi"
    if p.note:       q += f". Note: {p.note}"
    return q


async def _chiedi_claude(query: str, analisi: bool, zona: str) -> dict:
    """Chiama Claude Haiku e restituisce il JSON parsato."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY non impostata nell'ambiente")

    analisi_field = (
        f'"analisi_mercato":"analisi prezzi medi al m² e trend mercato a {zona}"'
        if analisi else '"analisi_mercato":""'
    )
    system = (
        "Sei un esperto immobiliare italiano. Genera annunci con prezzi realistici, "
        "indirizzi plausibili (strade reali della città) e descrizioni concrete. "
        "Rispondi SOLO con JSON valido, zero markdown, zero testo aggiuntivo:\n"
        '{"results":[{"titolo":"","prezzo":"€XXX.XXX","superficie":"XX m²",'
        '"locali":"Bilocale","indirizzo":"Via reale, N","descrizione":"max 90 car",'
        f'"prezzo_mq":"X.XXX €/m²"}}],"sommario":"riepilogo breve",{analisi_field}}}'
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            ANTHROPIC_API_URL,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": MODEL,
                "max_tokens": 2000,
                "system": system,
                "messages": [{"role": "user", "content": query}],
            },
        )
        resp.raise_for_status()

    data = resp.json()
    testo = "".join(b["text"] for b in data.get("content", []) if b["type"] == "text")
    testo = re.sub(r"```json|```", "", testo).strip()

    try:
        return json.loads(testo)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", testo)
        if match:
            return json.loads(match.group())
        raise ValueError("Claude non ha restituito JSON valido")


def _formatta_markdown(risultati: list[dict], portali: list[dict],
                       sommario: str, analisi: str, params: CercaImmobiliInput) -> str:
    """Formatta i risultati in Markdown leggibile."""
    lines = [
        f"# 🏠 HomeRadar — {params.tipo.value.capitalize()} in {params.operazione.value} a {params.zona}",
        "",
    ]
    if sommario:
        lines += [f"> {sommario}", ""]

    for i, (annuncio, portale) in enumerate(zip(risultati, portali * 10), 1):
        lines += [
            f"## {i}. {annuncio.get('titolo', 'Annuncio immobiliare')}",
            f"📍 **{annuncio.get('indirizzo', '—')}**",
            f"💶 **{annuncio.get('prezzo', 'N.d.')}**"
            + (f" · {annuncio.get('prezzo_mq', '')} /m²" if annuncio.get("prezzo_mq") else ""),
            f"📐 {annuncio.get('superficie', '—')} · {annuncio.get('locali', '—')}",
            f"📝 {annuncio.get('descrizione', '')}",
            f"🔗 [Vedi su {portale['portale']}]({portale['url']})",
            "",
        ]

    lines += ["---", "## 🔎 Cerca direttamente sui portali", ""]
    for p in portali:
        lines.append(f"- [{p['portale']}]({p['url']})")

    if analisi:
        lines += ["", "---", "## 📊 Analisi di mercato", "", analisi]

    return "\n".join(lines)


# ── Tool principale ───────────────────────────────────────────────────────────
@mcp.tool(
    name="homeradar_cerca_immobili",
    annotations={
        "title": "Cerca Immobili in Italia",
        "readOnlyHint":    True,
        "destructiveHint": False,
        "idempotentHint":  False,
        "openWorldHint":   True,
    },
)
async def homeradar_cerca_immobili(params: CercaImmobiliInput) -> str:
    """Cerca immobili in vendita o affitto in Italia su Immobiliare.it, Idealista.it e Casa.it.

    Genera annunci realistici con prezzi di mercato, indirizzi verosimili e link
    diretti alle pagine di ricerca filtrate dei portali principali.

    Args:
        params (CercaImmobiliInput): Parametri di ricerca:
            - zona (str): Città o quartiere (es. "Milano Navigli", "Roma Prati")
            - operazione: "vendita" o "affitto"
            - tipo: appartamento, villa, ufficio, negozio, garage, terreno, capannone
            - budget (str, opz.): Prezzo massimo in euro (es. "300000")
            - superficie (str, opz.): m² minimi (es. "80")
            - locali: monolocale, bilocale, trilocale, 4+, 5+
            - ascensore, garage, giardino, animali (bool)
            - note (str, opz.): Preferenze libere
            - numero_risultati: 1-10 (default 5)
            - analisi_mercato (bool): Analisi prezzi zona
            - formato: "markdown" o "json"

    Returns:
        str: Lista annunci con prezzi, indirizzi, caratteristiche e link portali.

    Esempi d'uso:
        - "Cerca bilocale affitto Milano Navigli max 1200€"
        - "Trovami un trilocale in vendita a Roma, budget 400000, con ascensore"
        - "Appartamenti in vendita a Bologna superficie min 90mq"
    """
    try:
        portali   = _build_portal_urls(params)
        query     = _build_query(params)
        dati      = await _chiedi_claude(query, params.analisi_mercato, params.zona)

        risultati = dati.get("results", [])
        sommario  = dati.get("sommario", "")
        analisi   = dati.get("analisi_mercato", "")

        # Assegna portali ciclicamente
        for i, r in enumerate(risultati):
            r["portale"] = portali[i % len(portali)]["portale"]
            r["url"]     = portali[i % len(portali)]["url"]

        if params.formato == FormatoRisposta.JSON:
            return json.dumps({
                "zona":     params.zona,
                "operazione": params.operazione.value,
                "tipo":     params.tipo.value,
                "risultati": risultati,
                "sommario": sommario,
                "analisi_mercato": analisi,
                "portali":  portali,
            }, ensure_ascii=False, indent=2)

        return _formatta_markdown(risultati, portali, sommario, analisi, params)

    except ValueError as e:
        return f"❌ Errore configurazione: {e}"
    except httpx.HTTPStatusError as e:
        codice = e.response.status_code
        if codice == 401:
            return "❌ API key Anthropic non valida. Controlla la variabile ANTHROPIC_API_KEY."
        if codice == 429:
            return "❌ Limite richieste Claude raggiunto. Riprova tra qualche minuto."
        return f"❌ Errore API Claude ({codice}). Riprova più tardi."
    except httpx.TimeoutException:
        return "❌ Timeout: Claude non ha risposto in tempo. Riprova."
    except Exception as e:
        return f"❌ Errore inatteso: {type(e).__name__}: {e}"


# ── Tool: genera solo i link portali ─────────────────────────────────────────
@mcp.tool(
    name="homeradar_link_portali",
    annotations={
        "title": "Genera link di ricerca sui portali immobiliari",
        "readOnlyHint":    True,
        "destructiveHint": False,
        "idempotentHint":  True,
        "openWorldHint":   False,
    },
)
async def homeradar_link_portali(params: CercaImmobiliInput) -> str:
    """Genera i link diretti alle pagine di ricerca filtrata su Immobiliare.it, Idealista.it e Casa.it.

    Non chiama Claude — restituisce solo gli URL con i filtri applicati.
    Utile quando l'utente vuole cercare da solo sui portali senza annunci generati.

    Args:
        params (CercaImmobiliInput): Stessi parametri di homeradar_cerca_immobili.

    Returns:
        str: Link formattati per ogni portale con i filtri applicati.
    """
    try:
        portali = _build_portal_urls(params)
        op      = params.operazione.value
        tipo    = params.tipo.value

        lines = [
            f"## 🔗 Cerca {tipo} in {op} a {params.zona}",
            "",
            "Clicca su un portale per vedere gli annunci con i tuoi filtri:",
            "",
        ]
        filtri = []
        if params.budget:       filtri.append(f"Budget max: €{params.budget}")
        if params.superficie:   filtri.append(f"Superficie min: {params.superficie} m²")
        if params.locali.value: filtri.append(f"Locali: {params.locali.value}")
        if params.ascensore:    filtri.append("Con ascensore")
        if params.garage:       filtri.append("Con garage")
        if params.giardino:     filtri.append("Con giardino")
        if params.animali:      filtri.append("Animali ammessi")

        if filtri:
            lines += ["**Filtri applicati:** " + " · ".join(filtri), ""]

        for p in portali:
            lines.append(f"🏠 [{p['portale']}]({p['url']})")

        return "\n".join(lines)

    except Exception as e:
        return f"❌ Errore: {e}"


# ── Avvio ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "http":
        mcp.settings.host = "0.0.0.0"
        mcp.settings.port = int(os.environ.get("PORT", 8000))
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
