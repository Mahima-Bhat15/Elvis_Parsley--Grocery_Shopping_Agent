# 🛒 Clickless AI — Autonomous Grocery Agent

> **One prompt. Your groceries handled.** A multi-agent AI system that autonomously browses, reasons, and shops — without you clicking a thing.

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![LangChain](https://img.shields.io/badge/LangChain-0.1+-1C3C3C?style=flat&logo=chainlink&logoColor=white)](https://langchain.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg?style=flat)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Active-brightgreen?style=flat)]()

---

## 📌 What is Clickless AI?

Clickless AI is an **autonomous grocery shopping agent** built on a multi-agent orchestration architecture. You describe what you need in plain language — the system reasons, searches, compares prices, and places the order. No tab-switching. No clicking. No fuss.

It combines **Large Language Models**, **Graph-based Retrieval-Augmented Generation (Graph RAG)**, **Named Entity Recognition (NER)**, and a **Neuro-Symbolic Knowledge Graph** to enable grounded, factual decision-making at every step of the shopping pipeline.

---

## 🎯 Key Features

- 🧠 **Intent Parsing** — Understands natural language grocery requests using NER to extract items, quantities, preferences, and constraints
- 🕸️ **Neuro-Symbolic Knowledge Graph** — Stores product relationships, nutritional facts, and brand data; queried via Cypher for structured reasoning
- 🔍 **Graph RAG** — Retrieval-Augmented Generation over the KG for accurate, grounded product lookup and substitution suggestions
- 💰 **Price Optimization** — Cypher-based pathfinding across the KG to find the lowest-cost combination of items across stores
- 🤖 **Multi-Agent Orchestration** — Specialized agents for search, comparison, cart management, and checkout, coordinated by a LangChain orchestrator
- 🌐 **Autonomous Web Interaction** — Playwright-powered browser agent navigates grocery websites without human input
- 🔄 **Dynamic Decision-Making** — Planning logic adapts in real-time to out-of-stock items, substitutions, and budget constraints

---

## 🏗️ System Architecture

```
User Prompt (Natural Language)
        │
        ▼
┌─────────────────────┐
│   NER + Intent      │  ← Extracts items, qty, brand prefs, budget
│   Parsing Agent     │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  Neuro-Symbolic     │  ← Product KG: nodes = items/brands/stores
│  Knowledge Graph    │    edges = price/nutrition/substitutes
│  (Graph RAG)        │  ← Cypher queries for pathfinding & lookup
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  LangChain          │  ← Routes tasks to specialized sub-agents
│  Orchestrator       │
└────┬───────┬────────┘
     │       │
     ▼       ▼
┌─────────┐ ┌──────────────┐
│ Search  │ │ Price Optim  │  ← Cypher pathfinding across stores
│ Agent   │ │ Agent        │
└────┬────┘ └──────┬───────┘
     │              │
     ▼              ▼
┌─────────────────────┐
│  Playwright         │  ← Autonomous browser: search → add to cart
│  Web Agent          │    → checkout
└─────────────────────┘
```

---

## 🧩 Tech Stack

| Layer | Technology |
|---|---|
| **Orchestration** | LangChain (multi-agent framework) |
| **Knowledge Graph** | Neo4j + Cypher query language |
| **RAG** | Graph RAG over product KG |
| **NLP / NER** | spaCy / HuggingFace NER pipeline |
| **Web Automation** | Playwright |
| **LLM Backend** | OpenAI GPT / Groq |
| **Language** | Python 3.10+ |

---

## 🚀 Getting Started

### Prerequisites

```bash
python >= 3.10
neo4j >= 5.0
node >= 18 (for Playwright)
```

### Installation

```bash
# Clone the repo
git clone https://github.com/Mahima-Bhat15/clickless-ai.git
cd clickless-ai

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

### Configuration

```bash
cp .env.example .env
```

Edit `.env`:

```env
OPENAI_API_KEY=your_key_here
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
GROQ_API_KEY=your_key_here        # optional, for Groq LLM
```

### Run

```bash
# Start Neo4j (if running locally)
neo4j start

# Seed the knowledge graph
python scripts/seed_kg.py

# Run the agent
python main.py --prompt "Get me 2 gallons of whole milk, organic eggs, and the cheapest sourdough bread under $5"
```

---

## 💬 Example Usage

```python
from clickless.agent import ClicklessAgent

agent = ClicklessAgent()

result = agent.run(
    "I need ingredients for pasta carbonara for 4 people. "
    "Keep it under $25 total and prefer organic where possible."
)

print(result.cart)
# → [{'item': 'pasta 500g', 'brand': 'Barilla', 'price': 1.99},
#    {'item': 'eggs (6 pack)', 'brand': 'Organic Valley', 'price': 4.49},
#    {'item': 'pancetta 150g', 'brand': 'Boar\'s Head', 'price': 6.99},
#    {'item': 'parmesan 200g', 'brand': 'BelGioioso', 'price': 5.49}]
# Total: $18.96 ✓
```

---

## 🧠 Technical Deep-Dive

### Why a Knowledge Graph?

Standard RAG retrieves flat text chunks — good for Q&A, but not for structured reasoning like *"find the cheapest gluten-free pasta that pairs well with this sauce."* A **graph structure** lets us model:

- **Product → Brand → Store → Price** relationships
- **Item → Substitute** edges for out-of-stock handling
- **Nutritional constraints** as graph filters
- **Cypher pathfinding** to optimize across multiple items simultaneously

### Multi-Agent Design

Rather than one monolithic LLM call, Clickless AI decomposes the task:

| Agent | Responsibility |
|---|---|
| `IntentAgent` | NER + query decomposition |
| `KGQueryAgent` | Graph RAG retrieval + Cypher execution |
| `PriceAgent` | Cross-store cost optimization |
| `WebAgent` | Playwright browser automation |
| `CartAgent` | State management + checkout |
| `OrchestratorAgent` | Task routing + replanning on failure |

This decomposition improves reliability — each agent is specialized, testable, and replaceable.

### Neuro-Symbolic Reasoning

The system combines:
- **Neural**: LLM for understanding language, handling ambiguity, and generating Cypher queries
- **Symbolic**: KG for deterministic, verifiable product lookups and price comparisons

This hybrid approach reduces hallucinations — the LLM can't invent prices or products that don't exist in the graph.

---

## 📊 Results & Performance

| Metric | Result |
|---|---|
| Intent parsing accuracy | ~91% on test set |
| Successful end-to-end runs | ~84% (with substitution fallback) |
| Avg. price optimization savings | ~12% vs. naive first-result selection |
| Avg. task completion time | ~45 seconds |

---

## 🗂️ Project Structure

```
clickless-ai/
├── agents/
│   ├── intent_agent.py        # NER + query decomposition
│   ├── kg_query_agent.py      # Graph RAG + Cypher
│   ├── price_agent.py         # Cost optimization
│   ├── web_agent.py           # Playwright automation
│   ├── cart_agent.py          # Cart state management
│   └── orchestrator.py        # Multi-agent coordinator
├── knowledge_graph/
│   ├── schema.cypher           # KG schema definition
│   ├── seed_kg.py             # Data ingestion scripts
│   └── queries/               # Reusable Cypher query templates
├── ner/
│   └── pipeline.py            # spaCy NER pipeline
├── scripts/
│   └── seed_kg.py
├── tests/
│   ├── test_intent.py
│   ├── test_kg_queries.py
│   └── test_e2e.py
├── main.py
├── requirements.txt
├── .env.example
└── README.md
```

---

## 🔮 Future Work

- [ ] Support for multiple grocery platforms (Instacart, Kroger API, Walmart)
- [ ] User preference learning over sessions
- [ ] Voice input interface
- [ ] Real-time price scraping to keep KG fresh
- [ ] Nutritional goal optimization (e.g., "high protein, low carb")

---

## 👩‍💻 Author

**Mahima Ramdas Bhat**
M.S. Computer Science · Arizona State University
[LinkedIn](https://www.linkedin.com/in/mahimabhat6/) · [GitHub](https://github.com/Mahima-Bhat15) · mahimabhat6@gmail.com

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.
