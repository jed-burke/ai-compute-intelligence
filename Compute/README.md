# AI Compute Intelligence System

An open-source intelligence platform for analyzing global AI compute infrastructure — data centers, chip supply chains, export controls, and strategic dependencies across frontier AI organizations.

Built on a RAG (Retrieval-Augmented Generation) architecture that grounds every analysis in primary research rather than model training data.

---

## What it does

**🔍 RAG Analysis** — Ask natural-language questions against an indexed corpus of primary research (RAND, CSET, Berkeley, DHS, AI Index 2026, and more). Every answer cites its sources.

**🏢 Company Dashboard** — Structured intelligence on 12 frontier AI organizations across the US, PRC, and EU. Interactive map, milestone timeline, risk matrix, and company deep dives — each with a live RAG query against the research corpus.

**🔮 Scenario Forge** — A causal impact model that projects how changes in compute access, export controls, geopolitical tension, funding, and model releases shift the competitive landscape. Outputs include:
- Before/after capability rankings
- Risk matrix with movement arrows
- Spider charts per company
- Research-grounded narrative assessment via Claude
- Bayesian confidence scoring that degrades as scenario magnitude grows

All views export to formatted Word reports.

---

## Companies tracked

| Company | Region | Focus |
|---|---|---|
| OpenAI | 🇺🇸 US | GPT-4o, o3, Sora |
| Anthropic | 🇺🇸 US | Claude series |
| Google DeepMind | 🇺🇸/🇬🇧 US | Gemini, AlphaFold |
| Meta AI | 🇺🇸 US | Llama (open source) |
| xAI | 🇺🇸 US | Grok, Colossus cluster |
| Mistral AI | 🇪🇺 EU | Mistral, Mixtral |
| Baidu | 🇨🇳 PRC | ERNIE, Kunlun chip |
| Alibaba (Qwen) | 🇨🇳 PRC | Qwen series |
| ByteDance | 🇨🇳 PRC | Doubao |
| DeepSeek | 🇨🇳 PRC | R1, V3 |
| Huawei | 🇨🇳 PRC | Ascend chip, PanGu |
| Zhipu AI | 🇨🇳 PRC | GLM-4, CogVideoX |

---

## Architecture

```
research/          ← Your PDF corpus (not included — add your own)
data/
  chroma/          ← ChromaDB vector store (built locally on first run)
  companies.json   ← Baseline company dataset
src/
  app.py           ← Streamlit UI (three tabs)
  ingest.py        ← PDF extraction, chunking, ChromaDB indexing
  fetch.py         ← RSS + web scraping for live sources
  rag.py           ← Retrieval + Claude API integration
  dashboard.py     ← Company dashboard visualizations
  scenario.py      ← Causal impact model + scenario engine
```

**Stack:** Python · Streamlit · ChromaDB · sentence-transformers · Claude API · Plotly · pdfplumber · trafilatura

---

## Setup

**1. Clone the repo**
```bash
git clone https://github.com/YOUR_USERNAME/ai-compute-intelligence.git
cd ai-compute-intelligence
```

**2. Install dependencies**
```bash
pip install -r requirements.txt
```

**3. Add your Anthropic API key**
```bash
cp .env.template .env
# Edit .env and add your key from console.anthropic.com
```

**4. Add research PDFs**

Place PDF reports in the `research/` folder. The system is designed around open-source and commercial AI infrastructure research — RAND, CSET, Brookings, DHS, AI Index, Berkeley, etc.

**5. Launch**
```bash
streamlit run src/app.py
```

Then click **"Index Research Library"** in the sidebar on first run (~2 minutes).

---

## Live web sources

The system pulls automatically from:

- MIT Technology Review
- Epoch AI
- RAND Corporation
- Brookings Institution
- CSET Georgetown
- CNAS
- MLCommons
- Exxact Corp
- CoreWeave
- SemiAnalysis

Click **"Fetch Latest Articles"** in the sidebar, or enable auto-fetch on a schedule.

---

## Scenario presets

| Scenario | Description |
|---|---|
| Export Controls Tightened | BIS restrictions expand; PRC compute access drops |
| PRC Achieves Compute Parity | Huawei Ascend reaches H100-level performance |
| US–China Détente | Diplomatic reset eases technology friction |
| Open Source Surge | Major open-weight releases reshape competitive dynamics |
| Global Chip Supply Crunch | TSMC disruption hits all labs |
| Frontier Capability Leap (US) | Qualitative capability jump widens US lead |

---

## Notes

- All company scores (capability, risk dimensions) are analyst estimates based on publicly available information
- Confidence scores apply Bayesian prior dilution — uncertainty grows with scenario magnitude
- No proprietary or classified data is used
- Research corpus must be supplied by the user

---

## Related

**[CTI Intelligence Platform](https://github.com/jed-burke/cti-intelligence-platform)** — A companion project covering cyber threat intelligence, AI risk, and compute competition via daily/weekly feed collection, AI-generated analyst notes, and a structured briefing portal.

---

*Built with [Claude](https://claude.ai) · [Anthropic API](https://docs.anthropic.com)*
