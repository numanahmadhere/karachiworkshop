// AI Dashboard: Densight AI Build Room
// Reads the Data tab and your style choices from the Prompt tab.
// 1) Builds a dashboard WITHOUT AI (plain code).
// 2) Calculates exact facts with code.
// 3) Asks an AI model to turn the facts into a dashboard WITH AI.
// 4) Checks the AI's numbers, then shows everything in a pop-up.
// Watch the Log tab while it runs.

// If the first model stops working, the script tries the next one.
// To change models, edit this list (names are on console.groq.com/docs/models).
const MODELS = ['openai/gpt-oss-120b', 'openai/gpt-oss-20b'];
const GROQ_URL = 'https://api.groq.com/openai/v1/chat/completions';
const MAX_ROWS = 40;

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('AI Dashboard')
    .addItem('Generate dashboard', 'generateDashboard')
    .addToUi();
}

// ---------- The main steps ----------

function generateDashboard() {
  const started = Date.now();
  const ui = SpreadsheetApp.getUi();
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const dataSheet = ss.getSheetByName('Data');
  const promptSheet = ss.getSheetByName('Prompt');

  if (!dataSheet || !promptSheet) {
    ui.alert('Your sheet needs two tabs named exactly Data and Prompt.');
    return;
  }
  const apiKey = PropertiesService.getScriptProperties().getProperty('GROQ_API_KEY');
  if (!apiKey) {
    ui.alert('No API key found. Add GROQ_API_KEY in Script Properties.');
    return;
  }

  const log = startLog(ss);

  // 1. Read the data as plain text rows
  const values = dataSheet.getDataRange().getDisplayValues();
  const headers = values[0];
  const rows = values
    .slice(1)
    .filter(function (r) { return r.join('').trim() !== ''; })
    .slice(0, MAX_ROWS);
  const dataText = [headers]
    .concat(rows)
    .map(function (r) { return r.join(' | '); })
    .join('\n');
  logStep(log, '1. Read your data', rows.length + ' rows, ' + headers.length + ' columns');

  // 2. Read the three style choices
  const style = promptSheet.getRange('B2').getDisplayValue();
  const audience = promptSheet.getRange('B3').getDisplayValue();
  const focus = promptSheet.getRange('B4').getDisplayValue();
  logStep(log, '2. Read your choices', style + ' | ' + audience + ' | ' + focus);

  // 3. Build the dashboard WITHOUT AI (plain code, same layout every time)
  const info = analyze(headers, rows);
  const plainHtml = buildPlainDashboard(info, rows.length);
  logStep(log, '3. Built the Without AI dashboard', 'Plain code, no AI involved');

  // 4. Calculate exact facts with code. Code counts, AI thinks.
  const facts = buildFacts(rows, info);
  logStep(log, '4. Calculated the facts with code', facts.keys.length + ' key numbers');

  // 5. Write the instruction for the AI. Fixed rules keep the same backbone.
  const systemPrompt =
    'You are a senior data analyst and front-end developer. ' +
    'Return ONE complete, self-contained HTML page and nothing else. ' +
    'No explanation, no markdown fences. ' +
    'Rules: put all CSS in a style tag; ' +
    'do not load any external scripts, fonts, images or stylesheets; ' +
    'you may use a small amount of plain JavaScript; ' +
    'draw charts with HTML and CSS or inline SVG; ' +
    'use ONLY the DATA and FACTS provided; ' +
    'write every number exactly as it appears in FACTS (same digits, with commas, ' +
    'no abbreviations); never invent numbers. ' +
    'The page must contain, in this order: (1) a clear title; ' +
    '(2) a row of 4 headline numbers taken from FACTS; ' +
    '(3) two different charts that help answer the Focus; ' +
    '(4) a section called Key insights with 3 findings, each quoting specific numbers; ' +
    '(5) a section called Recommended actions with 3 actions written for the Audience; ' +
    '(6) a table of all the data rows with a dropdown that filters the rows by one ' +
    'text column, using plain JavaScript. ' +
    'Keep the code compact, under 220 lines. ' +
    'Make it look polished on a screen about 900 pixels wide.';
  const userPrompt =
    'Build the dashboard in this style: ' + style + '\n' +
    'It is for: ' + audience + '\n' +
    'Focus on: ' + focus + '\n\n' +
    'FACTS (calculated by code, exact):\n' + facts.text + '\n\n' +
    'DATA (columns separated by |):\n' + dataText;
  logStep(log, '5. Wrote the instruction for the AI',
    (systemPrompt.length + userPrompt.length) + ' characters');

  // 6. Ask the AI
  const result = callAI(apiKey, systemPrompt, userPrompt, log);
  const seconds = Math.round((Date.now() - started) / 100) / 10;
  logStep(log, '7. The AI answered',
    'Code ' + result.code + ', ' + seconds + ' seconds in total');

  let aiHtml = '';
  let errorMsg = '';
  let usage = {};
  let numberCheck = 'not checked';
  if (result.code !== 200) {
    errorMsg = 'The AI did not answer (code ' + result.code + '). ' +
      result.body.slice(0, 250) + ' See Part 9 of your guide.';
    logStep(log, 'Problem', 'The AI did not answer. The Without AI tab still works.');
  } else {
    const data = JSON.parse(result.body);
    usage = data.usage || {};
    const choice = data.choices[0];
    aiHtml = cleanHtml(choice.message.content || '');
    logStep(log, '8. Tokens used', (usage.prompt_tokens || '?') + ' in, ' +
      (usage.completion_tokens || '?') + ' out');
    if (aiHtml === '') {
      errorMsg = 'The AI did not return a page this time. Run it again.';
      logStep(log, 'Problem', 'No page came back');
    } else {
      logStep(log, '9. Cleaned the page', aiHtml.length + ' characters of HTML');
      const found = checkNumbers(aiHtml, facts.keys);
      numberCheck = found + ' of ' + facts.keys.length;
      logStep(log, '10. Checked the AI\'s numbers',
        found + ' of ' + facts.keys.length + ' key numbers match the facts');
      if (choice.finish_reason === 'length') {
        logStep(log, 'Warning', 'The page was cut off. Try a simpler Style.');
      }
    }
  }

  // 7. Show everything
  const stats = {
    model: result.model,
    seconds: seconds,
    tokens: usage.total_tokens || '?',
    rows: rows.length,
    check: numberCheck
  };
  const page = buildResultsPage(
    plainHtml, aiHtml, systemPrompt + '\n\n' + userPrompt, stats, errorMsg);
  logStep(log, '11. Showing the results', 'Look for the pop-up with four tabs');
  ui.showModelessDialog(
    HtmlService.createHtmlOutput(page).setWidth(1000).setHeight(700),
    'Your dashboards');
}

