"""AI dashboard pipeline for the Densight AI Build Room.

GitHub Actions runs this file in separate jobs, each with its own command:

    python build_dashboard.py prepare   read the data, calculate the facts
    python build_dashboard.py plain     build the dashboard WITHOUT AI
    python build_dashboard.py ai        build a dashboard WITH AI (one model)
    python build_dashboard.py publish   check, combine and save the results

The plain job and the AI jobs run at the same time. Uses only the Python
standard library, so there is nothing to install.
"""
import csv
import html
import io
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MAX_ROWS = 40
WORK = "work"        # passed from the prepare job to the other jobs
OUT = "out"          # what each job hands to the publish job
DOCS = "docs"        # the final website (GitHub Pages)

SYSTEM_PROMPT = (
    "You are a senior data analyst and front-end developer. "
    "Return ONE complete, self-contained HTML page and nothing else. "
    "No explanation, no markdown fences. "
    "Rules: put all CSS in a style tag; "
    "do not load any external scripts, fonts, images or stylesheets; "
    "you may use a small amount of plain JavaScript; "
    "draw charts with HTML and CSS or inline SVG; "
    "use ONLY the DATA and FACTS provided; "
    "write every number exactly as it appears in FACTS (same digits, with commas, "
    "no abbreviations); never invent numbers. "
    "The page must contain, in this order: (1) a clear title; "
    "(2) a row of 4 headline numbers taken from FACTS; "
    "(3) two different charts that help answer the Focus; "
    "(4) a section called Key insights with 3 findings, each quoting specific numbers; "
    "(5) a section called Recommended actions with 3 actions written for the Audience; "
    "(6) a table of all the data rows with a dropdown that filters the rows by one "
    "text column, using plain JavaScript. "
    "Keep the code compact, under 220 lines. "
    "Make it look polished on a screen about 900 pixels wide."
)


def log(title, detail=""):
    """Each step shows up as its own line in the GitHub Actions log."""
    print(f"::group::{title}", flush=True)
    if detail:
        print(detail, flush=True)
    print("::endgroup::", flush=True)


def write(folder, name, text):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
        f.write(text)


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


# ---------- Reading the data ----------

