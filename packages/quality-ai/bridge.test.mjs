import { test } from 'node:test';
import assert from 'node:assert/strict';
import { MockLanguageModelV4 } from 'ai/test';
import { correct } from './bridge.mjs';

const request = { task: 'spelling', model: 'google/gemini-3.5-flash-lite',
  context: 'helllo', issues: [{ id: 0, text: 'helllo', score: 90 }] };
function model(output) {
  return new MockLanguageModelV4({ doGenerate: async () => ({
    content: [{ type: 'text', text: JSON.stringify(output) }],
    finishReason: { unified: 'stop', raw: undefined },
    usage: { inputTokens: { total: 10 }, outputTokens: { total: 20 } },
    warnings: [],
  }) });
}
test('SDK validates structured proposals and returns usage provenance', async () => {
  const edit = { id: 0, before: 'helllo', after: 'hello', reason: 'Repeated letter' };
  const result = await correct(request, model({ edits: [edit], unresolved: [] }));
  assert.deepEqual(result.edits, [edit]);
  assert.equal(result.model, request.model);
  assert.equal(result.usage.inputTokens, 10);
});
test('SDK rejects invalid model output', async () => {
  await assert.rejects(correct(request, model({ edits: [{ id: -1 }], unresolved: [] })));
});
test('oversized input is rejected before any provider request', async () => {
  await assert.rejects(correct({ ...request, context: 'x'.repeat(100001) }, model({})));
});
