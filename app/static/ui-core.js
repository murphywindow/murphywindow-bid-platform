(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.MWUI = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const meaningfulValue = value => value !== null && value !== undefined && value !== false && String(value).trim() !== "";

  function correlationId(prefix = "cor") {
    const value = globalThis.crypto?.randomUUID?.() || `${Date.now()}_${Math.random().toString(16).slice(2)}`;
    return `${prefix}_${value.replaceAll("-", "")}`;
  }

  function parseClipboardMatrix(text) {
    const normalized = String(text ?? "").replace(/\r\n?/g, "\n");
    const rows = normalized.split("\n");
    if (rows.length > 1 && rows.at(-1) === "") rows.pop();
    return rows.map(row => row.split("\t"));
  }

  function mapClipboard(columns, startColumn, matrix) {
    const mapped = [];
    const editableColumns = columns
      .map((column, columnIndex) => ({ column, columnIndex }))
      .filter(item => item.columnIndex >= startColumn && !item.column.readOnly && item.column.editable !== false);
    matrix.forEach((values, rowOffset) => {
      values.forEach((value, clipboardColumn) => {
        const destination = editableColumns[clipboardColumn];
        if (!destination) return;
        const { column, columnIndex } = destination;
        mapped.push({ rowOffset, columnIndex, field: column.key, value });
      });
    });
    return mapped;
  }

  function nextEditablePosition(rows, rowIndex, columnIndex, direction, sameColumn = false) {
    if (!rows.length) return null;
    if (sameColumn) {
      const nextRow = rowIndex + direction;
      if (nextRow < 0 || nextRow >= rows.length) return null;
      return rows[nextRow].includes(columnIndex) ? { rowIndex: nextRow, columnIndex } : null;
    }
    const positions = [];
    rows.forEach((columns, ri) => columns.forEach(ci => positions.push({ rowIndex: ri, columnIndex: ci })));
    const current = positions.findIndex(item => item.rowIndex === rowIndex && item.columnIndex === columnIndex);
    return current < 0 ? null : positions[current + direction] || null;
  }

  class DraftStore {
    constructor() { this.values = new Map(); }
    get(tableId, defaults = {}) {
      if (!this.values.has(tableId)) this.values.set(tableId, { ...defaults });
      return this.values.get(tableId);
    }
    set(tableId, field, value, defaults = {}) {
      const draft = this.get(tableId, defaults);
      draft[field] = value;
      return draft;
    }
    reset(tableId, defaults = {}) { this.values.set(tableId, { ...defaults }); return this.values.get(tableId); }
    delete(tableId) { this.values.delete(tableId); }
  }

  class PendingCellStore {
    constructor() { this.values = new Map(); }
    key(tableId, rowId, field) { return `${tableId}/${rowId}/${field}`; }
    set(tableId, rowId, field, value, message) {
      const issue = { tableId, rowId, field, value, message };
      this.values.set(this.key(tableId, rowId, field), issue);
      return issue;
    }
    clear(tableId, rowId, field) { this.values.delete(this.key(tableId, rowId, field)); }
    get(tableId, rowId, field) { return this.values.get(this.key(tableId, rowId, field)); }
    all() { return [...this.values.values()]; }
  }

  class TableController {
    constructor(rootElement, options = {}) {
      this.root = rootElement;
      this.options = options;
      this.drafts = options.drafts || new DraftStore();
      this.pending = options.pending || new PendingCellStore();
      this.onInput = this.onInput.bind(this);
      this.onChange = this.onChange.bind(this);
      this.onKeyDown = this.onKeyDown.bind(this);
      this.onPaste = this.onPaste.bind(this);
      rootElement.addEventListener("input", this.onInput);
      rootElement.addEventListener("change", this.onChange);
      rootElement.addEventListener("keydown", this.onKeyDown);
      rootElement.addEventListener("paste", this.onPaste);
    }

    cellFrom(event) { return event.target.closest?.("[data-table-cell]"); }
    tableFrom(cell) { return cell?.closest?.("[data-edit-table]"); }
    rowFrom(cell) { return cell?.closest?.("[data-table-row]"); }
    value(cell) { return cell.type === "checkbox" ? cell.checked : cell.value; }

    applyValidation(cell, result) {
      const table = this.tableFrom(cell), row = this.rowFrom(cell);
      if (!table || !row) return result;
      const tableId = table.dataset.editTable, rowId = row.dataset.rowId, field = cell.dataset.field;
      if (result?.ok === false) {
        this.pending.set(tableId, rowId, field, this.value(cell), result.message || "Invalid value");
        cell.setAttribute("aria-invalid", "true");
        cell.title = result.message || "Invalid value";
        row.classList.add("has-pending-cell");
      } else {
        this.pending.clear(tableId, rowId, field);
        cell.removeAttribute("aria-invalid");
        cell.removeAttribute("title");
        if (![...row.querySelectorAll("[aria-invalid=true]")].length) row.classList.remove("has-pending-cell");
      }
      return result;
    }

    promoteDraft(cell, eventCorrelation) {
      const table = this.tableFrom(cell), row = this.rowFrom(cell);
      if (!table || row?.dataset.rowKind !== "draft") return null;
      const tableId = table.dataset.editTable;
      const defaults = this.options.draftDefaults?.(tableId) || {};
      const draft = this.drafts.set(tableId, cell.dataset.field, this.value(cell), defaults);
      const meaningful = [...row.querySelectorAll("[data-table-cell]")].some(input =>
        input.dataset.meaningful !== "false" && meaningfulValue(input.type === "checkbox" ? input.checked : input.value)
      );
      if (!meaningful) return null;
      const result = this.options.promoteDraft?.({ tableId, table, row, cell, draft: { ...draft }, correlationId: eventCorrelation });
      if (!result || result.ok === false) return this.applyValidation(cell, result || { ok: false, message: "Unable to create row" });
      const rowId = result.rowId;
      row.dataset.rowKind = "persisted";
      row.dataset.rowId = rowId;
      row.classList.remove("trailing-row");
      row.querySelectorAll("[data-table-cell]").forEach(input => {
        input.dataset.rowId = rowId;
        input.dataset.path = result.paths?.[input.dataset.field] || input.dataset.path || "";
        delete input.dataset.draft;
      });
      const actionCell = row.querySelector("[data-draft-actions]");
      if (actionCell) actionCell.innerHTML = result.actionsHtml || "";
      this.drafts.reset(tableId, defaults);
      const html = this.options.renderDraft?.(tableId);
      if (html) row.insertAdjacentHTML("afterend", html);
      return result;
    }

    commit(cell, correlation) {
      const row = this.rowFrom(cell);
      if (row?.dataset.rowKind === "draft") return this.promoteDraft(cell, correlation);
      const result = this.options.commitCell?.({
        tableId: this.tableFrom(cell)?.dataset.editTable,
        rowId: row?.dataset.rowId,
        field: cell.dataset.field,
        path: cell.dataset.path,
        value: this.value(cell),
        cell,
        correlationId: correlation
      });
      return this.applyValidation(cell, result || { ok: true });
    }

    onInput(event) {
      const cell = this.cellFrom(event);
      if (!cell) return;
      if (this.rowFrom(cell)?.dataset.rowKind === "draft") this.promoteDraft(cell, correlationId("entry"));
    }

    onChange(event) {
      const cell = this.cellFrom(event);
      if (!cell) return;
      this.commit(cell, correlationId("edit"));
    }

    tableGeometry(table) {
      const rows = [...table.querySelectorAll("[data-table-row]")];
      return rows.map(row => [...row.querySelectorAll("[data-table-cell]")].map(cell => Number(cell.dataset.columnIndex)));
    }

    focusPosition(table, position) {
      if (!position) return;
      const rows = [...table.querySelectorAll("[data-table-row]")];
      const target = rows[position.rowIndex]?.querySelector(`[data-table-cell][data-column-index="${position.columnIndex}"]`);
      target?.focus();
      target?.select?.();
    }

    onKeyDown(event) {
      const cell = this.cellFrom(event);
      if (!cell || event.altKey || event.ctrlKey || event.metaKey) return;
      if (event.key === "Enter" && (cell.tagName === "TEXTAREA" || event.shiftKey)) return;
      if (event.key !== "Tab" && event.key !== "Enter") return;
      const table = this.tableFrom(cell), row = this.rowFrom(cell);
      if (!table || !row) return;
      const correlation = correlationId("key");
      this.commit(cell, correlation);
      const rows = [...table.querySelectorAll("[data-table-row]")];
      const rowIndex = rows.indexOf(row);
      const columnIndex = Number(cell.dataset.columnIndex);
      const geometry = this.tableGeometry(table);
      const direction = event.shiftKey ? -1 : 1;
      const next = nextEditablePosition(geometry, rowIndex, columnIndex, direction, event.key === "Enter");
      if (!next) return;
      event.preventDefault();
      this.focusPosition(table, next);
    }

    onPaste(event) {
      const cell = this.cellFrom(event);
      if (!cell) return;
      const text = event.clipboardData?.getData("text/plain");
      if (text === undefined || (!text.includes("\t") && !/[\r\n]/.test(text))) return;
      event.preventDefault();
      const table = this.tableFrom(cell), row = this.rowFrom(cell);
      const definition = this.options.definition?.(table.dataset.editTable);
      if (!definition) return;
      const matrix = parseClipboardMatrix(text);
      const correlation = correlationId("paste");
      const result = this.options.applyPaste?.({
        tableId: table.dataset.editTable,
        rowId: row.dataset.rowId,
        startColumn: Number(cell.dataset.columnIndex),
        matrix,
        mapped: mapClipboard(definition.columns, Number(cell.dataset.columnIndex), matrix),
        correlationId: correlation
      });
      if (result?.errors) result.errors.forEach(error => {
        const target = table.querySelector(`[data-table-row][data-row-id="${CSS.escape(error.rowId)}"] [data-table-cell][data-field="${CSS.escape(error.field)}"]`);
        if (target) this.applyValidation(target, { ok: false, message: error.message });
      });
    }
  }

  class AutocompleteController {
    constructor(input, options) {
      this.input = input;
      this.options = options;
      this.popup = options.popup;
      this.items = [];
      this.active = -1;
      this.sequence = 0;
      this.abortController = null;
      this.timer = null;
      input.setAttribute("role", "combobox");
      input.setAttribute("aria-autocomplete", "list");
      input.setAttribute("aria-expanded", "false");
      input.addEventListener("input", () => this.queue());
      input.addEventListener("keydown", event => this.keydown(event));
      input.addEventListener("focus", () => this.queue(0));
      input.addEventListener("blur", event => {
        if (!this.popup.contains(event.relatedTarget)) {
          this.normalizeExact();
          this.close();
        }
      });
      this.popup.addEventListener("pointerdown", event => {
        const item = event.target.closest("[data-autocomplete-index]");
        if (!item) return;
        event.preventDefault();
        this.choose(Number(item.dataset.autocompleteIndex));
      });
    }
    queue(delay = this.options.delay ?? 180) {
      clearTimeout(this.timer);
      this.timer = setTimeout(() => this.search(), delay);
    }
    async search() {
      const query = this.input.value;
      const sequence = ++this.sequence;
      this.abortController?.abort();
      this.abortController = new AbortController();
      try {
        const items = await this.options.search(query, this.abortController.signal);
        if (sequence !== this.sequence) return;
        this.items = items || [];
        this.active = this.items.length ? 0 : -1;
        this.options.render(this.popup, this.items, this.active, query);
        this.open();
      } catch (error) {
        if (error.name !== "AbortError" && sequence === this.sequence) this.options.error?.(error);
      }
    }
    open() { this.popup.hidden = false; this.input.setAttribute("aria-expanded", "true"); this.position(); }
    close() { this.popup.hidden = true; this.input.setAttribute("aria-expanded", "false"); this.active = -1; }
    position() {
      const rect = this.input.getBoundingClientRect();
      this.popup.style.left = `${Math.max(8, Math.min(rect.left, innerWidth - Math.max(rect.width, 360) - 8))}px`;
      this.popup.style.top = `${Math.min(rect.bottom + 3, innerHeight - 280)}px`;
      this.popup.style.width = `${Math.min(Math.max(rect.width, 360), innerWidth - 16)}px`;
    }
    keydown(event) {
      if (event.key === "Escape") { this.close(); return; }
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        if (!this.items.length) return;
        this.active = Math.max(0, Math.min(this.items.length - 1, this.active + (event.key === "ArrowDown" ? 1 : -1)));
        this.options.render(this.popup, this.items, this.active, this.input.value);
      }
      if (event.key === "Enter" && !this.popup.hidden && this.active >= 0) {
        event.preventDefault();
        this.choose(this.active);
      }
    }
    choose(index) {
      const item = this.items[index];
      if (!item) return;
      this.options.select(item, this.input);
      this.close();
    }
    normalizeExact() {
      if (!this.options.normalizeExact) return;
      const entered = String(this.input.value || "").trim().toLocaleLowerCase();
      if (!entered) return;
      const matches = this.items.filter(item => String(this.options.itemLabel?.(item) || "").trim().toLocaleLowerCase() === entered);
      if (matches.length === 1) this.options.select(matches[0], this.input);
    }
  }

  return {
    meaningfulValue,
    correlationId,
    parseClipboardMatrix,
    mapClipboard,
    nextEditablePosition,
    DraftStore,
    PendingCellStore,
    TableController,
    AutocompleteController
  };
});
