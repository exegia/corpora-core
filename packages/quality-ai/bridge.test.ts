import { test } from "node:test";
import assert from "node:assert/strict";
import { MockLanguageModelV4 } from "ai/test";
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { correct } from './bridge.js';

const request = {
  task: "spelling",
  model: "google/gemini-3.5-flash-lite",
  context: "helllo",
  issues: [{ id: 0, text: "helllo", score: 90 }],
};
function model(output: unknown): MockLanguageModelV4 {
  return new MockLanguageModelV4({
    doGenerate: async () => ({
      content: [{ type: "text", text: JSON.stringify(output) }],
      finishReason: { unified: "stop", raw: undefined },
      usage: {
            inputTokens: { total: 10, noCache: 10, cacheRead: 0, cacheWrite: 0 },
            outputTokens: { total: 20, text: 20, reasoning: 0 },
          },
      warnings: [],
    }),
  });
}
test("SDK validates structured proposals and returns usage provenance", async () => {
  const edit = { id: 0, before: "helllo", after: "hello", reason: "Repeated letter" };
  const result = await correct(request, model({ edits: [edit], unresolved: [] }));
  assert.deepEqual(result.edits, [edit]);
  assert.equal(result.model, request.model);
  assert.equal(result.usage.inputTokens, 10);
});
test("SDK rejects invalid model output", async () => {
  await assert.rejects(correct(request, model({ edits: [{ id: -1 }], unresolved: [] })));
});
test('oversized input is rejected before any provider request', async () => {
  await assert.rejects(correct({ ...request, context: 'x'.repeat(100001) }, model({})));
});

function runCLI(input: string) {
  return spawnSync(process.execPath, [fileURLToPath(new URL('./bridge.js', import.meta.url))], {
    input,
    encoding: 'utf8',
    env: { ...process.env, AI_GATEWAY_API_KEY: '' },
    timeout: 10_000,
  });
}

test('built CLI returns a sanitized error for missing credentials', () => {
  const result = runCLI(JSON.stringify(request));
  assert.ifError(result.error);
  assert.equal(result.status, 1);
  assert.equal(result.stderr, '');
  assert.deepEqual(JSON.parse(result.stdout), { error: 'not_configured' });
});

test('built CLI returns a sanitized error for malformed JSON', () => {
  const result = runCLI('{');
  assert.ifError(result.error);
  assert.equal(result.status, 1);
  assert.equal(result.stderr, '');
  assert.deepEqual(JSON.parse(result.stdout), { error: 'request_failed' });
});