def read_rows(location):
    """Read a CSV from a web link (your published Sheet) or a file in the repo."""
    if location.startswith("http"):
        req = urllib.request.Request(location, headers={"User-Agent": "densight-workshop/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8-sig")
    else:
        with open(location, encoding="utf-8-sig") as f:
            text = f.read()
    return list(csv.reader(io.StringIO(text)))


def to_number(v):
    v = str(v).replace(",", "").strip()
    if v == "":
        return None
    try:
        n = float(v)
    except ValueError:
        return None
    return n if math.isfinite(n) else None


def fmt(n):
    return f"{round(n):,}"


def average(values):
    return sum(values) / len(values)


# ---------- Working out the data ----------

def analyze(headers, rows):
    """Find which columns are numbers and which are categories."""
    numeric, categories = [], []
    for c, name in enumerate(headers):
        col = [r[c] for r in rows if c < len(r) and r[c] != ""]
        if not col:
            continue
        nums = [n for n in (to_number(v) for v in col) if n is not None]
        if len(nums) >= len(col) * 0.8:
            numeric.append({"name": name, "index": c, "nums": nums})
        else:
            counts = {}
            for v in col:
                counts[v] = counts.get(v, 0) + 1
            if 1 < len(counts) <= 12 and len(counts) < len(col):
                categories.append({"name": name, "index": c, "counts": counts})
    return numeric, categories


def build_facts(rows, numeric, categories):
    """Exact numbers worked out by code. The AI must use these as written."""
    lines = [f"Rows: {len(rows)}"]
    keys = []
    for col in numeric[:2]:
        avg = fmt(average(col["nums"]))
        lines.append(f"Average {col['name']}: {avg}")
        keys.append(avg)
    if numeric:
        col = numeric[0]
        scored = [(to_number(r[col["index"]]), r[0]) for r in rows
                  if to_number(r[col["index"]]) is not None]
        hi, lo = max(scored), min(scored)
        lines.append(f"Highest {col['name']}: {fmt(hi[0])} ({hi[1]})")
        lines.append(f"Lowest {col['name']}: {fmt(lo[0])} ({lo[1]})")
        keys += [fmt(hi[0]), fmt(lo[0])]
        for cat in categories[:2]:
            groups = {}
            for r in rows:
                n = to_number(r[col["index"]])
                if n is not None:
                    groups.setdefault(r[cat["index"]], []).append(n)
            ranked = sorted(((g, average(v)) for g, v in groups.items()),
                            key=lambda p: -p[1])[:6]
            parts = "; ".join(f"{g} {fmt(a)}" for g, a in ranked)
            lines.append(f"Average {col['name']} by {cat['name']}: {parts}")
    for cat in categories[:2]:
        ranked = sorted(cat["counts"].items(), key=lambda p: -p[1])[:6]
        lines.append(f"Count by {cat['name']}: " + "; ".join(f"{k} {v}" for k, v in ranked))
    unique = list(dict.fromkeys(keys))
    return "\n".join(lines), unique


# ---------- The dashboard WITHOUT AI ----------

def build_plain(numeric, categories, row_count):
    cards = [("Rows", row_count)]
    for col in numeric[:2]:
        cards.append((f"Average {col['name']}", fmt(average(col["nums"]))))
    if numeric:
        cards.append((f"Highest {numeric[0]['name']}", fmt(max(numeric[0]["nums"]))))
    cards_html = "".join(
        f'<div class="card"><b>{html.escape(str(v))}</b><span>{html.escape(k)}</span></div>'
        for k, v in cards)
    charts_html = ""
    for cat in categories[:2]:
        entries = sorted(cat["counts"].items(), key=lambda p: -p[1])[:6]
        top = entries[0][1]
        bars = "".join(
            f'<div class="row"><span class="lab">{html.escape(k)}</span>'
            f'<div class="bar" style="width:{round(v / top * 100)}%"></div>'
            f'<span class="n">{v}</span></div>' for k, v in entries)
        charts_html += f'<div class="box"><h3>Count by {html.escape(cat["name"])}</h3>{bars}</div>'
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8"><style>'
        "body{font-family:Arial,sans-serif;margin:0;padding:18px;background:#f5f6f8;color:#222}"
        "h1{font-size:20px;margin:0 0 4px}p.s{margin:0 0 14px;color:#666;font-size:13px}"
        ".cards{display:flex;gap:10px;margin-bottom:14px}"
        ".card{flex:1;background:#fff;border:1px solid #ddd;padding:12px}"
        ".card b{display:block;font-size:22px}.card span{font-size:12px;color:#666}"
        ".box{background:#fff;border:1px solid #ddd;padding:12px;margin-bottom:12px}"
        ".box h3{font-size:14px;margin:0 0 8px}"
        ".row{display:flex;align-items:center;gap:8px;margin:4px 0;font-size:12px}"
        ".lab{width:130px;flex:none}.bar{background:#7a8aa0;height:14px}.n{color:#666}"
        "</style></head><body><h1>Standard dashboard (no AI)</h1>"
        '<p class="s">Plain code. The same layout for every sheet. It cannot read your '
        "Style, Audience or Focus. It writes no insights and gives no advice.</p>"
        f'<div class="cards">{cards_html}</div>{charts_html}</body></html>'
    )


# ---------- Talking to the AI ----------

def post_json(url, headers, payload):
    """Send the request. Returns (status code, response text)."""
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={**headers, "Content-Type": "application/json",
                 "User-Agent": "densight-workshop/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8", "replace")


