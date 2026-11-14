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
    const number = element.paragraph ?? element.entry;
    const kind = number ? `${label(element.kind)} ${number}` : label(element.kind);
    meta.textContent = `Element ${index} · ${kind} · x ${Math.round(r.x)}, y ${Math.round(r.y)} · ${percent(element.extraction_score)}`;
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

$("previous").addEventListener("click", () => { unitIndex -= 1; render(); renderTei(); });
$("next").addEventListener("click", () => { unitIndex += 1; render(); renderTei(); });
fetch("review.json").then((response) => {
  if (!response.ok) throw new Error(`Could not load review.json: ${response.status}`);
  return response.json();
}).then((result) => { reviewData = result; render(); loadTei(result.tei_url); }).catch((error) => {
  $("summary").textContent = error.message;
});

// -- TEI rendering --------------------------------------------------------------
// The TEI column renders document.tei.xml, as pdf-to-tf builds it from this
// extraction, as HTML. Each block shows its TEI type; each line keeps its xml:id
// (p{page}e{index}), so it shows only on its own page and links to its card.
const TEI_NS = "http://www.tei-c.org/ns/1.0";
const XML_NS = "http://www.w3.org/XML/1998/namespace";
const TYPE_LABELS = {
  fw: (n) => n.getAttribute("type") === "footer" ? "running footer" : "running header",
  note: () => "footnote",
  p: (n) => `paragraph ${n.getAttribute("n") || ""}`.trim(),
  ab: (n) => label((n.getAttribute("type") || "block").replaceAll("-", "_")),
  list: () => "list",
  listBibl: () => "bibliography",
  bibl: (n) => `entry ${n.getAttribute("n") || ""}`.trim(),
  table: () => "table",
  figure: (n) => label((n.getAttribute("type") || "figure").replaceAll("-", "_")),
};
let teiRoot;

function teiBlock(node, tag, className) {
  const element = document.createElement(tag);
  element.className = `tei-${className}`;
  const type = TYPE_LABELS[node.localName];
  if (type) element.dataset.type = type(node);
  return element;
}

function teiNode(node) {
  if (node.nodeType === Node.TEXT_NODE) return document.createTextNode(node.data);
  if (node.nodeType !== Node.ELEMENT_NODE || node.namespaceURI !== TEI_NS) return null;
  const name = node.localName;
  let element;
  switch (name) {
    case "div": element = teiBlock(node, "section", "div"); break;
    case "head": {
      const level = Number((node.getAttribute("type") || "h2").slice(1)) || 2;
      element = teiBlock(node, `h${Math.min(level + 1, 6)}`, "head");
      element.dataset.type = node.getAttribute("type") || "heading";
      break;
    }
    case "p": element = teiBlock(node, "p", "p"); break;
    case "ab": element = teiBlock(node, "div", `ab tei-ab-${node.getAttribute("type") || "block"}`); break;
    case "note": element = teiBlock(node, "aside", "note"); break;
    case "fw": element = teiBlock(node, "div", `fw tei-fw-${node.getAttribute("type") || "header"}`); break;
    case "list": element = teiBlock(node, "ul", "list"); break;
    case "listBibl": element = teiBlock(node, "ul", "bibl-list"); break;
    case "item": case "bibl": element = teiBlock(node, "li", name); break;
    case "table": element = teiBlock(node, "table", "table"); break;
    case "row": element = teiBlock(node, "tr", "row"); break;
    case "cell": element = teiBlock(node, "td", "cell"); break;
    case "figure": element = teiBlock(node, "figure", "figure"); element.textContent = "[visual element]"; break;
    case "pb": {
      element = teiBlock(node, "div", "pb");
      element.textContent = `Page ${node.getAttribute("n")}`;
      element.dataset.page = node.getAttribute("n");
      return element;
    }
    case "hi": element = document.createElement(node.getAttribute("rend") === "bold" ? "strong" : "em"); break;
    case "ref": {
      element = document.createElement("a");
      const target = node.getAttribute("target") || "";
      if (/^https?:\/\//.test(target)) element.href = target;
      element.target = "_blank";
      element.rel = "noopener";
      break;
    }
    default: element = document.createElement("span"); element.className = `tei-${name}`;
  }
  const id = node.getAttributeNS(XML_NS, "id");
  const line = id && /^p(\d+)e(\d+)$/.exec(id);
  if (line) {
    element.dataset.page = line[1];
    element.dataset.element = line[2];
    element.classList.add("tei-line");
    element.title = `${id} · <${name}${node.getAttribute("type") ? ` type="${node.getAttribute("type")}"` : ""}>`;
  }
  for (const child of node.childNodes) {
    const rendered = teiNode(child);
    if (rendered) element.append(rendered);
  }
  return element;
}

function renderTei() {
  const target = $("tei");
  if (!teiRoot) return;
  const page = String(unitIndex + 1);
  // Lines show on their own page; containers show while they hold a visible line.
  for (const node of target.querySelectorAll("[data-page]")) node.hidden = node.dataset.page !== page;
  const blocks = [...target.querySelectorAll("section, p, div, aside, ul, li, table, tr, td, figure, h2, h3, h4, h5, h6")]
    .filter((node) => !node.dataset.page);
  for (const node of blocks.reverse()) node.hidden = !node.querySelector(`[data-page="${page}"]`);
  // Only this page shows, so start the column at its top.
  target.closest(".panel").scrollTop = 0;
}

function loadTei(url) {
  if (!url) {
    $("tei").textContent = "No TEI in this review (built with --no-tei).";
    $("tei-link").hidden = true;
    return;
  }
  fetch(url).then((response) => {
    if (!response.ok) throw new Error(`Could not load ${url}: ${response.status}`);
    return response.text();
  }).then((xml) => {
    const doc = new DOMParser().parseFromString(xml, "application/xml");
    if (doc.querySelector("parsererror")) throw new Error(`${url} is not well-formed XML`);
    const body = doc.getElementsByTagNameNS(TEI_NS, "body")[0];
    const target = $("tei");
    target.replaceChildren(...[...body.childNodes].map(teiNode).filter(Boolean));
    teiRoot = body;
    renderTei();
  }).catch((error) => { $("tei").textContent = error.message; });
}

$("tei").addEventListener("click", (event) => {
  const line = event.target.closest(".tei-line");
  if (!line || event.target.closest("a")) return;
  const card = $(`element-${line.dataset.element}`);
  card?.scrollIntoView({block: "center"});
  card?.focus({preventScroll: true});
});
$("tei-types").addEventListener("change", (event) => {
  $("tei").classList.toggle("types", event.target.checked);
});
