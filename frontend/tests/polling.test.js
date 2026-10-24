import assert from "node:assert/strict";
import { test } from "node:test";
import { startPolling } from "../src/utils/polling.js";

const flush = () => new Promise((resolve) => setImmediate(resolve));

test("polling never overlaps, queues one manual refresh, and aborts on stop", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"], now: 1000 });
  let calls = 0;
  let release;
  let signal;
  const poller = startPolling((currentSignal) => {
    calls += 1;
    signal = currentSignal;
    return new Promise((resolve) => { release = resolve; });
  }, { intervalMs: 300000 });
  t.mock.timers.tick(0);
  t.mock.timers.tick(900000);
  poller.refresh();
  poller.refresh();
  assert.equal(calls, 1);
  release();
  await flush();
  t.mock.timers.tick(0);
  assert.equal(calls, 2);
  poller.stop();
  assert.equal(signal.aborted, true);
  release();
  await flush();
  t.mock.timers.tick(900000);
  assert.equal(calls, 2);
});

test("hidden admin tabs stop polling and resume with one fresh request", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"], now: 1000 });
  const documentTarget = new EventTarget();
  documentTarget.visibilityState = "visible";
  let calls = 0;
  const poller = startPolling(async () => { calls += 1; }, { intervalMs: 60000, documentTarget });
  t.mock.timers.tick(0);
  await flush();
  documentTarget.visibilityState = "hidden";
  documentTarget.dispatchEvent(new Event("visibilitychange"));
  t.mock.timers.tick(300000);
  assert.equal(calls, 1);
  documentTarget.visibilityState = "visible";
  documentTarget.dispatchEvent(new Event("visibilitychange"));
  t.mock.timers.tick(0);
  await flush();
  assert.equal(calls, 2);
  poller.stop();
});

test("display sync runs every five minutes and continues when hidden", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"], now: 1000 });
  const documentTarget = new EventTarget();
  documentTarget.visibilityState = "hidden";
  let calls = 0;
  const poller = startPolling(async () => { calls += 1; }, {
    intervalMs: 300000, pauseWhenHidden: false, documentTarget,
  });
  t.mock.timers.tick(0);
  await flush();
  t.mock.timers.tick(299999);
  assert.equal(calls, 1);
  t.mock.timers.tick(1);
  await flush();
  assert.equal(calls, 2);
  poller.stop();
});

test("failed requests back off instead of retrying continuously", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"], now: 1000 });
  let calls = 0;
  const poller = startPolling(async () => { calls += 1; throw new Error("offline"); }, { intervalMs: 1000 });
  t.mock.timers.tick(0);
  await flush();
  t.mock.timers.tick(1999);
  assert.equal(calls, 1);
  t.mock.timers.tick(1);
  await flush();
  assert.equal(calls, 2);
  poller.stop();
});
