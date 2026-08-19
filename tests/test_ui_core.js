"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const {
  parseClipboardMatrix,
  mapClipboard,
  nextEditablePosition,
  DraftStore,
  PendingCellStore,
  meaningfulValue
} = require("../app/static/ui-core.js");

test("clipboard parsing preserves a rectangular Excel range", () => {
  assert.deepEqual(parseClipboardMatrix("A\tB\r\nC\t\r\n"), [["A", "B"], ["C", ""]]);
});

test("clipboard mapping consumes values across editable destinations and never writes calculated columns", () => {
  const columns = [
    { key: "mark", editable: true },
    { key: "quantity", editable: true },
    { key: "square_feet", readOnly: true },
    { key: "notes", editable: true }
  ];
  assert.deepEqual(mapClipboard(columns, 1, [["2", "note"]]), [
    { rowOffset: 0, columnIndex: 1, field: "quantity", value: "2" },
    { rowOffset: 0, columnIndex: 3, field: "notes", value: "note" }
  ]);
});

test("Tab moves horizontally and Enter moves down the same editable column", () => {
  const rows = [[0, 1, 3], [0, 1, 3], [0, 1, 3]];
  assert.deepEqual(nextEditablePosition(rows, 0, 1, 1, false), { rowIndex: 0, columnIndex: 3 });
  assert.deepEqual(nextEditablePosition(rows, 0, 1, 1, true), { rowIndex: 1, columnIndex: 1 });
});

test("navigation remains deterministic with one hundred populated rows and a draft", () => {
  const rows = Array.from({ length: 101 }, () => [0, 1, 2, 5]);
  assert.deepEqual(nextEditablePosition(rows, 99, 2, 1, true), { rowIndex: 100, columnIndex: 2 });
  assert.deepEqual(nextEditablePosition(rows, 99, 5, 1, false), { rowIndex: 100, columnIndex: 0 });
});

test("draft and pending values are UI state until deliberately consumed", () => {
  const drafts = new DraftStore();
  assert.deepEqual(drafts.get("frames/sec-1", { quantity: null }), { quantity: null });
  drafts.set("frames/sec-1", "mark", "A1");
  assert.equal(drafts.get("frames/sec-1").mark, "A1");
  drafts.reset("frames/sec-1", { quantity: null });
  assert.deepEqual(drafts.get("frames/sec-1"), { quantity: null });

  const pending = new PendingCellStore();
  pending.set("equipment", "eqp-1", "code", "BAD", "Unknown code");
  assert.equal(pending.all().length, 1);
  pending.clear("equipment", "eqp-1", "code");
  assert.equal(pending.all().length, 0);
});

test("meaningful row detection ignores false and blank values", () => {
  assert.equal(meaningfulValue(false), false);
  assert.equal(meaningfulValue("  "), false);
  assert.equal(meaningfulValue(0), true);
  assert.equal(meaningfulValue("A1"), true);
});
