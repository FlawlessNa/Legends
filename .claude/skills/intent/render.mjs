#!/usr/bin/env node
// Render a topic discussion page after editing it. docs/agents/topics.md
// describes the page; run this after every edit, before replying in Lavish.
//
//   node .claude/skills/intent/render.mjs .lavish/<topic>
//
// 1. Injects the page runtime (runtime.html, beside this script) between the
//    <!-- intent:runtime --> markers, so every page runs the current version.
// 2. Inlines each <script type="text/markdown" data-md="<file>"> block from
//    <topic>/<file>. Lavish runs the page in a sandboxed iframe with an opaque
//    origin, so the page cannot fetch() the file itself.
// 3. Embeds the previous iteration from <topic>/.history/, so the page can
//    highlight what changed since then, and saves this iteration there.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const dir = process.argv[2];
if (!dir) { console.error("usage: render.mjs <topic-dir>"); process.exit(2); }
const page = path.join(dir, "index.html");
const hist = path.join(dir, ".history");
fs.mkdirSync(hist, { recursive: true });

const PREV = /<script type="application\/json" id="lavish-prev">[\s\S]*?<\/script>\n?/;
let html = fs.readFileSync(page, "utf8").replace(PREV, "");

// 1. The runtime.
const runtime = fs.readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)), "runtime.html"), "utf8");
const RUNTIME = /<!-- intent:runtime -->[\s\S]*?<!-- \/intent:runtime -->/;
if (!RUNTIME.test(html)) { console.error("index.html has no <!-- intent:runtime --> markers"); process.exit(2); }
html = html.replace(RUNTIME, () => `<!-- intent:runtime -->\n${runtime.trim()}\n<!-- /intent:runtime -->`);

// 2. The markdown sources. "</script" inside markdown would end the block.
html = html.replace(
  /(<script type="text\/markdown" data-md="([^"]+)">)[\s\S]*?(<\/script>)/g,
  (_, open, name, close) => {
    const src = path.join(dir, name);
    const md = fs.existsSync(src) ? fs.readFileSync(src, "utf8") : `*${name} does not exist yet.*`;
    return open + "\n" + md.replace(/<\/script/gi, "<\\/script") + "\n" + close;
  },
);

// 3. The previous iteration, then this one saved without it.
const previous = fs.readdirSync(hist).filter((f) => f.endsWith(".html")).sort().pop();
const iteration = previous ? Number(previous.slice(0, 4)) + 1 : 1;
if (previous) {
  const prevHtml = fs.readFileSync(path.join(hist, previous), "utf8");
  const json = JSON.stringify({ iteration: iteration - 1, html: prevHtml }).replace(/</g, "\\u003c");
  html = html.replace("</body>", () => `<script type="application/json" id="lavish-prev">${json}</script>\n</body>`);
}
fs.writeFileSync(page, html);
fs.writeFileSync(path.join(hist, `${String(iteration).padStart(4, "0")}.html`), html.replace(PREV, ""));
console.log(`rendered iteration ${iteration}` + (previous ? `, compared against ${iteration - 1}` : ", nothing to compare against"));