// ---------- Talking to the AI ----------

function callAI(apiKey, systemPrompt, userPrompt, log) {
  let response = null;
  let code = 0;
  let model = '';
  for (let m = 0; m < MODELS.length; m++) {
    model = MODELS[m];
    const options = {
      method: 'post',
      contentType: 'application/json',
      headers: { Authorization: 'Bearer ' + apiKey },
      muteHttpExceptions: true,
      payload: JSON.stringify({
        model: model,
        temperature: 0.4,
        max_completion_tokens: 6000,
        reasoning_effort: 'low',
        include_reasoning: false,
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: userPrompt }
        ]
      })
    };
    for (let attempt = 1; attempt <= 3; attempt++) {
      logStep(log, '6. Sent to the AI', 'Model ' + model + ', try ' + attempt);
      response = UrlFetchApp.fetch(GROQ_URL, options);
      code = response.getResponseCode();
      if (code !== 429 && code < 500) break;
      if (attempt < 3) {
        logStep(log, 'The free AI is busy', 'Waiting 20 seconds, then trying again');
        Utilities.sleep(20000);
      }
    }
    if (code === 200) break;
    // 404 or 400 means this model is not available: try the next one
    if (code !== 404 && code !== 400) break;
    logStep(log, 'Model not available',
      model + ' gave code ' + code + '. Trying the next.');
  }
  return { code: code, body: response.getContentText(), model: model };
}

function cleanHtml(raw) {
  let html = raw.replace(/```html/gi, '').replace(/```/g, '').trim();
  const start = html.search(/<!DOCTYPE html|<html/i);
  const end = html.toLowerCase().lastIndexOf('</html>');
  if (start >= 0 && end > start) {
    html = html.slice(start, end + 7);
  }
  const lower = html.toLowerCase();
  if (lower.indexOf('<html') === -1 && lower.indexOf('<div') === -1) {
    return '';
  }
  return html;
}

// Counts how many of the key numbers from the facts appear in the AI page.
function checkNumbers(html, keys) {
  const text = html.replace(/,/g, '');
  let found = 0;
  keys.forEach(function (k) {
    if (text.indexOf(k.replace(/,/g, '')) !== -1) found++;
  });
  return found;
}

// ---------- The Log tab ----------

function startLog(ss) {
  let sheet = ss.getSheetByName('Log');
  if (!sheet) sheet = ss.insertSheet('Log');
  sheet.clear();
  sheet.appendRow(['Time', 'Step', 'Detail']);
  sheet.getRange('A1:C1').setFontWeight('bold');
  sheet.getRange('A:A').setNumberFormat('HH:mm:ss');
  sheet.setColumnWidth(1, 80);
  sheet.setColumnWidth(2, 270);
  sheet.setColumnWidth(3, 520);
  ss.setActiveSheet(sheet);
  SpreadsheetApp.flush();
  return sheet;
}

