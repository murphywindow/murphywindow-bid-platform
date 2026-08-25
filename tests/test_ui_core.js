"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const {
  parseClipboardMatrix,
  parseColumnValue,
  mapClipboard,
  nextEditablePosition,
  arrowNavigationIntent,
  horizontalVisibilityDelta,
  clampedHorizontalScroll,
  cycleSort,
  naturalCompare,
  compareSortValues,
  stableSortRows,
  visiblePasteRows,
  SortStateStore,
  activeHistoryBand,
  clampHistoryMarker,
  normalizeDecimalPrecision,
  formatNumeric,
  comparisonChangedSegment,
  calculateTooltipPosition,
  DraftStore,
  PendingCellStore,
  meaningfulValue,
  countLabel,
  TableController,
  AutocompleteController,
  TooltipController,
  DrawerController
} = require("../app/static/ui-core.js");

test("comparison intravalue emphasis requires unchanged surrounding text", () => {
  assert.deepEqual(comparisonChangedSegment("Backpans from OBE", "Backpans from Hart"), {prefix:"Backpans from ",changed:"Hart",suffix:""});
  assert.deepEqual(comparisonChangedSegment("Clear anodized finish", "Dark bronze finish"), {prefix:"",changed:"Dark bronze",suffix:" finish"});
  assert.equal(comparisonChangedSegment("5", "6"), null);
  assert.equal(comparisonChangedSegment("Standard", "Steel-reinforced"), null);
  assert.equal(comparisonChangedSegment("Same", "Same"), null);
});

test("traditional sorting cycles and Shift-click maintains an ordered multi-column stack", () => {
  let stack = cycleSort([], "code");
  assert.deepEqual(stack, [{ key: "code", direction: "asc" }]);
  stack = cycleSort(stack, "code");
  assert.deepEqual(stack, [{ key: "code", direction: "desc" }]);
  stack = cycleSort(stack, "code");
  assert.deepEqual(stack, []);
  stack = cycleSort([{ key: "vendor", direction: "asc" }], "code", true);
  assert.deepEqual(stack, [{ key: "vendor", direction: "asc" }, { key: "code", direction: "asc" }]);
  stack = cycleSort(stack, "code", true);
  assert.equal(stack[1].direction, "desc");
  stack = cycleSort(stack, "code", true);
  assert.deepEqual(stack, [{ key: "vendor", direction: "asc" }]);
  assert.deepEqual(cycleSort(stack, "price"), [{ key: "price", direction: "asc" }]);
});

test("stable raw-value sorting handles numbers, dates, natural codes, blanks, and canonical restoration", () => {
  const rows = [
    { id: "a", code: "08 10 2", price: "10", date: "2026-08-20" },
    { id: "b", code: "08 10 10", price: null, date: "" },
    { id: "c", code: "08 10 2", price: "2", date: "2026-08-19" },
  ];
  const columns = [{ key: "code" }, { key: "price", type: "currency" }, { key: "date", type: "date" }];
  assert.ok(naturalCompare("ALT2", "ALT10") < 0);
  assert.equal(compareSortValues(null, 0, "number"), 1);
  assert.deepEqual(stableSortRows(rows, [{ key: "price", direction: "asc" }], columns).map(row => row.id), ["c", "a", "b"]);
  assert.deepEqual(stableSortRows(rows, [{ key: "price", direction: "desc" }], columns).map(row => row.id), ["a", "c", "b"]);
  assert.deepEqual(stableSortRows(rows, [{ key: "code", direction: "asc" }, { key: "date", direction: "asc" }], columns).map(row => row.id), ["c", "a", "b"]);
  assert.deepEqual(stableSortRows(rows, [], columns), rows);
});

test("sort state stays browser-only and discards only removed columns", () => {
  const values = new Map();
  const storage = {getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)};
  const store = new SortStateStore(storage);
  store.set("project/quotes/base", [{key:"vendor",direction:"asc"},{key:"removed",direction:"desc"}]);
  assert.deepEqual(store.get("project/quotes/base", ["vendor", "price"]), [{key:"vendor",direction:"asc"}]);
  assert.deepEqual(JSON.parse([...values.values()][0]), [{key:"vendor",direction:"asc"}]);
});

