import test from "node:test";
import assert from "node:assert/strict";
import { createSaveRequest } from "../src/utils/saveRequest.js";

function memoryStorage() {
  const items = new Map();
  return { getItem: (k) => items.get(k), setItem: (k,v) => items.set(k,v), removeItem: (k) => items.delete(k) };
}
const ready = { version: { id: 1, status: "ready", png_url: "/api/media/1" } };
const payload = { rates: { USD: "16000" }, title: "Board" };

test("duplicate clicks share one save; retry after lost response reuses its key", async () => {
  const calls = [];
  const save = createSaveRequest(async (body) => { calls.push(body); if (calls.length === 1) throw Error("response lost"); return ready; }, memoryStorage());
  const first = save.save(payload);
  assert.equal(save.save(payload), first);
  await assert.rejects(first, /lost/);
  assert.equal((await save.save(payload)).id, 1);
  assert.equal(calls.length, 2);
  assert.equal(calls[0].idempotency_key, calls[1].idempotency_key);
});

test("reload preserves identity; changed payload or explicit new board starts a new save", async () => {
  const keys = [], storage = memoryStorage();
  const send = async (body) => { keys.push(body.idempotency_key); return ready; };
  await createSaveRequest(send, storage).save(payload);
  const reloaded = createSaveRequest(send, storage);
  await reloaded.save({ title: "Board", rates: { USD: "16000" } });
  assert.equal(keys[0], keys[1]);
  await reloaded.save({ ...payload, title: "Changed" });
  assert.notEqual(keys[1], keys[2]);
  reloaded.reset();
  await reloaded.save({ ...payload, title: "Changed" });
  assert.notEqual(keys[2], keys[3]);
});

test("incomplete generation never reports success", async () => {
  for (const version of [{ status: "generating", png_url: "/1" }, { status: "ready" }]) {
    await assert.rejects(createSaveRequest(async () => ({ version }), memoryStorage()).save(payload), /belum siap/);
  }
});

test("unmount aborts the request without losing retry identity", async () => {
  let received;
  const save = createSaveRequest(async (_body, { signal }) => { received = signal; return ready; }, memoryStorage());
  const pending = save.save(payload);
  save.cancel();
  await pending;
  assert.equal(received.aborted, true);
});