function logStep(sheet, step, detail) {
  sheet.appendRow([new Date(), step, detail]);
  SpreadsheetApp.flush();
}

// ---------- Working out the data ----------

function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function toNumber(v) {
  if (String(v).trim() === '') return null;
  const n = Number(String(v).replace(/,/g, '').trim());
  return isNaN(n) ? null : n;
}

function fmt(n) {
  return Math.round(n).toLocaleString('en-US');
}

function average(list) {
  return list.reduce(function (a, b) { return a + b; }, 0) / list.length;
}

// Finds which columns are numbers and which are categories.
function analyze(headers, rows) {
  const numeric = [];
  const categories = [];
  headers.forEach(function (name, c) {
    const col = rows
      .map(function (r) { return r[c]; })
      .filter(function (v) { return v !== ''; });
    if (col.length === 0) return;
    const nums = col.map(toNumber).filter(function (n) { return n !== null; });
    if (nums.length >= col.length * 0.8) {
      numeric.push({ name: name, index: c, nums: nums });
    } else {
      const counts = {};
      col.forEach(function (v) { counts[v] = (counts[v] || 0) + 1; });
      const distinct = Object.keys(counts).length;
      if (distinct > 1 && distinct <= 12 && distinct < col.length) {
        categories.push({ name: name, index: c, counts: counts });
      }
    }
  });
  return { numeric: numeric, categories: categories };
}

// Exact numbers worked out by code. The AI is told to use these as written.
function buildFacts(rows, info) {
  const lines = ['Rows: ' + rows.length];
  const keys = [];
  info.numeric.slice(0, 2).forEach(function (col) {
    const avg = fmt(average(col.nums));
    lines.push('Average ' + col.name + ': ' + avg);
    keys.push(avg);
  });
  if (info.numeric.length > 0) {
    const col = info.numeric[0];
    let hi = null;
    let lo = null;
    rows.forEach(function (r) {
      const n = toNumber(r[col.index]);
      if (n === null) return;
      if (hi === null || n > hi.n) hi = { n: n, label: r[0] };
      if (lo === null || n < lo.n) lo = { n: n, label: r[0] };
    });
    lines.push('Highest ' + col.name + ': ' + fmt(hi.n) + ' (' + hi.label + ')');
    lines.push('Lowest ' + col.name + ': ' + fmt(lo.n) + ' (' + lo.label + ')');
    keys.push(fmt(hi.n), fmt(lo.n));
    info.categories.slice(0, 2).forEach(function (cat) {
      const groups = {};
      rows.forEach(function (r) {
        const n = toNumber(r[col.index]);
        if (n === null) return;
        if (!groups[r[cat.index]]) groups[r[cat.index]] = [];
        groups[r[cat.index]].push(n);
      });
      const parts = Object.keys(groups)
        .map(function (g) { return [g, average(groups[g])]; })
        .sort(function (a, b) { return b[1] - a[1]; })
        .slice(0, 6)
        .map(function (p) { return p[0] + ' ' + fmt(p[1]); });
      lines.push('Average ' + col.name + ' by ' + cat.name + ': ' + parts.join('; '));
    });
  }
  info.categories.slice(0, 2).forEach(function (cat) {
    const parts = Object.keys(cat.counts)
      .map(function (k) { return [k, cat.counts[k]]; })
      .sort(function (a, b) { return b[1] - a[1]; })
      .slice(0, 6)
      .map(function (p) { return p[0] + ' ' + p[1]; });
    lines.push('Count by ' + cat.name + ': ' + parts.join('; '));
  });
  const unique = keys.filter(function (k, i) { return keys.indexOf(k) === i; });
  return { text: lines.join('\n'), keys: unique };
}

// ---------- The dashboard WITHOUT AI ----------