function fakeDom() {
  const listenerMethods = target => {
    target._listeners = new Map();
    target.addEventListener = (type, handler) => {
      if (!target._listeners.has(type)) target._listeners.set(type, new Set());
      target._listeners.get(type).add(handler);
    };
    target.removeEventListener = (type, handler) => target._listeners.get(type)?.delete(handler);
    target.emit = (type, init = {}) => {
      const event = {
        type,
        target: init.target || target,
        relatedTarget: init.relatedTarget || null,
        key: init.key,
        defaultPrevented: false,
        preventDefault() { this.defaultPrevented = true; },
        ...init
      };
      for (const handler of target._listeners.get(type) || []) handler(event);
      return event;
    };
  };

  class FakeElement {
    constructor(tagName, ownerDocument) {
      this.tagName = String(tagName).toUpperCase();
      this.ownerDocument = ownerDocument;
      this.nodeType = 1;
      this.parentElement = null;
      this.children = [];
      this.attributes = new Map();
      this.dataset = {};
      this.style = {};
      this.hidden = false;
      this.inert = false;
      this.isConnected = false;
      this.focusCount = 0;
      this.rect = { left: 100, right: 140, top: 80, bottom: 100, width: 40, height: 20 };
      this._innerHTML = "";
      this.textContent = "";
      listenerMethods(this);
    }
    _connect(value) {
      this.isConnected = value;
      this.children.forEach(child => child._connect(value));
    }
    appendChild(child) {
      child.parentElement?.children.splice(child.parentElement.children.indexOf(child), 1);
      child.parentElement = this;
      this.children.push(child);
      child._connect(this.isConnected);
      return child;
    }
    replaceChildren(...children) {
      this.children.forEach(child => { child.parentElement = null; child._connect(false); });
      this.children = [];
      children.forEach(child => this.appendChild(child));
      this._innerHTML = "";
    }
    remove() {
      if (!this.parentElement) return;
      const index = this.parentElement.children.indexOf(this);
      if (index >= 0) this.parentElement.children.splice(index, 1);
      this.parentElement = null;
      this._connect(false);
    }
    contains(node) {
      for (let current = node; current; current = current.parentElement) if (current === this) return true;
      return false;
    }
    matches(selector) {
      const match = selector.trim().match(/^\[([^\]]+)\]$/);
      return Boolean(match && this.attributes.has(match[1]));
    }
    closest(selector) {
      const selectors = selector.split(",").map(value => value.trim());
      for (let current = this; current; current = current.parentElement) {
        if (selectors.some(value => current.matches(value))) return current;
      }
      return null;
    }
    querySelector(selector) {
      for (const child of this.children) {
        if (child.matches(selector)) return child;
        const nested = child.querySelector(selector);
        if (nested) return nested;
      }
      return null;
    }
    querySelectorAll(selector) {
      const matches = [];
      for (const child of this.children) {
        if (child.matches(selector)) matches.push(child);
        matches.push(...child.querySelectorAll(selector));
      }
      return matches;
    }
    setAttribute(name, value) {
      const text = String(value);
      this.attributes.set(name, text);
      if (name.startsWith("data-")) {
        const key = name.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
        this.dataset[key] = text;
      }
    }
    getAttribute(name) { return this.attributes.has(name) ? this.attributes.get(name) : null; }
    hasAttribute(name) { return this.attributes.has(name); }
    removeAttribute(name) {
      this.attributes.delete(name);
      if (name.startsWith("data-")) {
        const key = name.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
        delete this.dataset[key];
      }
    }
    getBoundingClientRect() { return this.rect; }
    focus() { this.focusCount += 1; this.ownerDocument.activeElement = this; }
    set innerHTML(value) { this.replaceChildren(); this._innerHTML = String(value); }
    get innerHTML() { return this._innerHTML; }
  }

  const view = { innerWidth: 320, innerHeight: 200 };
  listenerMethods(view);
  const document = { defaultView: view, activeElement: null };
  listenerMethods(document);
  document.createElement = tagName => new FakeElement(tagName, document);
  document.documentElement = document.createElement("html");
  document.documentElement.clientWidth = view.innerWidth;
  document.documentElement.clientHeight = view.innerHeight;
  document.documentElement._connect(true);
  document.body = document.createElement("body");
  document.documentElement.appendChild(document.body);
  document.activeElement = document.body;
  return { document, view };
}

test("clipboard parsing preserves a rectangular Excel range", () => {
  assert.deepEqual(parseClipboardMatrix("A\tB\r\nC\t\r\n"), [["A", "B"], ["C", ""]]);
});

