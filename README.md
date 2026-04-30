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
3. **Output**:
   - `understood_intent`
   - `recommended_links` (5-8)
   - `disclaimer`

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

5. Ensure your `.env` includes:
   - `SERP_API_KEY` (required)
   - `OPENAI_API_KEY` (optional but recommended for better intent/explanations)

## Run (JSON CLI output)

```bash
python -m shopping_search_agent.main 'I need waterproof running shoes for women under $120'
```

Expected output is structured JSON with ranked external links and explanations.

PowerShell note: prefer single quotes around queries with `$` so budget values are not expanded as shell variables.

## Run (Chat UX)

Start the chat web app:

```bash
python -m shopping_search_agent.chat_app
```

Then open:

- [http://localhost:5000](http://localhost:5000)

The chat UI returns conversational responses for each message and uses the same core shopping pipeline under the hood.

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
git commit -m "Initial commit: shopping search agent with chat UX"
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
git commit -m "Stop tracking local .env"
git push
```

## Package layout

- `src/shopping_search_agent/router.py` - semantic routing
- `src/shopping_search_agent/intent_parser.py` - intent extraction
- `src/shopping_search_agent/query_generator.py` - diversified query planning
- `src/shopping_search_agent/search.py` - SerpApi retrieval
- `src/shopping_search_agent/ranking.py` - ranking/filtering and dedupe
- `src/shopping_search_agent/explanation.py` - evidence-based explanation
- `src/shopping_search_agent/agent.py` - end-to-end orchestration
- `src/shopping_search_agent/main.py` - executable CLI
- `src/shopping_search_agent/chat_app.py` - Flask chat UI + `/api/chat` endpoint
