(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.MWUI = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const meaningfulValue = value => value !== null && value !== undefined && value !== false && String(value).trim() !== "";
  const DEFAULT_DECIMAL_PRECISION = Object.freeze({currency:2,currency_per_unit:2,percentage:2,quantity:2,dimension:2,square_footage:2,linear_footage:2,labor_hours:2,rate:2,multiplier:2,percentile:2});

  function normalizeDecimalPrecision(settings = {}) {
    const result = {...DEFAULT_DECIMAL_PRECISION};
    for (const key of Object.keys(result)) {
      const value = Number(settings?.[key]);
      if (Number.isInteger(value) && value >= 0 && value <= 6) result[key] = value;
    }
    return result;
  }

  function formatNumeric(value, category="quantity", settings={}, options={}) {
    if (value === null || value === undefined || value === "") return options.empty ?? "—";
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return String(value);
    const precision = normalizeDecimalPrecision(settings)[category] ?? DEFAULT_DECIMAL_PRECISION.quantity;
    return new Intl.NumberFormat(options.locale||"en-US",{
      ...(options.currency?{style:"currency",currency:options.currency}:{}),
      minimumFractionDigits:precision,
      maximumFractionDigits:precision,
      useGrouping:options.useGrouping!==false,
    }).format(numeric);
  }

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

  function parseDecimal(value, label) {
    const cleaned = String(value ?? "").replace(/[,\s]/g, "");
    if (!cleaned) return null;
    if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(cleaned) || !Number.isFinite(Number(cleaned))) {
      throw new Error(`Enter a valid ${label}.`);
    }
    return cleaned;
  }

  function parseDate(value) {
    const raw = String(value ?? "").trim();
    if (!raw) return "";
    let match = raw.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/), year, month, day;
    if (match) {
      [, year, month, day] = match;
    } else {
      match = raw.match(/^(\d{1,2})[\/-](\d{1,2})[\/-](\d{2}|\d{4})$/);
      if (!match) throw new Error("Enter a valid date as YYYY-MM-DD or M/D/YYYY.");
      month = match[1];
      day = match[2];
      year = match[3].length === 2 ? String(2000 + Number(match[3])) : match[3];
    }
    const iso = `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    const date = new Date(`${iso}T00:00:00Z`);
    if (Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== iso) throw new Error("Enter a valid calendar date.");
    return iso;
  }

  function parseColumnValue(column, value) {
    if (column?.type === "checkbox") {
      if (typeof value === "boolean") return { handled: true, value };
      const normalized = String(value ?? "").trim().toLowerCase();
      if (["true", "yes", "y", "1", "x", "checked"].includes(normalized)) return { handled: true, value: true };
      if (["false", "no", "n", "0", "", "unchecked"].includes(normalized)) return { handled: true, value: false };
      throw new Error("Enter TRUE or FALSE for a checkbox column.");
    }
    if (column?.type === "number") return { handled: true, value: parseDecimal(value, "number") };
    if (column?.type === "currency") return { handled: true, value: parseDecimal(String(value ?? "").replace(/[$]/g, ""), "currency amount") };
    if (column?.type === "date") return { handled: true, value: parseDate(value) };
    if (column?.type === "select") {
      const raw = String(value ?? "").trim();
      if (!raw) return { handled: true, value: "" };
      const match = (column.values || []).find(option => {
        const optionValue = Array.isArray(option) ? option[0] : option;
        const label = Array.isArray(option) ? option[1] : option;
        return String(optionValue).toLowerCase() === raw.toLowerCase() || String(label).toLowerCase() === raw.toLowerCase();
      });
      if (!match) throw new Error(`Select a valid ${String(column.label || "option").toLowerCase()}.`);
      return { handled: true, value: Array.isArray(match) ? match[0] : match };
    }
    return { handled: false, value };
  }

  function mapClipboard(columns, startColumn, matrix) {
    const mapped = [];
    const editableColumns = columns
      .map((column, columnIndex) => ({ column, columnIndex }))
      .filter(item => item.columnIndex >= startColumn && !item.column.readOnly && !item.column.calc && item.column.editable !== false);
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

  function arrowNavigationIntent(cell, key) {
    if (!cell || !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(key)) return null;
    if (key === "ArrowLeft" || key === "ArrowRight") {
      const supportsCaret = typeof cell.selectionStart === "number" && typeof cell.selectionEnd === "number";
      const fullValueSelected = supportsCaret && cell.selectionStart === 0 && cell.selectionEnd === String(cell.value ?? "").length;
      if (supportsCaret && !fullValueSelected) return null;
    }
    return {
      direction: key === "ArrowLeft" || key === "ArrowUp" ? -1 : 1,
      sameColumn: key === "ArrowUp" || key === "ArrowDown"
    };
  }

  function activeHistoryBand(position, bands) {
    if (position === null || position === undefined || position === "") return -1;
    const value = Number(position);
    if (!Number.isFinite(value) || !Array.isArray(bands) || bands.length === 0) return -1;
    const clamped = Math.max(0, Math.min(100, value));
    return bands.findIndex((band, index) => clamped >= Number(band.start) && (clamped < Number(band.end) || index === bands.length - 1));
  }

  function clampHistoryMarker(position, padding = 2) {
    const value = Number(position);
    if (!Number.isFinite(value)) return 50;
    const insetValue = Number(padding);
    const inset = Number.isFinite(insetValue) ? Math.max(0, Math.min(49, insetValue)) : 2;
    return Math.max(inset, Math.min(100 - inset, value));
  }

  function calculateTooltipPosition(anchorRect, tooltipSize, viewport, options = {}) {
    const margin = Math.max(0, Number(options.margin ?? 8));
    const gap = Math.max(0, Number(options.gap ?? 8));
    const viewportWidth = Math.max(0, Number(viewport?.width ?? 0));
    const viewportHeight = Math.max(0, Number(viewport?.height ?? 0));
    const tooltipWidth = Math.max(0, Number(tooltipSize?.width ?? 0));
    const tooltipHeight = Math.max(0, Number(tooltipSize?.height ?? 0));
    const anchorLeft = Number(anchorRect?.left ?? anchorRect?.x ?? 0);
    const anchorTop = Number(anchorRect?.top ?? anchorRect?.y ?? 0);
    const anchorRight = Number(anchorRect?.right ?? anchorLeft + Number(anchorRect?.width ?? 0));
    const anchorBottom = Number(anchorRect?.bottom ?? anchorTop + Number(anchorRect?.height ?? 0));
    const clamp = (value, minimum, maximum) => Math.min(Math.max(value, minimum), Math.max(minimum, maximum));

    const left = clamp(
      anchorLeft + (anchorRight - anchorLeft - tooltipWidth) / 2,
      margin,
      viewportWidth - tooltipWidth - margin
    );
    const aboveTop = anchorTop - tooltipHeight - gap;
    const belowTop = anchorBottom + gap;
    const aboveFits = aboveTop >= margin;
    const belowFits = belowTop + tooltipHeight <= viewportHeight - margin;
    const preferBelow = options.preferredPlacement === "below";
    let placement;
    if (preferBelow && belowFits) placement = "below";
    else if (!preferBelow && aboveFits) placement = "above";
    else if (belowFits) placement = "below";
    else if (aboveFits) placement = "above";
    else placement = anchorTop >= viewportHeight - anchorBottom ? "above" : "below";
    const desiredTop = placement === "above" ? aboveTop : belowTop;
    const top = clamp(desiredTop, margin, viewportHeight - tooltipHeight - margin);
    return { left, top, placement };
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
    clear() { this.values.clear(); }
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
    clearRow(tableId, rowId) {
      for (const [key, issue] of this.values) if (issue.tableId === tableId && issue.rowId === rowId) this.values.delete(key);
    }
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
        cell.setAttribute("data-tooltip", result.message || "Invalid value");
        row.classList.add("has-pending-cell");
      } else {
        this.pending.clear(tableId, rowId, field);
        cell.removeAttribute("aria-invalid");
        cell.removeAttribute("data-tooltip");
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
      const rowId = result.rowId, draftRowId = row.dataset.rowId;
      this.pending.clearRow(tableId, draftRowId);
      row.dataset.rowKind = "persisted";
      row.dataset.rowId = rowId;
      row.classList.remove("trailing-row");
      row.querySelectorAll("[data-table-cell]").forEach(input => {
        input.dataset.rowId = rowId;
        input.dataset.path = result.paths?.[input.dataset.field] || input.dataset.path || "";
        delete input.dataset.draft;
        input.removeAttribute("aria-invalid");
        input.removeAttribute("data-tooltip");
      });
      row.classList.remove("has-pending-cell");
      const actionCell = row.querySelector("[data-draft-actions]");
      if (actionCell) actionCell.innerHTML = result.actionsHtml || "";
      this.drafts.reset(tableId, defaults);
      const html = this.options.renderDraft?.(tableId);
      let newDraftRow = null;
      if (html) {
        row.insertAdjacentHTML("afterend", html);
        newDraftRow = row.nextElementSibling || null;
      }
      this.options.afterPromote?.({
        tableId,
        table,
        row,
        rowId,
        newDraftRow,
        cell,
        result,
        correlationId: eventCorrelation
      });
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
      if (!cell || event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return;
      if (event.key === "Enter" && (cell.tagName === "TEXTAREA" || event.shiftKey)) return;
      const arrow = arrowNavigationIntent(cell, event.key);
      if (event.key !== "Tab" && event.key !== "Enter" && !arrow) return;
      const table = this.tableFrom(cell), row = this.rowFrom(cell);
      if (!table || !row) return;
      const correlation = correlationId("key");
      this.commit(cell, correlation);
      const rows = [...table.querySelectorAll("[data-table-row]")];
      const rowIndex = rows.indexOf(row);
      const columnIndex = Number(cell.dataset.columnIndex);
      const geometry = this.tableGeometry(table);
      const direction = arrow?.direction ?? (event.shiftKey ? -1 : 1);
      const next = nextEditablePosition(geometry, rowIndex, columnIndex, direction, arrow?.sameColumn ?? event.key === "Enter");
      event.preventDefault();
      if (next) this.focusPosition(table, next);
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
      this.view = options.window || input.ownerDocument?.defaultView || globalThis;
      if (!this.popup.id) this.popup.id = correlationId("autocomplete");
      this.popup.setAttribute("role", "listbox");
      input.setAttribute("role", "combobox");
      input.setAttribute("aria-autocomplete", "list");
      input.setAttribute("aria-expanded", "false");
      input.setAttribute("aria-controls", this.popup.id);
      this.onInput = () => this.queue();
      this.onKeyDown = event => this.keydown(event);
      this.onFocus = () => this.queue(0);
      this.onBlur = event => {
        if (!this.popup.contains(event.relatedTarget)) {
          this.normalizeExact();
          this.close();
        }
      };
      this.onPointerDown = event => {
        const item = event.target.closest("[data-autocomplete-index]");
        if (!item) return;
        event.preventDefault();
        this.choose(Number(item.dataset.autocompleteIndex));
      };
      this.onViewportChange = () => { if (!this.popup.hidden) this.position(); };
      input.addEventListener("input", this.onInput);
      input.addEventListener("keydown", this.onKeyDown);
      input.addEventListener("focus", this.onFocus);
      input.addEventListener("blur", this.onBlur);
      this.popup.addEventListener("pointerdown", this.onPointerDown);
      this.view?.addEventListener?.("resize", this.onViewportChange);
      this.view?.addEventListener?.("scroll", this.onViewportChange, true);
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
        this.syncAccessibility();
        this.open();
      } catch (error) {
        if (error.name !== "AbortError" && sequence === this.sequence) this.options.error?.(error);
      }
    }
    syncAccessibility() {
      const options = [...this.popup.querySelectorAll("[data-autocomplete-index]")];
      options.forEach((option, index) => {if (!option.id) option.id = `${this.popup.id}-option-${index}`;option.setAttribute("role", "option");option.setAttribute("aria-selected", String(index === this.active))});
      const active = options.find(option => Number(option.dataset.autocompleteIndex) === this.active);
      if (active) {this.input.setAttribute("aria-activedescendant", active.id);active.scrollIntoView?.({ block: "nearest" });}else this.input.removeAttribute("aria-activedescendant");
    }
    open() { this.popup.hidden = false; this.input.setAttribute("aria-expanded", "true"); this.position(); }
    close() { this.popup.hidden = true; this.input.setAttribute("aria-expanded", "false"); this.input.removeAttribute("aria-activedescendant");this.active = -1; }
    position() {
      const rect = this.input.getBoundingClientRect(),viewportWidth=Number(this.view?.innerWidth||this.input.ownerDocument?.documentElement?.clientWidth||0),viewportHeight=Number(this.view?.innerHeight||this.input.ownerDocument?.documentElement?.clientHeight||0),margin=8,gap=3,width=Math.max(0,Math.min(Math.max(rect.width,360),viewportWidth-margin*2));
      this.popup.style.width = `${width}px`;this.popup.style.maxHeight=`${Math.max(120,viewportHeight-margin*2)}px`;
      const height=Math.min(this.popup.scrollHeight||280,Math.max(0,viewportHeight-margin*2)),below=viewportHeight-rect.bottom-gap,above=rect.top-gap,preferred=below>=Math.min(height,280)||below>=above?rect.bottom+gap:rect.top-gap-height,top=Math.max(margin,Math.min(preferred,viewportHeight-height-margin));
      this.popup.style.left = `${Math.max(margin,Math.min(rect.left,viewportWidth-width-margin))}px`;
      this.popup.style.top = `${top}px`;
    }
    keydown(event) {
      if (event.key === "Escape") { this.close(); return; }
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        if (!this.items.length) return;
        this.active = Math.max(0, Math.min(this.items.length - 1, this.active + (event.key === "ArrowDown" ? 1 : -1)));
        this.options.render(this.popup, this.items, this.active, this.input.value);
        this.syncAccessibility();
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
    destroy() {
      clearTimeout(this.timer);
      this.sequence += 1;
      this.abortController?.abort();
      this.close();
      this.input.removeEventListener("input", this.onInput);
      this.input.removeEventListener("keydown", this.onKeyDown);
      this.input.removeEventListener("focus", this.onFocus);
      this.input.removeEventListener("blur", this.onBlur);
      this.popup.removeEventListener("pointerdown", this.onPointerDown);
      this.view?.removeEventListener?.("resize", this.onViewportChange);
      this.view?.removeEventListener?.("scroll", this.onViewportChange, true);
    }
  }

  class TooltipController {
    constructor(rootElement, options = {}) {
      if (!rootElement?.addEventListener) throw new TypeError("TooltipController requires an event root");
      this.root = rootElement;
      this.options = options;
      this.document = options.document || rootElement.ownerDocument || globalThis.document;
      this.view = options.window || this.document?.defaultView || globalThis;
      this.selector = options.selector || "[data-tooltip]";
      this.delay = Math.max(0, Number(options.delay ?? 350));
      this.pointerTarget = null;
      this.focusTarget = null;
      this.pendingTarget = null;
      this.activeTarget = null;
      this.priorDescribedBy = null;
      this.timer = null;
      this.ownsTooltip = !options.tooltipElement;
      this.tooltip = options.tooltipElement || this.createTooltip();
      this.onPointerOver = this.onPointerOver.bind(this);
      this.onPointerOut = this.onPointerOut.bind(this);
      this.onFocusIn = this.onFocusIn.bind(this);
      this.onFocusOut = this.onFocusOut.bind(this);
      this.onKeyDown = this.onKeyDown.bind(this);
      this.onViewportChange = this.onViewportChange.bind(this);
      rootElement.addEventListener("pointerover", this.onPointerOver);
      rootElement.addEventListener("pointerout", this.onPointerOut);
      rootElement.addEventListener("focusin", this.onFocusIn);
      rootElement.addEventListener("focusout", this.onFocusOut);
      this.document?.addEventListener?.("keydown", this.onKeyDown, true);
      this.view?.addEventListener?.("resize", this.onViewportChange);
      this.view?.addEventListener?.("scroll", this.onViewportChange, true);

      const Observer = options.MutationObserver || this.view?.MutationObserver || globalThis.MutationObserver;
      if (Observer) {
        this.observer = new Observer(mutations => {
          for (const mutation of mutations || []) {
            if (mutation.type !== "attributes" || mutation.attributeName !== "data-tooltip") continue;
            const target = mutation.target,content = this.contentFor(target),focused = target === this.document?.activeElement || target.contains?.(this.document?.activeElement);
            if (focused && content) this.focusTarget = target;
            if (!content) {
              if (this.focusTarget === target) this.focusTarget = null;
              if (this.pointerTarget === target) this.pointerTarget = null;
              if (this.activeTarget === target) this.hide();
            } else if (this.activeTarget === target) {
              this.tooltip.textContent = content;
              this.position();
            }
          }
          if (this.pointerTarget && !this.connected(this.pointerTarget)) this.pointerTarget = null;
          if (this.focusTarget && !this.connected(this.focusTarget)) this.focusTarget = null;
          if (this.activeTarget && !this.connected(this.activeTarget)) this.hide();
          this.syncIntent();
        });
        try { this.observer.observe(rootElement, { childList: true, attributes: true, attributeFilter: ["data-tooltip"], subtree: true }); }
        catch { this.observer = null; }
      }
    }

    createTooltip() {
      if (!this.document?.createElement) throw new TypeError("TooltipController requires a document");
      const tooltip = this.document.createElement("div");
      tooltip.id = correlationId("tooltip");
      tooltip.className = "mw-tooltip";
      tooltip.setAttribute("role", "tooltip");
      tooltip.hidden = true;
      tooltip.style.position = "fixed";
      tooltip.style.pointerEvents = "none";
      const parent = this.options.portal || this.document.body || this.document.documentElement;
      parent.appendChild(tooltip);
      return tooltip;
    }

    contains(target) { return Boolean(target && (target === this.root || this.root.contains?.(target))); }
    connected(target) {
      if (!target) return false;
      return "isConnected" in target ? Boolean(target.isConnected) : this.contains(target);
    }
    triggerFrom(target) {
      const trigger = target?.closest?.(this.selector);
      return this.contains(trigger) ? trigger : null;
    }
    contentFor(target) {
      const value = this.options.content?.(target) ?? target?.getAttribute?.("data-tooltip");
      return String(value ?? "").trim();
    }
    intentTarget() {
      if (this.connected(this.focusTarget)) return this.focusTarget;
      if (this.connected(this.pointerTarget)) return this.pointerTarget;
      return null;
    }

    onPointerOver(event) {
      const trigger = this.triggerFrom(event.target);
      if (!trigger || trigger.contains?.(event.relatedTarget)) return;
      this.pointerTarget = trigger;
      this.syncIntent();
    }
    onPointerOut(event) {
      const trigger = this.triggerFrom(event.target);
      if (!trigger || trigger !== this.pointerTarget || trigger.contains?.(event.relatedTarget)) return;
      this.pointerTarget = null;
      this.syncIntent();
    }
    onFocusIn(event) {
      const trigger = this.triggerFrom(event.target);
      if (!trigger) return;
      this.focusTarget = trigger;
      this.syncIntent();
    }
    onFocusOut(event) {
      const trigger = this.triggerFrom(event.target);
      if (!trigger || trigger !== this.focusTarget || trigger.contains?.(event.relatedTarget)) return;
      this.focusTarget = null;
      this.syncIntent();
    }
    onKeyDown(event) {
      if (event.key !== "Escape" || (!this.activeTarget && !this.pendingTarget)) return;
      event.preventDefault();
      this.close();
    }
    onViewportChange() {
      if (this.activeTarget && this.connected(this.activeTarget)) this.position();
      else if (this.activeTarget) this.close();
    }

    syncIntent() {
      const target = this.intentTarget();
      if (!target || !this.contentFor(target)) { this.hide(); return; }
      if (target === this.activeTarget && !this.tooltip.hidden) return;
      if (target === this.pendingTarget) return;
      this.hide();
      this.pendingTarget = target;
      this.timer = setTimeout(() => {
        this.timer = null;
        const intended = this.intentTarget();
        this.pendingTarget = null;
        if (intended === target && this.connected(target)) this.open(target);
      }, this.delay);
    }

    describe(target) {
      this.priorDescribedBy = target.getAttribute?.("aria-describedby");
      const ids = new Set(String(this.priorDescribedBy || "").split(/\s+/).filter(Boolean));
      ids.add(this.tooltip.id);
      target.setAttribute?.("aria-describedby", [...ids].join(" "));
    }
    restoreDescription() {
      if (!this.activeTarget) return;
      if (this.priorDescribedBy === null) this.activeTarget.removeAttribute?.("aria-describedby");
      else this.activeTarget.setAttribute?.("aria-describedby", this.priorDescribedBy);
      this.priorDescribedBy = null;
    }
    open(target) {
      const content = this.contentFor(target);
      if (!content || !this.connected(target)) return;
      if (this.activeTarget === target) {
        this.tooltip.textContent = content;
        this.tooltip.hidden = false;
        this.position();
        return;
      }
      if (this.activeTarget && this.activeTarget !== target) this.hide();
      this.activeTarget = target;
      this.tooltip.textContent = content;
      this.tooltip.hidden = false;
      this.describe(target);
      this.position();
      this.options.onOpen?.(target, this.tooltip);
    }
    position() {
      if (!this.activeTarget || this.tooltip.hidden) return;
      const anchorRect = this.activeTarget.getBoundingClientRect();
      const tooltipRect = this.tooltip.getBoundingClientRect();
      const viewport = {
        width: Number(this.view?.innerWidth || this.document?.documentElement?.clientWidth || 0),
        height: Number(this.view?.innerHeight || this.document?.documentElement?.clientHeight || 0)
      };
      const position = calculateTooltipPosition(anchorRect, tooltipRect, viewport, this.options);
      this.tooltip.style.left = `${Math.round(position.left)}px`;
      this.tooltip.style.top = `${Math.round(position.top)}px`;
      this.tooltip.dataset.placement = position.placement;
    }
    hide() {
      clearTimeout(this.timer);
      this.timer = null;
      this.pendingTarget = null;
      const priorTarget = this.activeTarget;
      this.restoreDescription();
      this.activeTarget = null;
      this.tooltip.hidden = true;
      this.tooltip.removeAttribute?.("data-placement");
      if (priorTarget) this.options.onClose?.(priorTarget, this.tooltip);
    }
    close() {
      this.pointerTarget = null;
      this.focusTarget = null;
      this.hide();
    }
    destroy() {
      this.close();
      this.root.removeEventListener("pointerover", this.onPointerOver);
      this.root.removeEventListener("pointerout", this.onPointerOut);
      this.root.removeEventListener("focusin", this.onFocusIn);
      this.root.removeEventListener("focusout", this.onFocusOut);
      this.document?.removeEventListener?.("keydown", this.onKeyDown, true);
      this.view?.removeEventListener?.("resize", this.onViewportChange);
      this.view?.removeEventListener?.("scroll", this.onViewportChange, true);
      this.observer?.disconnect?.();
      if (this.ownsTooltip) this.tooltip.remove?.();
    }
  }

  class DrawerController {
    constructor(rootElement, options = {}) {
      if (!rootElement?.appendChild) throw new TypeError("DrawerController requires a portal root");
      this.root = rootElement;
      this.options = options;
      this.document = options.document || rootElement.ownerDocument || globalThis.document;
      this.ownsLayer = !options.layerElement;
      this.layer = options.layerElement || this.createLayer();
      this.panel = options.panelElement || this.layer.querySelector?.("[data-drawer-panel]");
      this.content = options.contentElement || this.layer.querySelector?.("[data-drawer-content]");
      if (!this.panel || !this.content) throw new TypeError("DrawerController requires panel and content elements");
      if (!this.panel.id) this.panel.id = correlationId("drawer");
      this.panel.setAttribute("role", "dialog");
      this.panel.setAttribute("aria-modal", "true");
      this.opener = null;
      this.openerState = null;
      this.backgroundState = [];
      this.onClick = this.onClick.bind(this);
      this.onKeyDown = this.onKeyDown.bind(this);
      this.onFocusIn = this.onFocusIn.bind(this);
      this.layer.addEventListener("click", this.onClick);
      this.document?.addEventListener?.("keydown", this.onKeyDown, true);
      this.document?.addEventListener?.("focusin", this.onFocusIn, true);
      this.layer.hidden = true;
      this.layer.setAttribute?.("aria-hidden", "true");
      this.panel.setAttribute("aria-hidden", "true");
    }

    createLayer() {
      if (!this.document?.createElement) throw new TypeError("DrawerController requires a document");
      const layer = this.document.createElement("div");
      layer.className = "mw-drawer-layer";
      layer.setAttribute("data-drawer-layer", "");
      const backdrop = this.document.createElement("div");
      backdrop.className = "mw-drawer-backdrop";
      backdrop.setAttribute("data-drawer-backdrop", "");
      backdrop.setAttribute("aria-hidden", "true");
      const panel = this.document.createElement("aside");
      panel.className = "mw-drawer";
      panel.setAttribute("data-drawer-panel", "");
      panel.setAttribute("role", "dialog");
      panel.setAttribute("aria-modal", "true");
      panel.tabIndex = -1;
      const close = this.document.createElement("button");
      close.type = "button";
      close.className = "mw-drawer-close";
      close.setAttribute("data-drawer-close", "");
      close.setAttribute("aria-label", "Close detail panel");
      close.textContent = "×";
      const content = this.document.createElement("div");
      content.className = "mw-drawer-content";
      content.setAttribute("data-drawer-content", "");
      panel.appendChild(close);
      panel.appendChild(content);
      layer.appendChild(backdrop);
      layer.appendChild(panel);
      (this.options.portal || this.root).appendChild(layer);
      return layer;
    }

    get isOpen() { return !this.layer.hidden; }
    onClick(event) {
      if (event.target.closest?.("[data-drawer-close], [data-drawer-backdrop]")) this.close();
    }
    onKeyDown(event) {
      if (!this.isOpen) return;
      if (event.key === "Escape") {
        event.preventDefault();
        this.close();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = this.focusableElements();
      if (!focusable.length) {
        event.preventDefault();
        this.panel.focus?.({ preventScroll: true });
        return;
      }
      const active = this.document?.activeElement;
      const index = focusable.indexOf(active);
      if (index < 0) {
        event.preventDefault();
        focusable[event.shiftKey ? focusable.length - 1 : 0].focus?.({ preventScroll: true });
      } else if (event.shiftKey && index === 0) {
        event.preventDefault();
        focusable[focusable.length - 1].focus?.({ preventScroll: true });
      } else if (!event.shiftKey && index === focusable.length - 1) {
        event.preventDefault();
        focusable[0].focus?.({ preventScroll: true });
      }
    }
    onFocusIn(event) {
      if (!this.isOpen || this.panel.contains?.(event.target)) return;
      const target = this.focusableElements()[0] || this.panel;
      target.focus?.({ preventScroll: true });
    }
    focusableElements() {
      const candidates = [];
      const visit = element => {
        for (const child of Array.from(element.children || [])) {
          const tag = String(child.tagName || "").toUpperCase();
          const hasTabIndex = child.getAttribute?.("tabindex") !== null;
          const contenteditable = child.getAttribute?.("contenteditable");
          const naturallyFocusable = ["BUTTON", "INPUT", "SELECT", "TEXTAREA"].includes(tag)
            || (tag === "A" && child.getAttribute?.("href") !== null);
          if (naturallyFocusable || hasTabIndex || (contenteditable !== null && contenteditable !== "false")) {
            candidates.push(child);
          }
          visit(child);
        }
      };
      visit(this.panel);
      return candidates.filter(element => {
        const tabindex = element.getAttribute?.("tabindex");
        const contenteditable = element.getAttribute?.("contenteditable");
        let concealed = false;
        for (let ancestor = element; ancestor && ancestor !== this.panel; ancestor = ancestor.parentElement) {
          if (ancestor.hidden || ancestor.inert || ancestor.hasAttribute?.("inert") || ancestor.getAttribute?.("aria-hidden") === "true") {
            concealed = true;
            break;
          }
        }
        return !concealed
          && !element.disabled
          && !element.hasAttribute?.("disabled")
          && element.getAttribute?.("aria-hidden") !== "true"
          && (tabindex === null || !Number.isFinite(Number(tabindex)) || Number(tabindex) >= 0)
          && contenteditable !== "false";
      });
    }
    isolateBackground() {
      if (this.backgroundState.length) return;
      let branch = this.layer;
      while (branch?.parentElement) {
        const parent = branch.parentElement;
        for (const sibling of Array.from(parent.children || [])) {
          if (sibling === branch) continue;
          this.backgroundState.push({
            element: sibling,
            ariaHidden: sibling.getAttribute?.("aria-hidden"),
            hadInertAttribute: sibling.hasAttribute?.("inert") || false,
            inertAttribute: sibling.getAttribute?.("inert"),
            inertProperty: "inert" in sibling ? sibling.inert : undefined
          });
          sibling.setAttribute?.("aria-hidden", "true");
          sibling.setAttribute?.("inert", "");
          if ("inert" in sibling) sibling.inert = true;
        }
        if (parent === this.document?.body) break;
        branch = parent;
      }
    }
    restoreBackground() {
      for (const state of this.backgroundState) {
        const { element } = state;
        if (state.ariaHidden === null || state.ariaHidden === undefined) element.removeAttribute?.("aria-hidden");
        else element.setAttribute?.("aria-hidden", state.ariaHidden);
        if (state.hadInertAttribute) element.setAttribute?.("inert", state.inertAttribute ?? "");
        else element.removeAttribute?.("inert");
        if (state.inertProperty !== undefined) element.inert = state.inertProperty;
      }
      this.backgroundState = [];
    }
    render(content) {
      this.content.replaceChildren?.();
      if (content === null || content === undefined) return this.content;
      let rendered = content;
      if (typeof content === "function") rendered = content(this.content);
      if (rendered === undefined || rendered === this.content) return this.content;
      if (typeof rendered === "string") this.content.innerHTML = rendered;
      else if (rendered?.nodeType) this.content.appendChild(rendered);
      else if (rendered?.[Symbol.iterator]) {
        for (const node of rendered) if (node?.nodeType) this.content.appendChild(node);
      } else this.content.textContent = String(rendered);
      return this.content;
    }
    open(content, options = {}) {
      if (content !== undefined) this.render(content);
      const alreadyOpen = this.isOpen;
      const candidate = options.opener || (alreadyOpen ? this.opener : this.document?.activeElement);
      if (alreadyOpen && options.opener && options.opener !== this.opener) this.restoreOpenerState(false);
      if (!alreadyOpen || candidate !== this.opener) this.opener = candidate?.focus ? candidate : null;
      if (this.opener && (!alreadyOpen || !this.openerState)) {
        this.openerState = {
          expanded: this.opener.getAttribute?.("aria-expanded"),
          controls: this.opener.getAttribute?.("aria-controls")
        };
        this.opener.setAttribute?.("aria-expanded", "true");
        this.opener.setAttribute?.("aria-controls", this.panel.id);
      }
      if (options.label) this.panel.setAttribute("aria-label", options.label);
      else this.panel.removeAttribute("aria-label");
      if (options.labelledBy) this.panel.setAttribute("aria-labelledby", options.labelledBy);
      else this.panel.removeAttribute("aria-labelledby");
      this.layer.hidden = false;
      this.layer.setAttribute?.("aria-hidden", "false");
      this.panel.setAttribute("aria-hidden", "false");
      if (options.focus !== false || !this.panel.contains?.(this.document?.activeElement)) {
        this.panel.focus?.({ preventScroll: true });
      }
      if (!alreadyOpen) this.isolateBackground();
      this.options.onOpen?.(this);
      return this;
    }
    restoreOpenerState(returnFocus) {
      const opener = this.opener;
      if (opener) {
        const restore = (name, value) => value === null || value === undefined
          ? opener.removeAttribute?.(name)
          : opener.setAttribute?.(name, value);
        restore("aria-expanded", this.openerState?.expanded);
        restore("aria-controls", this.openerState?.controls);
        if (returnFocus && ("isConnected" in opener ? opener.isConnected : true)) opener.focus?.({ preventScroll: true });
      }
      this.opener = null;
      this.openerState = null;
    }
    close(options = {}) {
      if (!this.isOpen) return this;
      this.layer.hidden = true;
      this.layer.setAttribute?.("aria-hidden", "true");
      this.panel.setAttribute("aria-hidden", "true");
      this.restoreBackground();
      this.restoreOpenerState(options.restoreFocus !== false);
      this.options.onClose?.(this, options.reason || "dismissed");
      return this;
    }
    destroy() {
      this.close({ restoreFocus: false, reason: "destroyed" });
      this.layer.removeEventListener("click", this.onClick);
      this.document?.removeEventListener?.("keydown", this.onKeyDown, true);
      this.document?.removeEventListener?.("focusin", this.onFocusIn, true);
      if (this.ownsLayer) this.layer.remove?.();
    }
  }

  return {
    meaningfulValue,
    DEFAULT_DECIMAL_PRECISION,
    normalizeDecimalPrecision,
    formatNumeric,
    correlationId,
    parseClipboardMatrix,
    parseColumnValue,
    mapClipboard,
    nextEditablePosition,
    arrowNavigationIntent,
    activeHistoryBand,
    clampHistoryMarker,
    calculateTooltipPosition,
    DraftStore,
    PendingCellStore,
    TableController,
    AutocompleteController,
    TooltipController,
    DrawerController
  };
});