test("clipboard mapping consumes values across editable destinations and never writes calculated columns", () => {
  const columns = [
    { key: "mark", editable: true },
    { key: "quantity", editable: true },
    { key: "square_feet", calc: () => 0 },
    { key: "notes", editable: true }
  ];
  assert.deepEqual(mapClipboard(columns, 1, [["2", "note"]]), [
    { rowOffset: 0, columnIndex: 1, field: "quantity", value: "2" },
    { rowOffset: 0, columnIndex: 3, field: "notes", value: "note" }
  ]);
});

test("rectangular paste follows visible sorted row order instead of canonical storage order", () => {
  const rows = [{ id: "a" }, { id: "b" }, { id: "c" }, { id: "d" }];
  const visible = visiblePasteRows(rows, ["c", "a", "d", "b"]);
  const start = visible.findIndex(row => row.id === "a");
  assert.deepEqual(visible.slice(start, start + 2).map(row => row.id), ["a", "d"]);
});

test("rectangular paste does not spill into rows hidden from a filtered table", () => {
  const rows = [{ id: "a" }, { id: "b" }, { id: "c" }, { id: "d" }];
  assert.deepEqual(visiblePasteRows(rows, ["c", "a"]).map(row => row.id), ["c", "a"]);
  assert.deepEqual(visiblePasteRows(rows).map(row => row.id), ["a", "b", "c", "d"]);
});

test("pasted grid values normalize valid Excel text and reject values the controls would hide", () => {
  assert.deepEqual(parseColumnValue({ type: "number" }, "1,250.5"), { handled: true, value: "1250.5" });
  assert.throws(() => parseColumnValue({ type: "number" }, "N/A"), /valid number/);
  assert.deepEqual(parseColumnValue({ type: "date" }, "8/19/2026"), { handled: true, value: "2026-08-19" });
  assert.throws(() => parseColumnValue({ type: "date" }, "2/30/2026"), /valid calendar date/);
  const select = { type: "select", label: "Credit type", values: [["percentage", "Percentage"], ["dollar", "Dollar amount"]] };
  assert.deepEqual(parseColumnValue(select, "Dollar amount"), { handled: true, value: "dollar" });
  assert.throws(() => parseColumnValue(select, "Unsupported"), /valid credit type/);
  assert.deepEqual(parseColumnValue({ type: "checkbox" }, "FALSE"), { handled: true, value: false });
});

test("Tab moves horizontally and Enter moves down the same editable column", () => {
  const rows = [[0, 1, 3], [0, 1, 3], [0, 1, 3]];
  assert.deepEqual(nextEditablePosition(rows, 0, 1, 1, false), { rowIndex: 0, columnIndex: 3 });
  assert.deepEqual(nextEditablePosition(rows, 0, 1, 1, true), { rowIndex: 1, columnIndex: 1 });
});

test("table arrows navigate selected cells while left and right preserve text editing", () => {
  const selectedText = { value: "125.00", selectionStart: 0, selectionEnd: 6 };
  assert.deepEqual(arrowNavigationIntent(selectedText, "ArrowLeft"), { direction: -1, sameColumn: false });
  assert.deepEqual(arrowNavigationIntent(selectedText, "ArrowRight"), { direction: 1, sameColumn: false });
  assert.deepEqual(arrowNavigationIntent(selectedText, "ArrowUp"), { direction: -1, sameColumn: true });
  assert.deepEqual(arrowNavigationIntent(selectedText, "ArrowDown"), { direction: 1, sameColumn: true });

  const editingText = { value: "125.00", selectionStart: 3, selectionEnd: 3 };
  assert.equal(arrowNavigationIntent(editingText, "ArrowLeft"), null);
  assert.equal(arrowNavigationIntent(editingText, "ArrowRight"), null);
  assert.deepEqual(arrowNavigationIntent(editingText, "ArrowUp"), { direction: -1, sameColumn: true });

  const numberInput = { value: "125", selectionStart: null, selectionEnd: null };
  assert.deepEqual(arrowNavigationIntent(numberInput, "ArrowUp"), { direction: -1, sameColumn: true });
  assert.deepEqual(arrowNavigationIntent(numberInput, "ArrowRight"), { direction: 1, sameColumn: false });
});

