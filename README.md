# AI Comments Workbench (Prototype)

Python web prototype implementing the requested flow with OpenAI integration.

## Features

- **Financial performance snapshot** shown before comment entry with credible 2024 vs 2025 multi-country KPI data and business storyline for comparative analysis comments
- **Insert comment** with optional:
  - `Suggest improvements before submit` (LLM quality review + revised draft popup)
  - `Normalize to English before submit` (LLM translation)
- **Header actions**:
  - `Reset all data` button to clear comments, consolidated comments, and executive summary
  - top-right `⚙️ Configuration` panel
- **Configuration panel** contains:
  - OpenAI API key
  - Tone of voice rules (free text)
  - Improvements rules (free text)
- **Raw comments table**: `id`, `text`, `created_at`
- **AI consolidated comments table**: `comment_id`, `consolidated_text`, `created_at`
- **Executive summary** auto-refreshes on each saved comment and is shown as formatted text (supports markdown-like `**bold**`, `*italic*`, `` `code` ``)
- **Analysis Q&A** over consolidated comments with OpenAI

## Run

```bash
python app.py
```

Open: `http://localhost:8501`

## Notes

- Configuration is stored in browser `localStorage`.
- The API key is sent to backend requests but not persisted to disk.
- Data persistence: `data/comments_store.json`.
