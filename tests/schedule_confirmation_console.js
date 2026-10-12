'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../app/static/schedule/js/utils.js'), 'utf8');

async function scenario(method, url, data, needsConfirmation, accept) {
  const requests = [];
  const modals = [];
  const context = {
    window: {}, document: {addEventListener() {}},
    fetch: async (url, options) => {
      requests.push({url, options});
      return {ok: true, json: async () => url.endsWith('/preview') ? {
        requires_confirmation: needsConfirmation,
        segments: [{date: '2026-03-16', start_time: '08:00', end_time: '10:45'}],
      } : {id: 'saved'}};
    },
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  context.window.ScheduleApp.showConfirmModal = async (message, options) => {
    modals.push({message, options});
    assert.equal(requests.length, 1, 'no mutation is sent before confirmation');
    return accept;
  };
  const promise = context.window.ScheduleApp.api(method, url, data);
  if (needsConfirmation && !accept) {
    await assert.rejects(promise, error => error.cancelled === true);
    assert.equal(requests.length, 1, 'cancel sends preview only');
  } else {
    assert.equal((await promise).id, 'saved');
    assert.equal(requests.length, 2);
    assert.equal(requests[1].url, url);
    assert.deepEqual(JSON.parse(requests[1].options.body), data);
  }
  assert.equal(modals.length, needsConfirmation ? 1 : 0);
  if (needsConfirmation) {
    assert.ok(modals[0].message.includes('2026-03-16 08:00–10:45'));
    assert.equal(modals[0].options.okText, '배치');
    assert.equal(modals[0].options.cancelText, '취소');
  }
}

(async () => {
  await scenario('POST', '/schedule/api/blocks', {date: '2026-03-13', start_time: '16:30', end_time: '19:30'}, true, false);
  await scenario('POST', '/schedule/api/blocks', {date: '2026-03-13', start_time: '16:30', end_time: '19:30'}, true, true);
  await scenario('POST', '/schedule/api/blocks', {date: '2026-03-13', start_time: '16:00', end_time: '17:00'}, false, true);
  await scenario('PUT', '/schedule/api/blocks/blk_test', {date: '2026-03-13'}, true, false);
  await scenario('PUT', '/schedule/api/blocks/blk_test', {start_time: '16:30', end_time: '19:30', resize: true}, true, false);
  await scenario('POST', '/schedule/api/blocks/blk_test/split', {keep_test_item_ids: ['TC-001']}, true, false);
  await scenario('POST', '/schedule/api/blocks/blk_test/return-test_items', {keep_test_item_ids: ['TC-001']}, true, false);
})().catch(error => { console.error(error); process.exitCode = 1; });