test("focused table cells keep their full width inside the horizontal viewport", () => {
  assert.equal(horizontalVisibilityDelta(120, 180, 100, 300), 0);
  assert.equal(horizontalVisibilityDelta(80, 140, 100, 300), -20);
  assert.equal(horizontalVisibilityDelta(260, 320, 100, 300), 20);
  assert.equal(clampedHorizontalScroll(590, 25, 900, 300), 600);
  assert.equal(clampedHorizontalScroll(5, -25, 900, 300), 0);
});

test("frame focus scrolling reveals a cell hidden underneath frozen Qty", () => {
  const root = { addEventListener() {} };
  const controller = new TableController(root);
  const wrap = { scrollWidth: 900, clientWidth: 300, scrollLeft: 200, classList: { contains: name => name === "frame-grid" }, getBoundingClientRect: () => ({ left: 0, right: 300 }) };
  const frozenQty = { getBoundingClientRect: () => ({ left: 60, right: 140 }) };
  const actions = { getBoundingClientRect: () => ({ left: 270, right: 300 }) };
  const row = { children: [{}, frozenQty], querySelector: selector => selector === ".row-action-cell" ? actions : null };
  const table = { classList: { contains: () => false } };
  const cell = {
    cellIndex: 2,
    parentElement: row,
    getBoundingClientRect: () => ({ left: 120, right: 200 }),
    closest: selector => selector === ".table-wrap" ? wrap : selector === "table" ? table : null
  };
  row.children.push(cell);
  controller.ensureFocusVisible({ closest: selector => selector === "td, th" ? cell : null });
  assert.equal(wrap.scrollLeft, 180);
});

test("five-band history visualization activates every range without classification logic", () => {
  const bands = [
    { start: 0, end: 20 }, { start: 20, end: 40 }, { start: 40, end: 60 },
    { start: 60, end: 80 }, { start: 80, end: 100 }
  ];
  assert.deepEqual([5, 25, 50, 75, 95].map(value => activeHistoryBand(value, bands)), [0, 1, 2, 3, 4]);
  assert.equal(activeHistoryBand(100, bands), 4);
  assert.equal(activeHistoryBand(null, bands), -1);
  assert.equal(activeHistoryBand(undefined, bands), -1);
});

test("history markers remain visible at distribution extremes", () => {
  assert.deepEqual(
    [0, 1, 25, 50, 75, 99, 100].map(value => clampHistoryMarker(value)),
    [2, 2, 25, 50, 75, 98, 98]
  );
});

test("semantic precision changes presentation without changing the raw number", () => {
  const raw = "109.87654321";
  const settings = normalizeDecimalPrecision({currency:0,percentage:3,quantity:1,square_footage:4});
  assert.equal(formatNumeric(raw,"currency",settings,{currency:"USD"}), "$110");
  assert.equal(formatNumeric(raw,"percentage",settings), "109.877");
  assert.equal(formatNumeric(raw,"quantity",settings), "109.9");
  assert.equal(formatNumeric(raw,"square_footage",settings), "109.8765");
  assert.equal(raw, "109.87654321");
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
  drafts.set("quotes-08", "vendor", "Vendor A");
  drafts.clear();
  assert.deepEqual(drafts.get("frames/sec-1", { quantity: 1 }), { quantity: 1 });
  assert.deepEqual(drafts.get("quotes-08", { vendor: "" }), { vendor: "" });

  const pending = new PendingCellStore();
  pending.set("equipment", "eqp-1", "code", "BAD", "Unknown code");
  assert.equal(pending.all().length, 1);
  pending.clear("equipment", "eqp-1", "code");
  assert.equal(pending.all().length, 0);
});

