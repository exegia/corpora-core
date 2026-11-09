"use strict";
let reviewData;
let unitIndex = 0;
const $ = (id) => document.getElementById(id);
const label = (value) => value.replaceAll("_", " ");
const percent = (score) => score ? `${Math.round(score.value * 100)}% · ${label(score.basis)}` : "score unavailable";

function contentFor(element) {
  const content = document.createElement("div");
  content.className = "content";
  // Preserve the source wording; marks are shown as evidence rather than
  // applied by substring replacement, which could misplace repeated text.
  content.textContent = element.text || "[visual element]";
  return content;
}

function render() {
  const unit = reviewData.units[unitIndex];
  $("source-name").textContent = reviewData.source_name;
  $("page-label").textContent = `${unit.label} of ${reviewData.units.length}`;
  $("previous").disabled = unitIndex === 0;
  $("next").disabled = unitIndex === reviewData.units.length - 1;
  $("source-document").src = unit.source_url;
  $("summary").textContent = `${unit.summary} · ${percent(unit.score)}`;
  const findings = $("findings");
  findings.replaceChildren();
  if (!unit.findings.length) findings.textContent = "No findings for this unit.";
  for (const finding of unit.findings) {
    const row = document.createElement("div");
    row.className = "finding";
    row.textContent = `${finding.code}: ${finding.message}`;
    findings.append(row);
  }
  const elements = $("elements");
  elements.replaceChildren();
  for (const element of unit.elements) {
    const card = document.createElement("article");
    card.className = "element";
    card.dataset.kind = element.kind;
    const meta = document.createElement("div");
    meta.className = "meta";
    const r = element.bounds;
    meta.textContent = `${label(element.kind)} · x ${Math.round(r.x)}, y ${Math.round(r.y)} · ${percent(element.extraction_score)}`;
    card.append(meta, contentFor(element));
    if (element.section_path.length) {
      const path = document.createElement("div");
      path.className = "section";
      path.textContent = `Section: ${element.section_path.join(" › ")}`;
      card.append(path);
    }
    for (const mark of element.marks) {
      const tag = document.createElement("span");
      tag.className = "badge";
      tag.textContent = `${label(mark.kind)}: ${mark.text}${mark.target ? ` → ${mark.target}` : ""}`;
      card.append(tag);
    }
    elements.append(card);
  }
}

$("previous").addEventListener("click", () => { unitIndex -= 1; render(); });
$("next").addEventListener("click", () => { unitIndex += 1; render(); });
fetch("review.json").then((response) => {
  if (!response.ok) throw new Error(`Could not load review.json: ${response.status}`);
  return response.json();
}).then((result) => { reviewData = result; render(); }).catch((error) => {
  $("summary").textContent = error.message;
});
