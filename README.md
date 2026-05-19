# Shopping Search Agent (SerpApi-powered)

Production-style AI shopping agent that converts natural-language shopping requests into ranked shopping links using SerpApi Google results metadata.

## Acknowledgment

This project was influenced by [Hoanganhvu123/ShoppingGPT](https://github.com/Hoanganhvu123/ShoppingGPT), especially the idea of combining shopping-focused routing and chat-oriented UX.

## Guarantees

- Uses SerpApi (`SERP_API_KEY`) for Google organic results.
- Uses only public metadata (`title`, `snippet`, `url`, `domain`).
- No scraping, no browser automation, no marketplace APIs, no product DB.
- LLM is used for understanding/routing/explanation only.

## Architecture

1. **Semantic Router**: classify `shopping` vs `chitchat`.
2. **Shopping Agent**:
   - Intent Parser
   - Query Generator (generic + `site:` scoped)
   - Search Retriever (SerpApi)
   - Ranking & Filtering (dedupe + spam penalties + trusted-domain preference)
   - Explanation Layer (non-hallucinated rationale)
3. **Output** (unified response schema via `to_public_response()`):
   - `version` — schema version (currently `"1"`)
   - `route` — `shopping` or `chitchat`
   - `query` — user request text
   - `constraints` — parsed shopping constraints (product type, budget, brands, must/nice-to-have, attributes)
   - `market` — `country_code`, `language`, `location`
   - `parse` — `status`, `confidence`, `needs_clarification`, `warnings`, `errors`
   - `shortlist` — ranked product links (0–N items)
   - `message` — human-readable summary for UI/clients (chat fills this for display)
   - `disclaimer` — price/stock verification note

Example response:

```json
{
  "version": "1",
  "route": "shopping",
  "query": "waterproof running shoes under $120",
  "constraints": {
    "product_type": "running shoes",
    "attributes": {"waterproof": "true"},
    "brand_include": [],
    "brand_exclude": [],
    "must_have": ["waterproof"],
    "nice_to_have": [],
    "budget": "under $120",
    "budget_amount": 120,
    "budget_currency": "USD",
    "usage": null
  },
  "market": {
    "country_code": "tr",
    "language": "tr",
    "location": null
  },
  "parse": {
    "status": "ok",
    "confidence": 0.85,
    "needs_clarification": false,
    "warnings": [],
    "errors": []
  },
  "shortlist": [
    {
      "title": "Example Shoe",
      "url": "https://www.trendyol.com/example",
      "domain": "trendyol.com",
      "merchant": "Trendyol",
      "price": "₺2,999",
      "extracted_price": 2999,
      "price_currency": "TRY",
      "in_stock": true,
      "explanation": "Matches waterproof running shoes in your budget range."
    }
  ],
  "message": "I found 3 options for running shoes (...).",
  "disclaimer": "Prices and stock are based on retailer search metadata at query time..."
}
```

CLI (`main.py`) and chat (`/api/chat`) both return this same JSON shape. HTTP error responses (`400`, `502`) still use `{"error": "..."}`.

## Setup (uv)

This project works well with `uv` for environment and dependency management.  
Reference: [How to Create a Python Virtual Environment with uv](https://earthly.dev/blog/python-uv/)

1. Install `uv` (Windows PowerShell):

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

2. Create a virtual environment in the repo:

```powershell
uv venv .venv
```

3. Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

4. Install project dependencies:

```powershell
uv pip install -r requirements.txt
uv pip install -e .
```

5. Copy the environment template and fill in secrets:

```powershell
copy .env.example .env
```

See [Environment variables](#environment-variables) below.

## Environment variables

Copy [`.env.example`](.env.example) to `.env` for local development. On hosted platforms (Render, Railway, Heroku, etc.), set the same keys in the service dashboard.

### Required

| Variable | Description |
|----------|-------------|
| `SERP_API_KEY` | SerpApi key for Google / marketplace search. App fails at startup without it (`Settings.validate()`). |

### Recommended for production (chat UI)

| Variable | Description |
|----------|-------------|
| `FLASK_SECRET_KEY` | Secret for Flask signed sessions. **Set in production** (do not use the dev default). |
| `OPENAI_API_KEY` | Enables OpenAI for intent, routing, relevance, and explanations. Without it, the agent falls back to heuristics. |
| `PORT` | HTTP port (set automatically on most hosts). Default `5000` for local dev. |

### Optional (defaults in `.env.example`)

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `openai` | LLM backend (`openai` when `OPENAI_API_KEY` is set). |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model name. |
| `SHOPPING_RESULTS_PER_QUERY` | `12` | Max raw results per search query. |
| `MIN_RECOMMENDED_LINKS` | `4` | Minimum links before broadening search. |
| `MAX_RECOMMENDED_LINKS` | `5` | Max items in the shortlist. |
| `RELEVANCE_MIN_SCORE` | `0.38` | Minimum relevance score to keep a result. |
| `RELEVANCE_CLARIFY_MAX_SCORE` | `0.48` | Below this, trigger clarification flow. |
| `MAX_IMMERSIVE_LOOKUPS` | `4` | Cap on SerpApi immersive product lookups. |
| `USD_TO_TRY_RATE` | `45.54` | FX rate for budget conversion (TRY markets). |
| `USE_AMAZON_SEARCH` | `true` | Enable Amazon search path. |
| `USE_TRENDYOL_NATIVE` | `true` | Enable Trendyol native API search. |
| `USE_TRENDYOL_SERPAPI_FALLBACK` | `true` | SerpApi fallback when Trendyol native is thin. |
| `TRENDYOL_FALLBACK_MIN_RESULTS` | `3` | Native result count before fallback. |
| `TRENDYOL_MAX_RESULTS_PER_QUERY` | `24` | Max Trendyol results per query. |
| `TRENDYOL_REQUEST_TIMEOUT` | `30` | Trendyol HTTP timeout (seconds). |

## Run (JSON CLI output)

```bash
python -m shopping_search_agent.main 'I need waterproof running shoes for women under $120'
```

Expected output is the unified JSON schema above (constraints, market, parse, shortlist, message, disclaimer).

PowerShell note: prefer single quotes around queries with `$` so budget values are not expanded as shell variables.

## Run (Chat UX)

Start the chat web app:

```bash
python -m shopping_search_agent.chat_app
```

Then open:

- [http://localhost:5000](http://localhost:5000)

The chat UI displays the `message` field from the same unified JSON returned by `/api/chat` (no separate `reply`/`data` wrapper).

## Production deployment

Use **gunicorn** (included in `requirements.txt` / `pyproject.toml`), not the Flask dev server.

### Start command

```bash
gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 2 --timeout 120 shopping_search_agent.chat_app:app
```

- **WSGI app:** `shopping_search_agent.chat_app:app` (Flask instance in `chat_app.py`).
- **`PORT`:** Set by the host (Render, Railway, Heroku, Fly, etc.). Defaults to `5000` locally if unset.
- **`Procfile`:** Same command for platforms that read a Procfile (`web:` process).

### Typical platform setup

1. Build: `pip install -r requirements.txt && pip install -e .`
2. Start command: use the gunicorn line above, or point the platform at [`Procfile`](Procfile).
3. Env: at minimum `SERP_API_KEY`, `FLASK_SECRET_KEY`, and `OPENAI_API_KEY` (recommended).

## Push to GitHub

Target repository: [venturero/ecommerce_agent](https://github.com/venturero/ecommerce_agent)

1. Initialize git in this project folder (if needed):

```bash
git init
```

2. Add your GitHub remote:

```bash
git remote add origin https://github.com/venturero/ecommerce_agent.git
```

If `origin` already exists, update it:

```bash
git remote set-url origin https://github.com/venturero/ecommerce_agent.git
```

3. Stage and commit:

```bash
git add .
git commit -m "feat: bootstrap shopping search agent with chat UX"
```

4. Push to GitHub:

```bash
git branch -M main
git push -u origin main
```

5. Verify that `.env` is not tracked:

```bash
git status
git check-ignore -v .env
```

If `.env` was already tracked before `.gitignore`, untrack it once:

```bash
git rm --cached .env
git commit -m "chore(git): stop tracking local .env"
git push
```

## Package layout

- `src/shopping_search_agent/router.py` - semantic routing
- `src/shopping_search_agent/intent_parser.py` - intent extraction
- `src/shopping_search_agent/query_generator.py` - diversified query planning
- `src/shopping_search_agent/search.py` - SerpApi retrieval
- `src/shopping_search_agent/ranking.py` - ranking/filtering and dedupe
- `src/shopping_search_agent/explanation.py` - evidence-based explanation
- `src/shopping_search_agent/public_response.py` - unified response mapper (`to_public_response`)
- `src/shopping_search_agent/agent.py` - end-to-end orchestration
- `src/shopping_search_agent/main.py` - executable CLI
- `src/shopping_search_agent/chat_app.py` - Flask chat UI + `/api/chat` endpoint
- `Procfile` - production web process (`gunicorn`)