test("table promotion ends the explicit draft without creating a replacement row", () => {
  const { document } = fakeDom();
  const root = document.createElement("main");
  const table = document.createElement("div");
  const row = document.createElement("div");
  const cell = document.createElement("input");
  const actions = document.createElement("div");
  root.appendChild(table);
  table.appendChild(row);
  row.appendChild(cell);
  row.appendChild(actions);
  document.body.appendChild(root);

  table.setAttribute("data-edit-table", "frames-sec-1");
  row.setAttribute("data-table-row", "");
  row.setAttribute("data-row-kind", "draft");
  row.setAttribute("data-row-id", "draft-frames-sec-1");
  row.classList = { remove() {} };
  cell.setAttribute("data-table-cell", "");
  cell.setAttribute("data-field", "mark");
  cell.setAttribute("data-draft", "true");
  cell.value = "A1";
  cell.type = "text";
  actions.setAttribute("data-draft-actions", "");

  let insertedHtml = null;
  row.insertAdjacentHTML = (position, html) => {
    assert.equal(position, "afterend");
    insertedHtml = html;
    const replacement = document.createElement("div");
    replacement.setAttribute("data-table-row", "");
    replacement.setAttribute("data-row-kind", "draft");
    table.appendChild(replacement);
    row.nextElementSibling = replacement;
  };

  let promoted = null;
  const controller = new TableController(root, {
    drafts: new DraftStore(),
    draftDefaults: () => ({ mark: "" }),
    promoteDraft: () => ({
      ok: true,
      rowId: "frm-1",
      paths: { mark: "takeoff_sections.0.lines.0.mark" },
      actionsHtml: "<button>Remove</button>"
    }),
    afterPromote: context => { promoted = context; }
  });

  const result = controller.promoteDraft(cell, "entry-1");
  assert.equal(result.rowId, "frm-1");
  assert.equal(row.dataset.rowKind, "persisted");
  assert.equal(row.dataset.rowId, "frm-1");
  assert.equal(cell.dataset.path, "takeoff_sections.0.lines.0.mark");
  assert.equal(insertedHtml, null);
  assert.equal(promoted.tableId, "frames-sec-1");
  assert.equal(promoted.table, table);
  assert.equal(promoted.row, row);
  assert.equal(promoted.rowId, "frm-1");
  assert.equal(promoted.newDraftRow, null);
  assert.equal(promoted.cell, cell);
  assert.equal(promoted.result, result);
  assert.equal(promoted.correlationId, "entry-1");
});

test("meaningful row detection ignores false and blank values", () => {
  assert.equal(meaningfulValue(false), false);
  assert.equal(meaningfulValue("  "), false);
  assert.equal(meaningfulValue(0), true);
  assert.equal(meaningfulValue("A1"), true);
});

test("shared count labels handle regular and irregular plurals", () => {
  assert.equal(countLabel(1, "frame"), "1 frame");
  assert.equal(countLabel(2, "frame"), "2 frames");
  assert.equal(countLabel(1, "foot"), "1 foot");
  assert.equal(countLabel(2, "foot"), "2 feet");
  assert.equal(countLabel(1, "linear foot"), "1 linear foot");
  assert.equal(countLabel(2, "linear foot"), "2 feet");
  assert.equal(countLabel(1, "sausage"), "1 sausage");
  assert.equal(countLabel(2, "sausage"), "2 sausages");
});

test("tooltip positioning prefers a centered placement above the trigger", () => {
  assert.deepEqual(
    calculateTooltipPosition(
      { left: 100, right: 140, top: 80, bottom: 100 },
      { width: 80, height: 30 },
      { width: 300, height: 200 }
    ),
    { left: 80, top: 42, placement: "above" }
  );
});

test("tooltip positioning falls below a top-edge trigger and clamps to the viewport", () => {
  assert.deepEqual(
    calculateTooltipPosition(
      { left: 4, right: 24, top: 3, bottom: 23 },
      { width: 80, height: 30 },
      { width: 100, height: 100 }
    ),
    { left: 8, top: 31, placement: "below" }
  );
});

test("tooltip positioning clamps the right edge without covering the trigger", () => {
  assert.deepEqual(
    calculateTooltipPosition(
      { left: 280, right: 300, top: 80, bottom: 100 },
      { width: 100, height: 40 },
      { width: 320, height: 180 }
    ),
    { left: 212, top: 32, placement: "above" }
  );
});

test("tooltip and drawer controllers remain available in CommonJS builds", () => {
  assert.equal(typeof AutocompleteController, "function");
  assert.equal(typeof TooltipController, "function");
  assert.equal(typeof DrawerController, "function");
});