def clean_html(raw):
    text = raw.replace("```html", "").replace("```", "").strip()
    start = re.search(r"<!DOCTYPE html|<html", text, re.I)
    end = text.lower().rfind("</html>")
    if start and end > start.start():
        text = text[start.start():end + 7]
    lower = text.lower()
    if "<html" not in lower and "<div" not in lower:
        return ""
    return text


def check_numbers(page, keys):
    text = page.replace(",", "")
    return sum(1 for k in keys if k.replace(",", "") in text)


# ---------- Job 1: prepare ----------

def prepare():
    data_url = os.environ.get("DATA_CSV_URL", "").strip()
    prompt_url = os.environ.get("PROMPT_CSV_URL", "").strip()
    if data_url and prompt_url:
        source = "your published Sheet"
        values, prompt_rows = read_rows(data_url), read_rows(prompt_url)
    else:
        source = "the sample files in this repo (sample folder)"
        values = read_rows("sample/data.csv")
        prompt_rows = read_rows("sample/prompt.csv")

    headers = values[0]
    rows = [r for r in values[1:] if "".join(r).strip()][:MAX_ROWS]
    log("Step 1: Read your data", f"Source: {source}\n{len(rows)} rows, {len(headers)} columns")

    def pick(i):
        return prompt_rows[i][1] if len(prompt_rows) > i and len(prompt_rows[i]) > 1 else ""
    style, audience, focus = pick(1), pick(2), pick(3)
    log("Step 2: Read your choices", f"{style} | {audience} | {focus}")

    numeric, categories = analyze(headers, rows)
    facts_text, keys = build_facts(rows, numeric, categories)
    log("Step 3: Calculated the facts with code", f"{len(keys)} key numbers\n{facts_text}")

    data_text = "\n".join(" | ".join(r) for r in [headers] + rows)
    user_prompt = (f"Build the dashboard in this style: {style}\n"
                   f"It is for: {audience}\nFocus on: {focus}\n\n"
                   f"FACTS (calculated by code, exact):\n{facts_text}\n\n"
                   f"DATA (columns separated by |):\n{data_text}")
    log("Step 4: Wrote the instruction for the AI",
        f"{len(SYSTEM_PROMPT) + len(user_prompt)} characters")

    write(WORK, "data.json", json.dumps({"headers": headers, "rows": rows,
                                         "source": source}))
    write(WORK, "facts.json", json.dumps({"text": facts_text, "keys": keys}))
    write(WORK, "user_prompt.txt", user_prompt)


# ---------- Job 2A: plain ----------

def plain():
    data = json.loads(read_text(os.path.join(WORK, "data.json")))
    numeric, categories = analyze(data["headers"], data["rows"])
    write(OUT, "plain.html", build_plain(numeric, categories, len(data["rows"])))
    log("Step 5A: Built the Without AI dashboard", "Plain code, no AI involved")


# ---------- Job 2B: ai (runs once per model, at the same time) ----------

