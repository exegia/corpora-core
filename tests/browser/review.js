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
  $("source-link").href = unit.source_url;
  $("source-document").hidden = Boolean(unit.source_image_url);
  if (unit.source_image_url) {
    $("source-document").removeAttribute("src");
    const image = $("source-image") || document.createElement("img");
    image.id = "source-image";
    image.src = unit.source_image_url;
    image.alt = `Original source · ${unit.label}`;
    if (!image.isConnected) $("source-document").before(image);
  } else {
    $("source-image")?.remove();
    $("source-document").src = unit.source_url;
  }
  $("summary").textContent = `${unit.summary} · ${percent(unit.score)}`;
  const findings = $("findings");
  findings.replaceChildren();
  if (!unit.findings.length) findings.textContent = "No findings for this unit.";
  const details = document.createElement("details");
  const summary = document.createElement("summary");
  summary.textContent = `${unit.findings.length} findings · expand to review`;
  details.append(summary);
  if (unit.findings.length) findings.append(details);
  for (const finding of unit.findings) {
    const row = document.createElement("div");
    row.className = "finding";
    row.textContent = `${finding.code}: ${finding.message}`;
    if (Number.isInteger(finding.element_index) && finding.element_index >= 0 && finding.element_index < unit.elements.length) {
      const jump = document.createElement("button");
      jump.type = "button";
      jump.textContent = `Show element ${finding.element_index}`;
      jump.addEventListener("click", () => {
        const target = $(`element-${finding.element_index}`);
        target.scrollIntoView({block: "center"});
        target.focus({preventScroll: true});
      });
      row.append(" ", jump);
    }
    details.append(row);
  }
  const elements = $("elements");
  elements.replaceChildren();
  for (const [index, element] of unit.elements.entries()) {
    const card = document.createElement("article");
    card.className = "element";
    card.id = `element-${index}`;
    card.tabIndex = -1;
    card.dataset.kind = element.kind;
    const meta = document.createElement("div");
    meta.className = "meta";
    const r = element.bounds;
    meta.textContent = `Element ${index} · ${label(element.kind)} · x ${Math.round(r.x)}, y ${Math.round(r.y)} · ${percent(element.extraction_score)}`;
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