test("autocomplete exposes listbox focus and clamps its popup in a short viewport", async () => {
  const { document, view } = fakeDom();
  const input = document.createElement("input");
  const popup = document.createElement("div");
  document.body.appendChild(input);
  document.body.appendChild(popup);
  input.value = "mu";
  const controller = new AutocompleteController(input, {
    popup,
    window: view,
    search: async () => [{ label: "Murphy Window" }, { label: "Murphy Glass" }],
    render: (box, items) => {
      box.replaceChildren(...items.map((item, index) => {
        const option = document.createElement("div");
        option.setAttribute("data-autocomplete-index", index);
        option.textContent = item.label;
        return option;
      }));
    },
    select() {}
  });
  await controller.search();
  assert.equal(input.getAttribute("role"), "combobox");
  assert.equal(input.getAttribute("aria-controls"), popup.id);
  assert.equal(popup.getAttribute("role"), "listbox");
  assert.equal(popup.children[0].getAttribute("role"), "option");
  assert.equal(popup.children[0].getAttribute("aria-selected"), "true");
  assert.equal(input.getAttribute("aria-activedescendant"), popup.children[0].id);
  assert.ok(Number.parseFloat(popup.style.top) >= 8);
  assert.ok(Number.parseFloat(popup.style.left) >= 8);

  input.emit("keydown", { target: input, key: "ArrowDown" });
  assert.equal(input.getAttribute("aria-activedescendant"), popup.children[1].id);
  controller.close();
  assert.equal(input.getAttribute("aria-activedescendant"), null);
});

test("delegated tooltip intent supports pointer, focus, Escape, and ARIA cleanup", async () => {
  const { document, view } = fakeDom();
  const root = document.createElement("main");
  const trigger = document.createElement("button");
  trigger.setAttribute("data-tooltip", "Project-only override");
  trigger.setAttribute("aria-describedby", "existing-help");
  root.appendChild(trigger);
  document.body.appendChild(root);
  const controller = new TooltipController(root, { document, window: view, delay: 0 });

  root.emit("pointerover", { target: trigger });
  assert.equal(controller.tooltip.hidden, true);
  await new Promise(resolve => setTimeout(resolve, 5));
  assert.equal(controller.tooltip.hidden, false);
  assert.equal(controller.tooltip.textContent, "Project-only override");
  assert.match(trigger.getAttribute("aria-describedby"), /existing-help tooltip_/);

  root.emit("pointerout", { target: trigger });
  assert.equal(controller.tooltip.hidden, true);
  assert.equal(trigger.getAttribute("aria-describedby"), "existing-help");

  root.emit("focusin", { target: trigger });
  await new Promise(resolve => setTimeout(resolve, 5));
  assert.equal(controller.tooltip.hidden, false);
  root.emit("focusout", { target: trigger });
  assert.equal(controller.tooltip.hidden, true);

  root.emit("focusin", { target: trigger });
  await new Promise(resolve => setTimeout(resolve, 5));
  const escape = document.emit("keydown", { target: trigger, key: "Escape" });
  assert.equal(escape.defaultPrevented, true);
  assert.equal(controller.tooltip.hidden, true);
  assert.equal(trigger.getAttribute("aria-describedby"), "existing-help");
  controller.destroy();
});

test("validation tooltip attributes added or removed on a focused cell reconcile immediately", async () => {
  const { document, view } = fakeDom();
  const root = document.createElement("main");
  const input = document.createElement("input");
  root.appendChild(input);
  document.body.appendChild(root);
  document.activeElement = input;
  let notify = null, observed = null;
  class FakeMutationObserver {
    constructor(callback) { notify = callback; }
    observe(target, options) { observed = { target, options }; }
    disconnect() {}
  }
  const controller = new TooltipController(root, { document, window: view, delay: 0, MutationObserver: FakeMutationObserver });
  assert.equal(observed.options.attributes, true);
  assert.deepEqual(observed.options.attributeFilter, ["data-tooltip"]);

  input.setAttribute("data-tooltip", "Choose a controlled Cost Code");
  notify([{ type: "attributes", attributeName: "data-tooltip", target: input }]);
  await new Promise(resolve => setTimeout(resolve, 5));
  assert.equal(controller.tooltip.hidden, false);
  assert.equal(controller.tooltip.textContent, "Choose a controlled Cost Code");
  assert.match(input.getAttribute("aria-describedby"), /tooltip_/);

  input.removeAttribute("data-tooltip");
  notify([{ type: "attributes", attributeName: "data-tooltip", target: input }]);
  assert.equal(controller.tooltip.hidden, true);
  assert.equal(input.getAttribute("aria-describedby"), null);
  controller.destroy();
});