def ai():
    api_key = os.environ.get("GROQ_API_KEY", "")
    model = os.environ.get("MODEL", "")
    slug = os.environ.get("SLUG", "") or model.split("/")[-1]
    if not api_key:
        print("::error::No GROQ_API_KEY found. Add it under Settings, "
              "Secrets and variables, Actions, Secrets.", flush=True)
        sys.exit(1)

    user_prompt = read_text(os.path.join(WORK, "user_prompt.txt"))
    keys = json.loads(read_text(os.path.join(WORK, "facts.json")))["keys"]
    payload = {
        "model": model, "temperature": 0.4, "max_completion_tokens": 6000,
        "reasoning_effort": "low", "include_reasoning": False,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": user_prompt}],
    }

    started = time.time()
    code, body = 0, ""
    for attempt in range(1, 4):
        log("Step 5B: Sent to the AI", f"Model {model}, try {attempt}")
        code, body = post_json(GROQ_URL, {"Authorization": f"Bearer {api_key}"}, payload)
        if code != 429 and code < 500:
            break
        if attempt < 3:
            log("The free AI is busy", "Waiting 20 seconds, then trying again")
            time.sleep(20)
    seconds = round(time.time() - started, 1)
    log("Step 6B: The AI answered", f"Code {code}, {seconds} seconds")

    page, error, usage, check, status = "", "", {}, "not checked", "ok"
    if code != 200:
        error = f"The AI did not answer (code {code}). {body[:250]}"
        status = "error"
    else:
        data = json.loads(body)
        usage = data.get("usage", {})
        choice = data["choices"][0]
        page = clean_html(choice["message"].get("content") or "")
        log("Step 7B: Tokens used",
            f"{usage.get('prompt_tokens', '?')} in, {usage.get('completion_tokens', '?')} out")
        if not page:
            error = "The AI did not return a page this time. Run the workflow again."
            status = "error"
        else:
            log("Step 8B: Cleaned the page", f"{len(page)} characters of HTML")
            found = check_numbers(page, keys)
            check = f"{found} of {len(keys)}"
            log("Step 9B: Checked the AI's numbers",
                f"{found} of {len(keys)} key numbers match the facts")
            if choice.get("finish_reason") == "length":
                status = "cut off"
                print("::warning::The page was cut off. Try a simpler Style.", flush=True)
    if error:
        print(f"::warning::{error}", flush=True)

    shown = page or ("<html><body style='font-family:Arial;padding:24px'>"
                     f"<h2>No AI dashboard from {html.escape(model)}</h2>"
                     f"<p>{html.escape(error)}</p></body></html>")
    write(OUT, "ai.html", shown)
    write(OUT, "code.txt", page or "No code this time.")
    write(OUT, "result.json", json.dumps({
        "model": model, "slug": slug, "status": status, "seconds": seconds,
        "tokens": usage.get("total_tokens", "?"), "check": check, "error": error}))


# ---------- Job 3: publish ----------

def build_compare(results):
    ok_times = [r["seconds"] for r in results if r["status"] != "error"]
    fastest = min(ok_times) if ok_times else None
    rows = ""
    for r in results:
        badge = " (fastest)" if fastest is not None and r["seconds"] == fastest \
            and r["status"] != "error" else ""
        rows += (f"<tr><td>{html.escape(r['model'])}</td><td>{html.escape(r['status'])}</td>"
                 f"<td>{r['seconds']} s{badge}</td><td>{html.escape(str(r['tokens']))}</td>"
                 f"<td>{html.escape(r['check'])}</td></tr>")
    return ("<!DOCTYPE html><html><head><meta charset='utf-8'><style>"
            "body{font-family:Arial,sans-serif;padding:20px;color:#222}"
            "table{border-collapse:collapse;width:100%;margin:12px 0}"
            "th{background:#0b1f3a;color:#fff;text-align:left}"
            "td,th{border:1px solid #ccc;padding:8px;font-size:14px}"
            "</style></head><body><h2>Model race</h2>"
            "<p>The same instruction and the same facts went to each model at the same "
            "time. Open each AI tab and compare the dashboards, then compare the numbers "
            "here.</p>"
            "<table><tr><th>Model</th><th>Result</th><th>Time</th><th>Tokens</th>"
            f"<th>Number check</th></tr>{rows}</table>"
            "<p>A fast model is not always the best one. Look at how well each one "
            "followed the instruction.</p></body></html>")