function buildPlainDashboard(info, rowCount) {
  const cards = [['Rows', rowCount]];
  info.numeric.slice(0, 2).forEach(function (col) {
    cards.push(['Average ' + col.name, fmt(average(col.nums))]);
  });
  if (info.numeric.length > 0) {
    const top = Math.max.apply(null, info.numeric[0].nums);
    cards.push(['Highest ' + info.numeric[0].name, fmt(top)]);
  }
  const cardsHtml = cards.map(function (c) {
    return '<div class="card"><b>' + esc(c[1]) + '</b><span>' + esc(c[0]) + '</span></div>';
  }).join('');

  const chartsHtml = info.categories.slice(0, 2).map(function (cat) {
    const entries = Object.keys(cat.counts)
      .map(function (k) { return [k, cat.counts[k]]; })
      .sort(function (a, b) { return b[1] - a[1]; })
      .slice(0, 6);
    const top = entries[0][1];
    const bars = entries.map(function (e) {
      return '<div class="row"><span class="lab">' + esc(e[0]) + '</span>' +
        '<div class="bar" style="width:' + Math.round(e[1] / top * 100) + '%"></div>' +
        '<span class="n">' + e[1] + '</span></div>';
    }).join('');
    return '<div class="box"><h3>Count by ' + esc(cat.name) + '</h3>' + bars + '</div>';
  }).join('');

  return '<!DOCTYPE html><html><head><meta charset="utf-8"><style>' +
    'body{font-family:Arial,sans-serif;margin:0;padding:18px;' +
    'background:#f5f6f8;color:#222}' +
    'h1{font-size:20px;margin:0 0 4px}p.s{margin:0 0 14px;color:#666;font-size:13px}' +
    '.cards{display:flex;gap:10px;margin-bottom:14px}' +
    '.card{flex:1;background:#fff;border:1px solid #ddd;padding:12px}' +
    '.card b{display:block;font-size:22px}.card span{font-size:12px;color:#666}' +
    '.box{background:#fff;border:1px solid #ddd;padding:12px;margin-bottom:12px}' +
    '.box h3{font-size:14px;margin:0 0 8px}' +
    '.row{display:flex;align-items:center;gap:8px;margin:4px 0;font-size:12px}' +
    '.lab{width:130px;flex:none}.bar{background:#7a8aa0;height:14px}.n{color:#666}' +
    '</style></head><body>' +
    '<h1>Standard dashboard (no AI)</h1>' +
    '<p class="s">Plain code. The same layout for every sheet. ' +
    'It cannot read your Style, Audience or Focus. It writes no insights ' +
    'and gives no advice.</p>' +
    '<div class="cards">' + cardsHtml + '</div>' + chartsHtml +
    '</body></html>';
}

// ---------- The results pop-up (four tabs) ----------

function buildResultsPage(plainHtml, aiHtml, promptText, stats, errorMsg) {
  // The AI page may use small scripts, so it gets its own locked box:
  // allow-scripts without allow-same-origin keeps it away from your sheet.
  const aiPane = aiHtml !== ''
    ? '<iframe sandbox="allow-scripts" srcdoc="' + esc(aiHtml) + '"></iframe>'
    : '<div class="msg">' + esc(errorMsg) + '</div>';
  const codePane = aiHtml !== ''
    ? '<pre>' + esc(aiHtml) + '</pre>'
    : '<div class="msg">No code this time.</div>';
  const statsLine = 'Model: ' + esc(stats.model) + ' | Total time: ' + stats.seconds +
    ' s | Tokens: ' + esc(stats.tokens) + ' | Rows read: ' + stats.rows +
    ' | Number check: ' + esc(stats.check);

  return '<!DOCTYPE html><html><head><meta charset="utf-8"><style>' +
    'body{font-family:Arial,sans-serif;margin:0;padding:10px;background:#fff}' +
    '.stats{font-size:12px;color:#555;margin:0 0 8px}' +
    '.tabs button{border:1px solid #bbb;background:#eee;padding:8px 14px;cursor:pointer}' +
    '.tabs button.on{background:#0b1f3a;color:#fff;border-color:#0b1f3a}' +
    '.pane{display:none;margin-top:8px}.pane.on{display:block}' +
    'iframe{width:100%;height:520px;border:1px solid #ccc}' +
    'pre{height:500px;overflow:auto;background:#f3f4f6;padding:10px;font-size:11px;' +
    'white-space:pre-wrap;border:1px solid #ccc}' +
    '.msg{padding:16px;background:#fdecea;border:1px solid #e0b4b0;font-size:14px}' +
    '</style></head><body>' +
    '<p class="stats">' + statsLine + '</p>' +
    '<div class="tabs">' +
    '<button onclick="show(0)">Without AI</button>' +
    '<button onclick="show(1)">With AI</button>' +
    '<button onclick="show(2)">The prompt we sent</button>' +
    '<button onclick="show(3)">The code the AI wrote</button></div>' +
    '<div class="pane"><iframe sandbox="" srcdoc="' + esc(plainHtml) + '"></iframe></div>' +
    '<div class="pane">' + aiPane + '</div>' +
    '<div class="pane"><pre>' + esc(promptText) + '</pre></div>' +
    '<div class="pane">' + codePane + '</div>' +
    '<script>' +
    'function show(i){var b=document.querySelectorAll(".tabs button");' +
    'var p=document.querySelectorAll(".pane");' +
    'for(var k=0;k<p.length;k++){p[k].className="pane"+(k==i?" on":"");' +
    'b[k].className=(k==i?"on":"");}}' +
    'show(1);' +
    '</script></body></html>';
}