test("modal drawer isolates and restores the background while preserving opener state", () => {
  const { document } = fakeDom();
  const application = document.createElement("main");
  application.setAttribute("aria-hidden", "false");
  const opener = document.createElement("button");
  application.appendChild(opener);
  document.body.appendChild(application);
  const alreadyInert = document.createElement("footer");
  alreadyInert.setAttribute("aria-hidden", "true");
  alreadyInert.setAttribute("inert", "");
  alreadyInert.inert = true;
  document.body.appendChild(alreadyInert);
  const drawer = new DrawerController(document.body, { document });
  const backdrop = drawer.layer.querySelector("[data-drawer-backdrop]");
  const closeButton = drawer.layer.querySelector("[data-drawer-close]");
  const setApplicationAttribute = application.setAttribute.bind(application);
  let activeWhenBackgroundHidden = null;
  application.setAttribute = (name, value) => {
    if (name === "aria-hidden" && value === "true") activeWhenBackgroundHidden = document.activeElement;
    setApplicationAttribute(name, value);
  };

  drawer.open("<p>Historical evidence</p>", { opener, label: "Historical detail" });
  assert.equal(drawer.isOpen, true);
  assert.equal(drawer.panel.getAttribute("role"), "dialog");
  assert.equal(drawer.panel.getAttribute("aria-modal"), "true");
  assert.equal(drawer.panel.getAttribute("aria-hidden"), "false");
  assert.equal(opener.getAttribute("aria-expanded"), "true");
  assert.equal(activeWhenBackgroundHidden, drawer.panel);
  assert.equal(application.getAttribute("aria-hidden"), "true");
  assert.equal(application.hasAttribute("inert"), true);
  assert.equal(application.inert, true);
  assert.equal(alreadyInert.getAttribute("aria-hidden"), "true");
  assert.equal(alreadyInert.inert, true);
  drawer.layer.emit("click", { target: backdrop });
  assert.equal(drawer.isOpen, false);
  assert.equal(drawer.panel.getAttribute("aria-hidden"), "true");
  assert.equal(application.getAttribute("aria-hidden"), "false");
  assert.equal(application.hasAttribute("inert"), false);
  assert.equal(application.inert, false);
  assert.equal(alreadyInert.getAttribute("aria-hidden"), "true");
  assert.equal(alreadyInert.hasAttribute("inert"), true);
  assert.equal(alreadyInert.inert, true);
  assert.equal(document.activeElement, opener);

  drawer.open("Updated detail", { opener });
  drawer.layer.emit("click", { target: closeButton });
  assert.equal(drawer.isOpen, false);

  drawer.open("Keyboard detail", { opener });
  const escape = document.emit("keydown", { key: "Escape", target: drawer.panel });
  assert.equal(escape.defaultPrevented, true);
  assert.equal(drawer.isOpen, false);
  assert.equal(document.activeElement, opener);
  drawer.destroy();
});

test("modal drawer traps Tab and Shift+Tab and redirects escaped focus", () => {
  const { document } = fakeDom();
  const application = document.createElement("main");
  const opener = document.createElement("button");
  const outside = document.createElement("button");
  application.appendChild(opener);
  application.appendChild(outside);
  document.body.appendChild(application);
  const drawer = new DrawerController(document.body, { document });
  const content = document.createElement("div");
  const first = document.createElement("button");
  const hidden = document.createElement("button");
  hidden.hidden = true;
  const last = document.createElement("input");
  content.appendChild(first);
  content.appendChild(hidden);
  content.appendChild(last);
  drawer.open(content, { opener });
  const closeButton = drawer.layer.querySelector("[data-drawer-close]");

  document.activeElement = drawer.panel;
  let event = document.emit("keydown", { key: "Tab", target: drawer.panel });
  assert.equal(event.defaultPrevented, true);
  assert.equal(document.activeElement, closeButton);

  document.activeElement = last;
  event = document.emit("keydown", { key: "Tab", target: last });
  assert.equal(event.defaultPrevented, true);
  assert.equal(document.activeElement, closeButton);

  document.activeElement = closeButton;
  event = document.emit("keydown", { key: "Tab", shiftKey: true, target: closeButton });
  assert.equal(event.defaultPrevented, true);
  assert.equal(document.activeElement, last);

  document.activeElement = outside;
  document.emit("focusin", { target: outside });
  assert.equal(document.activeElement, closeButton);

  drawer.destroy();
  assert.equal(application.hasAttribute("inert"), false);
});