def build_index(tabs, default, line):
    buttons = "".join(f'<button onclick="go({i})">{html.escape(t[0])}</button>'
                      for i, t in enumerate(tabs))
    pages = json.dumps([t[1] for t in tabs])
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>My AI dashboards</title><style>
body{{font-family:Arial,sans-serif;margin:0;padding:14px;background:#fff}}
.stats{{font-size:12px;color:#555;margin:0 0 8px}}
button{{border:1px solid #bbb;background:#eee;padding:8px 14px;cursor:pointer}}
button.on{{background:#0b1f3a;color:#fff;border-color:#0b1f3a}}
iframe{{width:100%;height:80vh;border:1px solid #ccc;margin-top:8px}}
</style></head><body><h2 style="margin:0 0 6px">My AI dashboards</h2>
<p class="stats">{html.escape(line)}</p>
<div id="tabs">{buttons}</div>
<iframe id="f" sandbox="allow-scripts"></iframe>
<script>
var pages={pages};
function go(i){{var b=document.querySelectorAll("#tabs button");
for(var k=0;k<b.length;k++){{b[k].className=(k==i?"on":"");}}
document.getElementById("f").src=pages[i];}}
go({default});
</script></body></html>"""


def publish():
    results_root = "results"
    results, plain_html = [], ""
    for name in sorted(os.listdir(results_root)) if os.path.isdir(results_root) else []:
        folder = os.path.join(results_root, name)
        if name == "result-plain":
            plain_html = read_text(os.path.join(folder, "plain.html"))
        elif os.path.exists(os.path.join(folder, "result.json")):
            result = json.loads(read_text(os.path.join(folder, "result.json")))
            result["folder"] = folder
            results.append(result)
    log("Step 10: Combined the results",
        f"Without AI: {'yes' if plain_html else 'missing'}. AI results: {len(results)}")

    # start the website folder fresh, but keep the .gitkeep file
    if os.path.isdir(DOCS):
        for old in os.listdir(DOCS):
            if old != ".gitkeep" and os.path.isfile(os.path.join(DOCS, old)):
                os.remove(os.path.join(DOCS, old))

    tabs = []
    if plain_html:
        write(DOCS, "plain.html", plain_html)
        tabs.append(("Without AI", "plain.html"))
    default = 0
    for r in results:
        write(DOCS, f"ai-{r['slug']}.html", read_text(os.path.join(r["folder"], "ai.html")))
        write(DOCS, f"code-{r['slug']}.txt", read_text(os.path.join(r["folder"], "code.txt")))
        if r["status"] != "error" and default == 0:
            default = len(tabs)
        tabs.append((f"With AI: {r['slug']}", f"ai-{r['slug']}.html"))
    if results:
        write(DOCS, "compare.html", build_compare(results))
        tabs.append(("Model race", "compare.html"))
    user_prompt = read_text(os.path.join(WORK, "user_prompt.txt"))
    write(DOCS, "prompt.txt", SYSTEM_PROMPT + "\n\n" + user_prompt)
    tabs.append(("The prompt we sent", "prompt.txt"))
    for r in results:
        tabs.append((f"Code: {r['slug']}", f"code-{r['slug']}.txt"))

    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    line = f"Updated: {updated} | Models: {', '.join(r['slug'] for r in results) or 'none'}"
    write(DOCS, "index.html", build_index(tabs, default, line))
    write(DOCS, "run.json", json.dumps({"updated": updated, "results": [
        {k: v for k, v in r.items() if k != "folder"} for r in results]}, indent=2))
    log("Step 11: Saved everything to the docs folder", f"{len(tabs)} tabs on your page")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if summary and "/" in repo:
        owner, name = repo.split("/", 1)
        table = "".join(f"| {r['model']} | {r['status']} | {r['seconds']} s | "
                        f"{r['tokens']} | {r['check']} |\n" for r in results)
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## Your dashboards\n\n"
                    f"Live link (after GitHub Pages is on): https://{owner}.github.io/{name}/\n\n"
                    "| Model | Result | Time | Tokens | Number check |\n"
                    "|---|---|---|---|---|\n" + table)


COMMANDS = {"prepare": prepare, "plain": plain, "ai": ai, "publish": publish}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        sys.exit("Use one of: " + ", ".join(COMMANDS))
    COMMANDS[sys.argv[1]]()
