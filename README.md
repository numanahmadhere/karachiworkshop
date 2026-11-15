# AI Dashboard Pipeline

Densight Labs AI Build Room template. One instruction, one set of data, and a
GitHub workflow that builds dashboards **without AI** and **with AI**, at the
same time, then checks the AI's numbers and publishes everything as a web page.

```
                        +--> 2A. Without AI (plain code) --+
1. Prepare  ------------+                                  +--> 3. Publish --> your live link
(read data,             +--> 2B. With AI: gpt-oss-120b ----+    (check, combine, save)
calculate facts)        +--> 2B. With AI: gpt-oss-20b  ----+
```

## What is in this repo

| Path | What it is |
|---|---|
| `.github/workflows/dashboard.yml` | The workflow. GitHub draws its jobs as a live graph. |
| `build_dashboard.py` | The Python code each job runs (standard library only). |
| `sample/data.csv`, `sample/prompt.csv` | Sample data and instructions, so the first run works at once. |
| `apps-script/Code.gs` | The Google Sheets version of the same idea (menu inside a sheet). |
| `docs/` | Where the finished website is saved (GitHub Pages reads this folder). |

## For the facilitator
1. Open **Settings** on this repo and tick **Template repository**.
2. Share the repo link. Students click **Use this template**, then **Create a new repository** (public).

## For students
1. In your new repo: **Settings, Secrets and variables, Actions, Secrets**, add a secret named `GROQ_API_KEY` with your free key from console.groq.com.
2. **Actions** tab, **Build AI dashboard**, **Run workflow**. Open the run and watch the jobs.
3. When it is green: **Settings, Pages**, Source **Deploy from a branch**, branch `main`, folder `/docs`.
4. Open your link: `https://YOUR-NAME.github.io/ai-dashboard/`.

### Use your own Google Sheet
Publish your **Data** tab and **Prompt** tab as CSV (File, Share, Publish to web). In
**Settings, Secrets and variables, Actions, Variables**, add `DATA_CSV_URL` and
`PROMPT_CSV_URL` with those links, then run the workflow again. Without these
variables the workflow uses the files in `sample/`.

Only publish data you are happy for anyone to see.

## Using the Apps Script version
Open your Google Sheet, **Extensions, Apps Script**, paste `apps-script/Code.gs`, add a
script property `GROQ_API_KEY`, refresh the sheet and use the **AI Dashboard** menu.
Your sheet needs two tabs named `Data` and `Prompt`.

## Notes
- The two AI jobs use different models, so each has its own free-tier limit and they can run together.
- Free-tier model names change. If a model stops working, edit the `matrix` list in the workflow
  (names are on console.groq.com/docs/models).
- If an AI job fails, the plain dashboard is still published.
