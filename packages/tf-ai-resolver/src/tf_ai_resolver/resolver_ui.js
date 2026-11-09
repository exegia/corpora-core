/* Local selection bridge. The TF iframe has no scripts; only this parent page calls the API. */
(() => {
  const frame = document.querySelector('#tf-rendered');
  const panel = document.createElement('section');
  panel.className = 'panel';
  panel.style.cssText = 'margin-top:16px;padding:16px';
  panel.innerHTML = '<h2>Text-Fabric expert</h2><p>Select text in the semantic TF view above.</p>' +
    '<p id="resolver-selection"></p><label>Task <select id="resolver-mode"><option value="fix">Fix</option>' +
    '<option value="suggest">Suggest correction</option><option value="custom">Custom prompt</option></select></label>' +
    '<label for="resolver-prompt">Instruction</label><textarea id="resolver-prompt" rows="3" ' +
    'style="display:block;width:100%;margin:10px 0;background:#10151f;color:#e7edf6;border:1px solid #607086;border-radius:6px;padding:9px" ' +
    'maxlength="2000">Correct the selected text while preserving its meaning.</textarea>' +
    '<button id="resolver-run" type="button" disabled>Run expert</button>' +
    '<button id="resolver-apply" type="button" disabled>Apply candidate to derived reading</button>' +
    '<pre id="resolver-result" style="white-space:pre-wrap;overflow-wrap:anywhere"></pre>';
  document.querySelector('main').append(panel);
  const selectionLabel = panel.querySelector('#resolver-selection');
  const result = panel.querySelector('#resolver-result');
  const run = panel.querySelector('#resolver-run');
  const apply = panel.querySelector('#resolver-apply');
  const mode = panel.querySelector('#resolver-mode');
  const prompt = panel.querySelector('#resolver-prompt');
  let pinned = null;
  let pending = null;
  let sequence = 0;

  async function post(path, body) {
    const response = await fetch(path, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-TF-Resolver': '1'},
      body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Resolver request failed');
    return data;
  }

  function containingRoot(node) {
    const element = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
    return element && element.closest('[data-tf-node]');
  }

  function scalarLength(value) { return [...value].length; }

  async function inspect() {
    const current = ++sequence;
    pinned = null;
    pending = null;
    run.disabled = true;
    apply.disabled = true;
    const view = frame.contentWindow;
    const browserSelection = view && view.getSelection();
    if (!browserSelection || browserSelection.rangeCount !== 1 || browserSelection.isCollapsed) return;
    const range = browserSelection.getRangeAt(0);
    const root = containingRoot(range.startContainer);
    if (!root || root !== containingRoot(range.endContainer) ||
        !root.contains(range.startContainer) || !root.contains(range.endContainer)) {
      selectionLabel.textContent = 'Select text within one TF document or note.';
      return;
    }
    const prefix = root.ownerDocument.createRange();
    prefix.selectNodeContents(root);
    prefix.setEnd(range.startContainer, range.startOffset);
    const start = scalarLength(prefix.toString());
    const end = start + scalarLength(range.toString());
    const expected_text = range.toString();
    if (!expected_text || scalarLength(expected_text) > 4096) {
      selectionLabel.textContent = 'Select between 1 and 4,096 characters.';
      return;
    }
    selectionLabel.textContent = `Checking selection: “${expected_text.slice(0, 120)}”`;
    try {
      const data = await post('/api/inspect', {
        node: Number(root.dataset.tfNode), start, end, expected_text,
      });
      if (current !== sequence) return;
      pinned = data.selection;
      run.disabled = false;
      selectionLabel.textContent = `Selected ${end - start} characters in TF node ${pinned.node}: “${expected_text.slice(0, 120)}”`;
      result.textContent = '';
    } catch (error) {
      if (current === sequence) selectionLabel.textContent = error.message;
    }
  }

  frame.addEventListener('load', () => {
    pinned = null;
    pending = null;
    run.disabled = true;
    apply.disabled = true;
    selectionLabel.textContent = 'Select text within one TF document or note.';
    const view = frame.contentWindow;
    if (!view) return;
    view.document.addEventListener('mouseup', inspect);
    view.document.addEventListener('keyup', inspect);
  });
  mode.addEventListener('change', () => {
    prompt.value = mode.value === 'fix' ? 'Correct the selected text while preserving its meaning.' :
      mode.value === 'suggest' ? 'Suggest a correction to the selected text.' : '';
  });
  run.addEventListener('click', async () => {
    if (!pinned || !prompt.value.trim()) return;
    run.disabled = true;
    pending = null;
    apply.disabled = true;
    result.textContent = 'The expert is working…';
    try {
      const data = await post('/api/resolve', {
        selection: pinned, mode: mode.value, prompt: prompt.value,
      });
      const proposal = data.report.resolution;
      pending = data;
      apply.disabled = proposal.action !== 'replace';
      result.textContent = `Status: ${proposal.status}\nAction: ${proposal.action}` +
        (proposal.action === 'replace' ? `\nCandidate: ${proposal.replacement}` : '') +
        `\nReason: ${proposal.reason}\nSaved audited TF bundle: ${data.output}` +
        '\nOriginal source reading is unchanged. Review the candidate before applying it.';
    } catch (error) {
      result.textContent = error.message;
    } finally {
      run.disabled = !pinned;
    }
  });
  apply.addEventListener('click', async () => {
    if (!pending || pending.report.resolution.action !== 'replace') return;
    apply.disabled = true;
    result.textContent += '\nApplying reviewed candidate…';
    try {
      const data = await post('/api/apply', {
        proposal_id: pending.proposal_id,
        resolution_id: pending.report.resolution.id,
        expected_replacement: pending.report.resolution.replacement,
      });
      pending = null;
      result.textContent = `Status: ${data.report.resolution.status}\n` +
        `Corrected reading feature: ${data.report.derived_text_feature}\n` +
        `Saved TF bundle: ${data.output}\nOriginal TF text and source slots remain unchanged.`;
    } catch (error) {
      result.textContent = error.message;
      apply.disabled = false;
    }
  });
})();
