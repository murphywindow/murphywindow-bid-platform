from pathlib import Path


def test_all_inf4320_lifecycle_surfaces_are_present():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    for label in (
        "Project Information", "Scope and Cost Codes", "Quotes", "Frame Takeoff",
        "Doors and Hardware", "Equipment", "Borrowed Lites", "Labor and Travel",
        "Rates", "Bid", "Alternates", "Proposal", "Review and Submission",
        "Award and Contract Allocation", "Change Orders", "Schedule of Values",
        "Closeout", "Audit History", "Administration",
    ):
        assert label in source
    assert "Copy job data" in Path("app/static/index.html").read_text(encoding="utf-8")


def test_responsive_and_editable_calculated_visual_contract():
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    for token in (
        "--ui-brand: #244f41", "--table-editable-bg: #ffffff",
        "--table-calculated-bg: #f3f7f5", "--focus-ring: 0 0 0 2px",
        "--motion-fast: 90ms", "--z-tooltip", "--z-drawer",
    ):
        assert token in css
    assert "@media (max-width: 47.5rem)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert ":focus-visible" in css
    assert ".calculated" in css and ".field input" in css


def test_bid_version_is_visible_in_header_pages_totals_and_proposal():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    assert source.count("bid_version?.display") >= 5
    assert "file r${state.doc.project.revision}" in source


def test_scope_cost_code_autocomplete_uses_owner_reference_and_keeps_description_editable():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    core = Path("app/static/ui-core.js").read_text(encoding="utf-8")
    assert "data-scope-code-cell" in source
    assert 'id:"cost-codes"' in source
    assert 'controlled:"reference"' in source
    assert "matchingScopeReferences" in source
    assert "selectScopeTableReference" in source
    assert "function controlledScopeCode" in source
    assert "controlledScopeCode(row.code,reference)" in source
    assert "selectedCode=controlledScopeCode(input.value,reference)" in source
    assert "Add Custom Code" in source
    assert 'row.custom||row.is_custom||row.custom_code||row.custom_status==="authorized_custom"' in source
    assert "<th>Cost Code</th><th>Description</th>" in source
    assert "AutocompleteController" in core


def test_autosave_reconciles_outputs_without_rebuilding_the_active_page():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    save = source[source.index("async function save"):source.index("function input")]
    assert "reconcileCalculatedView()" in save
    assert "render()" not in save
    assert "data-frame-line-value" in source
    assert "data-output-path" in source
    reconciliation = source[source.index("function reconcileCalculatedView"):source.index("function rowInput")]
    assert '[data-table-cell][data-path]:not([data-draft])' in reconciliation
    assert "document.activeElement" in reconciliation
    assert 'getAttribute("aria-invalid")' in reconciliation
    for path in ("quotes.${i}.calculated_cost", "borrowed_lites.${i}.calculated_square_feet", "labor_estimates.${i}.calculated_cost", "labor_estimates.${i}.calendar_weeks"):
        assert path in source


def test_configuration_autosaves_and_confirms_exact_commercial_impacts_before_recalculation():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    assert "function previewCommercialImpact" in source
    assert "/commercial-impact" in source
    assert "function confirmCommercialImpacts" in source
    assert "Accept changes and recalculate" in source
    assert "function changePricingConfiguration" in source
    assert "await save();if(state.saveError)" in source
    assert "refreshPricingConfigurationSummary()" in source
    assert "function scheduleAdminConfigurationAutosave" in source
    assert "function saveAdminConfiguration" in source
    assert "confirmed_commercial_impact" in source
    assert "Save new draft version" not in source
    assert 'if(el.closest(".bid-controls"))return' in source


def test_frame_takeoff_uses_compact_modules_and_explicit_entry_row():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    core = Path("app/static/ui-core.js").read_text(encoding="utf-8")
    assert 'FRAME_TAKEOFF_PRESENTATION = "production-compact"' in source
    assert "frame-module" in source and "module-identity" in source
    assert "frame-code-description" in source
    assert 'rows.map(r=>`<option value="${esc(r.code)}"' in source
    for label in ("ft²", "Install materials", "Sell $/ft²", "Frame totals"):
        assert label in source
    assert "Rows</small>" not in source
    assert "draftRowHtml" in source and "DraftStore" in core
    assert "ensureFrameTrailingRows" not in source
    assert "Trailing frame entry row maintained" not in source
    assert "trailing-row" in source
    assert "activeDraftTables" in source and "data-table-add-row" in source


def test_frame_cost_code_picker_can_add_scope_without_leaving_frame_takeoff():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    assert 'FRAME_ADD_COST_CODE="__frame_add_cost_code__"' in source
    assert "＋ Add Cost Code…" in source
    assert "function addFrameCostCodeUI" in source
    assert "matchingScopeReferences(search.value,20)" in source
    assert "Cost Code added from Frame Takeoff controlled-reference search" in source
    assert "data-frame-code" in source and "data-alt-section-field" in source
    assert ".frame-cost-code-results" in css and ".frame-cost-code-choice" in css


def test_workspace_pages_have_project_urls_and_browser_history_support():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    assert "function projectPageUrl" in source
    assert "function navigatePage" in source
    assert 'window.addEventListener("popstate"' in source
    assert "history.pushState" in source and "history.replaceState" in source
    assert 'href="${state.doc?projectPageUrl' in source


def test_frontend_assets_use_a_cache_busting_version():
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    assert "/assets/styles.css?v=" in html
    assert "/assets/basic.css" not in html
    assert "/assets/ui-core.js?v=" in html
    assert "/assets/app.js?v=" in html


def test_central_production_stylesheet_is_active():
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    assert 'href="/assets/styles.css' in html
    assert "Central production presentation foundation" in css
    for selector in (".topbar", ".sidebar", ".page-head", ".work-panel", ".data-grid"):
        assert selector in css


def test_estimating_tables_scroll_instead_of_clipping_critical_columns():
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    assert ".table-wrap" in css and "overflow-x: auto" in css
    assert ".frame-table" in css and ".frame-material-list" in css
    assert "position: sticky" in css
    assert ".bid-description" in css and "white-space: normal" in css
    assert ".money" in css and "white-space: nowrap" in css


def test_frame_grid_follows_workbook_column_order_and_marks_calculated_cells():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    labels = ["Mark / Type", "Qty", "Width", "Height", "ft²", "Perim.", "Caulk passes", "Caulk LF", "Head / Sill", "Head", "Sill", "Jamb", "Type", "Material", "Finish", "Notes", "Install mats"]
    frame = source[source.index("function frameTable"):source.index("function materialTable")]
    positions = [frame.index(f'label:"{label}"') for label in labels]
    assert positions == sorted(positions)
    assert frame.count('class:"calculated numeric"') >= 4
    assert frame.count("tooltip:") >= 7
    assert 'label:"Qty issue"' not in frame
    assert "quantity-issue-row" in frame and "frameQuantityIssueAction" in frame
    for field in ("mark", "head", "sill", "jamb", "type", "material", "finish", "notes"):
        assert f'key:"{field}"' in frame and f'key:"{field}",label:' in frame
    assert frame.count('type:"textarea"') >= 8


def test_frame_workspace_uses_shared_dense_production_primitives():
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    for selector in (".frame-module", ".module-header", ".section-metrics", ".material-config"):
        assert selector in css
    assert "work-module frame-module" in source
    assert "section-metrics" in source
    assert "material-config" in source
    assert "frameTotalsRail" in source and 'class="frame-totals-rail"' in source
    assert "frame-header-commercial" in source
    assert "frame-identity-picker" in source and "module-code-control" not in source[source.index("function renderFrames"):source.index("function frameTable")]


def test_frame_history_uses_delayed_vertical_preview_with_expanded_scale():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    assert "function verticalHistoryIndicator" in source
    assert 'data-history-vertical="true"' in source
    assert ".history-vertical-track" in css and ".history-expanded-scale" in css
    assert "transition-delay: 650ms" in css
    assert "40px high, five equal 8px ranges" in css
    assert "width: 3rem" in css and '.history-vertical-track .current::before' in css
    for label in ("Very Aggressive", "Aggressive", "Normal", "Conservative", "Very Conservative"):
        assert label in source
    assert "normalizedHistoryView" in source and "MWUI.activeHistoryBand" in source
    assert "visualBands=view.bands.map((band,index)=>({band,index})).reverse()" in source
    assert "top: calc(100% - var(--history-position, 50%));" in css
    assert "top: clamp(4px, calc(100% - var(--history-position, 50%)), calc(100% - 4px));" in css
    assert "history-popover-values" in source and "category_definition" in source
    assert 'data-frame-section-id' in source and 'drawerController.panel.dataset.costCode' in source


def test_installation_materials_expose_existing_inputs_results_and_lineage():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    assert 'class="frame-material-list table-wrap"' in source
    assert "<th scope=\"col\">Material</th><th scope=\"col\">Basis qty</th>" in source
    assert "material_overrides.${r.id}.factor_override" in source
    assert "material_overrides.${esc(r.id)}.rate_override" in source
    assert "override.factor_override??override.factor" in source
    assert "override.rate_override??override.rate" in source
    assert 'legacyPath=path.replace(/_override$/,""' in source
    assert 'statusBadge("Controlled","controlled")' in source
    assert 'Project-specific' in source
    assert 'data-tooltip="${esc(basis)}"' in source
    material_table = source[source.index("function materialTable"):source.index("function doorMeaningful")]
    assert "Tie Back qty" not in material_table
    assert "Backpan / insulation</span>" not in material_table


def test_installation_material_formula_builder_supports_base_alternates_and_revert():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    services = Path("app/services.py").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    runtime = source[source.index("const MATERIAL_FORMULA_SOURCES") : source.index("function alternateSectionCodePicker")]
    for contract in (
        '["square_feet","ft²"]', '["multiply","×"]', '["divide","÷"]',
        '["add","+"]', '["subtract","−"]', "data-material-formula-group",
        "data-revert-material-formula", "data-alt-revert-material-formula",
        "function revertBaseMaterialFormula", "function revertAlternateMaterialFormula",
        "function previewMaterialFormulaEditor", "function materialFormulaSourceValues",
        "function calculateMaterialFormulaTotal", "data-material-source-values", "data-material-rate",
        'class="material-formula-total"><small>Total</small>', "data-material-rate-input",
    ):
        assert contract in runtime
    assert "source_override" in services and "operator_override" in services and "operand_override" in services
    assert '"calculated_quantity"' in services and '"invalid_installation_material_formula"' in services
    assert ".scenario-frame-workspace .material-formula-editor" in css
    assert ".scenario-frame-workspace .formula-material-grid" in css
    assert 'control.addEventListener("input"' in source
    assert 'control.dispatchEvent(new Event("change",{bubbles:true}))' in source
    for heading in ("Installation<br>material", "Quantity<br>formula", "Unit<br>rate", "Extended<br>cost"):
        assert heading in runtime
    for contract in ("max-width: 780px", "width: 23%", "width: 50%", "width: 12%", "width: 11%", "width: 4%"):
        assert contract in css
    assert 'rerender:!input.closest(".formula-material-grid")' in source


def test_controlled_status_pills_are_globally_suppressed_without_changing_controls():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    assert 'function statusBadge(label,status="neutral",title=""){if(status==="controlled")return ""' in source
    assert 'data-controlled="true"' in source


def test_custom_material_and_bid_hierarchy_use_compact_canonical_contracts():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    for contract in ("sectionMaterialRules", "data-add-section-material", "data-remove-section-material", "manual_quantity", "controlled_rate_id"):
        assert contract in source
    for label in ("Base Product", "LAF", "LAS", "Installation Materials"):
        assert label in source or label in Path("app/services.py").read_text(encoding="utf-8")
    assert "bid-component-disclosure" in source and "bid-source-grid" in source
    assert ".installation-material-grid" in css and ".bid-breakdown th:nth-child(8)" in css
    assert "font-variant-numeric: tabular-nums" in css


def test_bid_worksheet_exposes_collapsible_components_and_alt_navigation_without_bottom_detail():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    worksheet = source[source.index("function renderBidWorksheet"):source.index("function renderProposalLegacy")]
    for heading in ("Direct Cost", "Markup %", "Markup $", "Selling Value", "Total ft²", "$/ft²", "History"):
        assert heading in worksheet
    assert "bidWorksheetComponentRows" in source
    assert "bidWorksheetSourceRows" in source
    assert "bid-subtotal-row" not in worksheet and "bid-grand-total" in source
    assert "effective_estimate" in worksheet
    assert "alternateTabs()+bidAlternateContext" in worksheet
    assert 'if(page==="bid"||page==="frames")return RENDER[page]();' in source
    assert 'alternateCommercialPanel("Alternate detail")' not in source
    assert "insertAlternateTabsAfterHeader(RENDER[page]())" in source
    assert "rerenderPreservingControl(\"data-alt-tab\",target)" in source
    for selector in (".bid-worksheet", ".bid-component-row", ".bid-grand-total", ".history-compact"):
        assert selector in css


def test_bid_tabulation_uses_only_the_shared_ui_draft_row():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    proposal = source[source.index("function renderProposal"):source.index("function renderReview")]
    assert 'tableEditor("bid_tabulations"' in proposal
    assert 'addButton("bid_tabulations"' not in proposal


def test_proposal_workspace_is_editable_compact_and_uses_safe_changed_only_rendering():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    proposal = source[source.rindex("function renderProposal()") : source.index("const RENDER=")]
    for path in ("project.proposal_scope", "project.proposal_inclusions", "project.proposal_exclusions", "project.additional_information"):
        assert f'input("{path}"' in proposal
    assert 'data-output-path="working_estimate.totals.selling_value"' in source
    assert 'data-output-path="working_estimate.totals.margin_percentage"' in source
    assert "proposal-preview.pdf" in proposal
    assert "compareLeft" not in proposal and "compareRight" not in proposal
    assert "data-compare-from" in proposal and "proposal-history-panel" in proposal
    assert "proposalDiffValue" in source and 'typeof value==="object"' in source
    assert "[object Object]" not in source
    assert "startHistoricalBranch" in source and "/branch" in source


def test_frame_dimensions_accept_natural_units_and_rows_can_be_duplicated():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    assert "function normalizeFrameDimension" in source
    assert "4f 6in" in source and "inputmode=\"decimal\"" in source
    frame = source[source.index("function frameTable"):source.index("function materialTable")]
    assert 'data-duplicate-frame="${si}:${ri}"' in frame
    assert "Frame row duplicated" in source


def test_frame_grid_has_live_section_totals_and_targeted_reconciliation():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    for key in ("quantity", "square_feet", "perimeter_lf", "caulking_lf", "head_sill_qty"):
        assert f'["{key}",' in source
    assert 'data-frame-section-value="${si}:${key}"' in source
    assert "querySelectorAll(`[data-frame-section-value=" in source


def test_frame_base_and_alternate_share_section_workspace_and_full_grid_contracts():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    current = source[source.rindex("function renderFrames()") : source.index("function insertAlternateTabsAfterHeader")]
    assert "frameSectionScenarioHtml" in current
    assert "alternateFrameSectionModels" in source
    assert "effective_takeoff_sections" in source
    assert 'page==="bid"||page==="frames"' in source
    for contract in (
        "alternateFrameTable", "alternateMaterialTable", "alternateSectionCodePicker",
        "data-alt-frame-add", "data-alt-section-add", "data-alt-restore",
        "data-alt-frame-material", "data-alt-add-section-material",
        "data-alt-remove-section-material", "changeAlternateMaterialField",
        "bindAlternateFrameGrid", "pasteAlternateFrameGrid",
    ):
        assert contract in source
    for field in (
        "square_feet", "perimeter_lf", "caulking_lf", "head_sill_qty",
        "installation_material_ids",
    ):
        assert f'["{field}"' in source
    assert "data-alt-frame-qty-ack" in source and "toggleAlternateFrameQuantityAcknowledgement" in source
    assert "data-alt-frame-output" in source and "refreshAlternateFrameCalculatedView" in source
    assert "--frame-mark-width" in css and "--frame-qty-width" in css
    assert ".scenario-frame-workspace .frame-grid td:nth-child(1)" in css
    assert "position: sticky" in css and "var(--calculated)" in css and "var(--input)" in css


def test_frame_grid_uses_compact_contained_responsive_column_budget():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    frame_css = css[css.index("/* Frame Takeoff: shared Base/ALT estimating worksheet authority. */"):]
    assert "--frame-grid-min-width: 0" in frame_css
    assert "min-width: var(--frame-grid-min-width)" in frame_css
    assert ".scenario-frame-workspace .frame-grid { width: 100%" in frame_css
    assert "table-layout: fixed" in frame_css
    assert "overscroll-behavior-x: contain" in frame_css
    assert ".scenario-frame-workspace .frame-table .table-wrap" in frame_css
    assert "max-width: 100%" in frame_css and "overflow-x: auto" in frame_css
    for column in range(1, 19):
        assert f"nth-child({column})" in frame_css
    assert "width: 120rem" not in frame_css
    assert "text-overflow: ellipsis" in frame_css and "white-space: nowrap" in frame_css
    assert "data-overflow-title" in source and "bindFrameOverflowTitles" in source
    assert "diagonalHeaders:true" not in source
    assert ".scenario-frame-workspace .frame-grid thead th" in frame_css
    assert "data-frame-text-entry" in source and "bindFrameTextExpansion" in source
    assert 'frameTextEntry=frameOverflow&&field!=="mark"' in source
    assert "frame-text-entry-expanded" in frame_css
    assert "bindFrameColumnResizing" in source and "frame-column-resizer" in frame_css
    assert "--frame-frozen-mark-width" in frame_css
    assert ".frame-column-resizer::after" in frame_css and "display: none" in frame_css
    assert "vertical-align: middle" in frame_css
    assert "transform: scale" not in frame_css and "zoom:" not in frame_css
    for column, width in ((7, "4.5%"), (9, "4.7%"), (17, "4.7%")):
        assert f":nth-child({column}) {{ width: {width}; }}" in frame_css
    assert "th:is(:nth-child(7), :nth-child(9), :nth-child(17)) .sort-label" in frame_css
    assert "text-align: center" in frame_css and "white-space: normal" in frame_css
    assert 'mw-frame-column-widths-v3-compact-headers' in source

    # Desktop Frame columns consume the available body width. A usable mobile
    # floor is the sole horizontal-overflow fallback.
    assert "--sidebar-width: 15rem" in css
    assert "--workspace-padding-x: 18px" in css
    assert ".scenario-frame-workspace .frame-grid { min-width: 760px; }" in frame_css


def test_frame_material_pickers_offer_mixed_state_all_selection_in_base_and_alternates():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    picker = source[source.index("function syncMaterialPickerSelection") : source.index("function bindFrameOverflowTitles")]
    assert "data-material-select-all" in picker
    assert 'master.indeterminate=selected>0&&selected<choices.length' in picker
    assert 'master.setAttribute("aria-checked",master.indeterminate?"mixed"' in picker
    assert "changeAllBaseFrameMaterials" in picker
    assert "changeAllAlternateFrameMaterials" in source
    assert 'next=checked?[...rules]:[]' in source
    assert ".material-picker .material-picker-all" in css


def test_frame_quantity_issue_requires_dimensions_and_caulking_default_is_deferred():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    assert 'caulking_passes:null' in source[source.index("function blankFrameRow"):source.index("function normalizeFrameDimension")]
    missing = source[source.index("function frameMissingQuantity"):source.index("function framePageHead")]
    assert "width_inches" in missing and "height_inches" in missing
    assert "frameRowPopulated" not in missing

def test_systems_administrator_ui_only_scopes_override_lock_to_calculated_fields():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    function = source[source.index("function applySessionOverrideScope"):source.index("function render()")]
    assert "[data-session-override=\"project\"]" in function
    assert "#page [data-path]" not in function


def test_frame_fractional_outputs_use_semantic_admin_precision_without_local_rounding():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    frame = source[source.index("function frameTable") : source.index("function materialTable")]
    assert 'number(r.calculated?.square_feet,"square_footage")' in frame
    for field in ("perimeter_lf", "caulking_lf", "head_sill_qty"):
        assert f'number(r.calculated?.{field},"linear_footage")' in frame
    assert ".toFixed(" not in frame and "Math.round(" not in frame


def test_shared_table_controller_contract_and_excel_paste_are_loaded():
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    core = Path("app/static/ui-core.js").read_text(encoding="utf-8")
    assert "/assets/ui-core.js?v=" in html
    assert "new MWUI.TableController" in source
    assert 'event.key !== "Tab"' in core and 'event.key !== "Enter"' in core
    assert 'cell.tagName === "TEXTAREA"' in core
    assert "function horizontalVisibilityDelta" in core
    assert "function clampedHorizontalScroll" in core
    assert 'rootElement.addEventListener("focusin", this.onFocusIn)' in core
    assert 'target?.focus?.({ preventScroll: true })' in core
    assert "scheduleFocusVisibility(target)" in core
    assert "view.requestAnimationFrame(align)" in core
    assert 'table?.classList?.contains?.("frame-grid") || wrap.classList?.contains?.("frame-grid")' in core
    assert "wrap.scrollWidth, wrap.clientWidth" in core
    assert "parseClipboardMatrix" in core and "mapClipboard" in core
    assert "correlationId(\"paste\")" in core
    assert "normalizeExact()" in core and "normalizeExact:true" in source


def test_shared_grid_markup_is_semantic_and_preserves_editable_calculated_distinction():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    editor = source[source.index("function tableEditor"):source.index("function addButton")]
    calculated = source[source.index("function calculatedTableCell"):source.index("function tableEditor")]
    assert '<table class="data-grid app-data-table">' in editor
    assert '<th scope="col"' in editor
    assert "data-column-key" in editor
    assert "data-output-path" in source
    assert "calculatedTableCell" in editor and "<output " in calculated
    assert 'aria-label="${esc(column.label||field)}"' in source
    assert 'readonly aria-readonly="true"' in source
    assert 'class="trailing-row"' in source


def test_shared_visual_system_unifies_live_tables_and_frame_variants():
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    visual = css[css.index("/* Cohesive estimating workspace presentation."):]
    for token in (
        "--ui-canvas: #f3f6f4",
        "--ui-sidebar: #eef3f0",
        "--ui-brand: #244f41",
        "--ui-border: #d4ded9",
        "--table-header-height: 28px",
        "--table-row-height: 28px",
        "--table-cell-padding-x: 7px",
        "--control-height-compact: 26px",
    ):
        assert token in css
    assert ".table-wrap > table th" in visual
    assert ".table-wrap > table td" in visual
    assert ".data-grid td.calculated" in visual
    assert "[data-edit-table] td > input" in visual
    assert ".data-grid .row-action-cell button" in visual
    assert ".scenario-frame-workspace .frame-header-commercial" in visual
    assert ".scenario-frame-workspace .compact-material-grid" in visual
    assert ".scenario-frame-workspace .frame-grid thead .diagonal-column-label" in visual
    assert "transform: none" in visual
    assert "scrollbar-gutter: stable" in visual


def test_exact_frame_header_material_table_and_action_contracts():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    exact = css[css.index("/* Exact shared visual-system authority."):]
    assert "26px minmax(260px, 1fr) 72px 108px 88px 70px 30px" in exact
    assert "min-height: 66px" in exact
    for width in ("7.2%", "3.9%", "4.7%", "4.8%", "4.5%", "6.3%", "6.1%", "5%", "5.7%", "8.2%", "6%", "8.7%"):
        assert f"width: {width}" in exact
    assert "width: 636px" in exact
    for width in ("188px", "106px", "78px", "126px", "104px", "34px"):
        assert f"width: {width}" in exact
    assert 'class="frame-section-tab-edit"' in source
    assert 'class="frame-section-description"' in source
    assert 'class="history-unavailable"' in source
    assert 'class="data-grid installation-material-grid compact-material-grid formula-material-grid"' in source
    assert 'class="row-action-cell">${iconButton("×",`Remove ${rule.name}`' in source
    assert "width: 26px" in exact and ".row-action-cell" in exact


def test_wide_tables_are_contained_by_the_padded_workspace():
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    containment = css[css.index("/* Wide worksheets own their horizontal overflow."):]
    for selector in ("main", "#workspace", "#page", ".editable-table-shell", ".material-config", ".frame-table"):
        assert selector in containment
    assert "overflow-x: clip" in containment
    assert "overflow-x: auto" in containment
    assert "justify-items: stretch" in containment
    assert "justify-self: stretch" in containment
    assert "contain: inline-size" not in containment
    assert ".frame-material-list:has(.compact-material-grid)" in containment
    assert "width: min(780px, 100%)" in containment
    assert "overscroll-behavior-y: auto" in containment


def test_frame_section_header_finishing_contains_history_and_removes_link_decoration():
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    finishing = css[css.index("/* Frame section-header finishing:"):]
    assert "text-decoration: none" in finishing
    assert "width: 48px" in finishing and "height: 28px" in finishing
    assert "width: 36px" in finishing and "height: 24px" in finishing
    assert "top: clamp(4px" in finishing
    assert "border-left: 1px solid var(--ui-border-subtle)" in finishing


def test_shared_table_cells_and_direct_controls_are_vertically_centered():
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    centering = css[css.index("/* Keep every shared worksheet cell") :]
    for selector in (".table-wrap > table", "table.data-grid", "table.app-data-table"):
        assert selector in centering
    assert "> tr > :is(th, td)" in centering
    assert "td > :is(input, select, textarea, button, output)" in centering
    assert centering.count("vertical-align: middle") >= 2
    assert ".alternate-grid td { vertical-align: top; }" not in css


def test_frame_inner_controls_are_centered_and_spec_sections_use_tabs():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    assert "function renderTabbedFrames" in source
    assert "activeFrameSectionByScenario:new Map()" in source
    assert 'role="tablist"' in source and 'role="tab"' in source
    assert 'data-frame-section-tab' in source and 'data-frame-section-scenario' in source
    assert "frames:renderTabbedFrames" in source
    assert ".scenario-frame-workspace .frame-section-tabs" in css
    assert ".scenario-frame-workspace .frame-section-tab.is-active" in css
    assert 'td > :is(input:not([type="checkbox"]), select, textarea)' in css
    assert "line-height: 18px" in css
    assert "td > :is(output, span)" in css
    assert "function alternateNumberLabel" in source
    assert "function alternateTabs()" in source
    tabbed = source[source.index("function renderTabbedFrames") : source.index("function insertAlternateTabsAfterHeader")]
    assert "alternateTabs(true)" in tabbed
    assert 'class="frame-section-add-tab"' in tabbed
    assert "＋ New section</button></nav>" in tabbed
    assert "description=" not in tabbed
    assert "<span>${esc(description)}</span>" not in tabbed
    assert ".scenario-frame-workspace .frame-section-add-tab" in css
    assert 'workspace-toolbar scenario-toolbar' not in tabbed
    assert '"Base takeoff"' not in tabbed


def test_alternate_route_refresh_totals_band_and_state_rail_contracts():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    assert 'new URLSearchParams(window.location.search).get("alternate")' in source
    assert '?alternate=${encodeURIComponent(alternateId)}' in source
    assert 'openProject(route.projectId,false,route.page,"replace",route.alternateId)' in source
    assert 'openProject(state.doc.project.id,false,state.page,"replace",state.ui.activeAlternateId)' in source
    assert '<section id="welcome" class="welcome" hidden>' in html
    assert '$("#welcome").hidden=false' in source
    assert "function frameTotalsRail" in source
    assert "afterTable:frameTotalsRail(s,si)" in source
    assert '<tfoot><tr class="frame-subtotal-row">' not in source
    assert '<tfoot aria-label="Frame totals">' not in source
    assert 'class="frame-totals-rail"' in source
    assert ".scenario-frame-workspace .frame-totals-rail" in css
    totals_css = css[css.index(".scenario-frame-workspace .frame-totals-rail {") : css.index(".scenario-frame-workspace .frame-table > .compact-add")]
    assert "border: 0" in totals_css
    assert "border-top" not in totals_css and "border-right" not in totals_css
    assert 'widths.map(width=>`${width}px`)' in source
    assert 'rail.style.width=`${widths.reduce((sum,width)=>sum+width,0)}px`' in source
    assert 'grid.matches(".table-wrap")?grid.querySelector(":scope > .frame-totals-rail")' in source
    assert "grid-template-columns:" in totals_css
    assert ".frame-totals-rail > span:nth-child(2)" in totals_css
    assert "background: var(--surface)" in totals_css
    assert "function bindTransientFrameScrollbars" in source
    assert 'wrap.classList.add("is-horizontal-scrolling")' in source
    assert 'wrap.classList.toggle("is-scrollbar-hovered",nearScrollbar)' in source
    assert ".is-horizontal-scrolling::-webkit-scrollbar-thumb" in css
    assert ".is-scrollbar-hovered::-webkit-scrollbar-thumb" in css
    assert ".table-wrap::-webkit-scrollbar { height: 0; background: transparent; }" in css
    assert ".table-wrap.is-scrollbar-hovered::-webkit-scrollbar { height: 8px; }" in css
    assert "scrollbar-width: none" in css
    assert ".table-wrap::-webkit-scrollbar-thumb:hover" in css
    assert ".frame-table .table-wrap:hover::-webkit-scrollbar-thumb" not in css
    assert ":is(table.frame-grid, .frame-grid > table)" in css
    assert ":is(table.frame-grid, .frame-grid > table) tr > :first-child { border-left: 1px solid var(--ui-border); }" in css
    assert ".frame-table .table-wrap" in css and "border: 0 !important" in css
    assert '.querySelectorAll(".scenario-frame-workspace .frame-table .table-wrap")' in source
    assert ".frame-totals-rail > span:first-child { border-left: 0 !important" in css
    assert ".frame-grid tbody tr:last-child td:first-child { border-bottom-left-radius: 5px; }" in css
    rail = css[css.index("/* Alternate state is communicated by row color") :]
    assert "border-left: 1px solid var(--ui-border)" in rail
    assert "box-shadow: none" in rail


def test_bid_workspace_and_review_pdf_are_compact_and_scenario_aware():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    main = Path("app/main.py").read_text(encoding="utf-8")
    worksheet = source[source.index("function renderBidWorksheet") : source.index("function renderProposalLegacy")]
    assert "visibleSummaries=summaries.filter" in worksheet
    assert 'groupKey=`cost-code|${summary.code}`' in worksheet
    assert 'colspan="9"' in worksheet
    assert "Bid Review PDF" in worksheet and "bid-review.pdf" in worksheet
    assert "alternateNumberLabel(alt)" in source
    assert ".bid-worksheet .bid-breakdown > table" in css
    assert "min-width: 0" in css and "overflow-x: clip" in css
    assert '@app.get("/api/projects/{project_id}/bid-review.pdf")' in main
    assert "def _render_bid_review_pdf" in main
    assert '"Cache-Control": "no-store"' in main


def test_blank_frame_drafts_disappear_when_focus_leaves():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    draft = source[source.index("function dismissEmptyFrameDraft") : source.index("function handleManualAddressChange")]
    assert 'startsWith("frames-")' in draft
    assert "frameRowPopulated(draft)" in draft
    assert "state.ui.activeDraftTables.delete(tableId)" in draft
    assert "state.ui.drafts.delete(tableId)" in draft
    assert 'document.addEventListener("pointerdown",dismissEmptyFrameDraft,true)' in source


def test_frame_spec_section_cost_code_is_selected_on_create_and_edited_from_tab():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    scenario = source[source.index("function frameSectionScenarioHtml") : source.index("function renderFrames")]
    tabbed = source[source.index("function renderTabbedFrames") : source.index("function insertAlternateTabsAfterHeader")]
    assert 'class="frame-section-code"' not in scenario
    assert "function chooseFrameSectionCostCodeUI" in source
    assert "function addFrameSectionUI" in source
    assert 'data-frame-managed-cost-code required autofocus' in source
    assert 'if(!code)return;' in source
    assert 'data-frame-section-add="${alt?"alternate":"base"}"' in tabbed
    assert 'data-frame-section-code-edit' in tabbed
    assert "function editFrameSectionCostCodeUI" in source
    assert 'const FRAME_DELETE_SECTION="__frame_delete_section__"' in source
    assert "allowDelete:true" in source
    assert 'deleteButton.textContent="Delete section"' in source
    assert 'data-dialog-transient-action' in source
    assert 'setAlternateRemoved(`takeoff_sections|${section.id}`,true)' in source
    assert 'removeAlternateAdded(`takeoff_sections|${model.addedIndex}`)' in source
    assert 'reason:"Frame Spec Section deleted from tab editor"' in source
    assert ".dialog-actions .dialog-destructive-action" in css
    assert ".scenario-frame-workspace .frame-section-tab-edit" in css


def test_frame_qty_sticky_offset_tracks_the_measured_mark_column():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    assert "function syncFrameFrozenColumnOffsets" in source
    assert 'headers.map(header=>header.getBoundingClientRect().width)' in source
    assert 'grid.style.setProperty("--frame-frozen-mark-width"' in source
    assert 'rail.style.setProperty("--frame-frozen-mark-width"' in source
    assert 'new ResizeObserver(()=>syncFrameFrozenColumnOffsets(workspace))' in source
    assert ":nth-child(2) { position: sticky; left: var(--frame-frozen-mark-width)" in css


def test_frame_header_sell_per_sf_matches_the_quote_inclusive_history_metric():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    helper = source[source.index("function frameSectionSellPerSf"):source.index("function frameTotalsRail")]
    assert "cost_code_summaries" in helper
    assert "dollars_per_square_foot" in helper
    assert "selling_value" in helper and "total_square_feet" in helper
    assert "Sell $/ft²" in helper
    assert 'attribute("sell_per_sf")' in helper
    assert "including the selected quote and other Bid components" in helper
    assert "sell_per_sf:frameSectionSellPerSf(section,true)" in source
    assert "sell_per_sf:frameSectionSellPerSf(section,false)" in source


def test_shared_table_sorting_quotes_dual_codes_and_markup_authority_contracts():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    core = Path("app/static/ui-core.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")

    assert "class SortStateStore" in core
    assert "function cycleSort" in core and "function stableSortRows" in core
    assert "Blank values remain after real values in either direction" in core
    assert "Shift-click to sort by multiple columns" in core
    assert "tableSortStateKey" in source
    assert "project,state.page,scenario,history,tableId" in source
    assert "MWUI.stableSortRows(canonicalRows" in source
    assert "canonicalRows.indexOf(row)" in source
    assert "function bindStaticTableSorting" in source and "staticRowGroups" in source
    sort_binding = source[source.index("function bindTableSorting"):source.index("function bindPage")]
    assert "bindTableSorting" in source and "markDirty" not in sort_binding
    assert ".table-sort-button" in css and ".app-data-table" in css

    quote = source[source.index("function quoteTable"):source.index("function quoteGroupSummary")]
    rendered = source[source.index("function renderQuotes"):source.index("function frameSectionName")]
    assert 'key:"code",label:"Cost Code",type:"select"' in quote
    assert 'id:"quotes"' in quote
    assert "quoteTableForCode" not in rendered
    assert "One continuous table" in rendered

    bid = source[source.index("function renderBidWorksheet"):source.index("function renderProposalLegacy")]
    assert '<th scope="col">Cost Code</th><th scope="col">Description</th>' in bid
    source_rows = source[source.index("function bidWorksheetSourceRows"):source.index("function bidWorksheetComponentRows")]
    assert "actual_cost_code" in source_rows
    assert "function actualCostCodeOptions" in source
    assert 'input[data-path$=".cost_code"]' in source and 'input[data-alt-material-field$="|cost_code"]' in source
    assert "markup_percent" in source and "markup_amount" in source
    assert "function alternateLabel" in source and "Alternate ${sequence}" in source


def test_tooltip_and_modal_drawer_are_shared_accessible_primitives():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    core = Path("app/static/ui-core.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    assert "new MWUI.TooltipController(document,{delay:400})" in source
    assert "new MWUI.DrawerController(document.body,{onClose:" in source
    assert "data-tooltip" in source and "aria-label" in source
    for contract in (
        "pointerover", "pointerout", "focusin", "focusout", 'key === "Escape"',
        "aria-describedby", "returnFocus", 'role", "dialog"', 'aria-modal", "true"',
    ):
        assert contract in core
    assert ".mw-tooltip" in css and ".mw-drawer-layer" in css
    assert "text-decoration: underline dotted" not in css
    assert "[data-tooltip] {\n  text-decoration: none;\n}" in css


def test_analogous_estimating_modules_share_compact_surfaces_and_status_language():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    for renderer, marker in (
        ("renderQuotes", "quote-workspace"),
        ("renderDoors", 'class="work-panel"'),
        ("renderEquipment", 'class="work-panel"'),
        ("renderLabor", 'class="work-panel"'),
    ):
        block = source[source.index(f"function {renderer}"):]
        assert marker in block[:12000]
    assert 'statusBadge("Controlled","controlled")' in source
    assert 'statusBadge("Project override","override"' in source or 'statusBadge("Override","override"' in source
    assert '"acknowledged-exception":"incomplete-row"' in source
    assert "Credit is applied before Surcharge" in source


def test_bid_uses_compact_historical_instrument_and_lazy_evidence_drawer():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    assert "function historyIndicator" in source
    assert "history-track" in source and "anchor q1" in source and "anchor q3" in source
    assert "Historical position is advisory and never changes pricing or submission." in source
    assert "/historical/bid-cost-codes" in source
    assert "/historical/bid-cost-code?code=" in source
    assert "openHistoricalDetail" in source and "drawerController?.open" in source
    assert ".history-indicator" in css and "--history-position" in css
    assert "hasQuartiles" in source and 'class="history-indicator loading no-history"' in source
    assert "historyDetailRequest" in source and "sequence!==state.historyDetailRequest" in source
    assert ".history-indicator.no-history" in css
    assert ".history-evidence" in css and ".drawer-metrics" in css


def test_history_slider_uses_symmetric_risk_scale_and_prominent_current_pin():
    styles = Path("app/static/styles.css").read_text(encoding="utf-8")
    track_rule = styles.split(".history-indicator > .history-track {", 1)[1].split("}", 1)[0]
    pin_rule = styles.split(".history-indicator .history-track > .current {", 1)[1].split("}", 1)[0]

    assert track_rule.count("rgba(163, 58, 53") == 2
    assert track_rule.count("rgba(181, 108, 21") == 2
    assert "rgba(65, 132, 99" in track_rule
    assert track_rule.index("rgba(163, 58, 53") < track_rule.index("rgba(181, 108, 21") < track_rule.index("rgba(65, 132, 99")
    assert "0 20%" in track_rule and "20% 40%" in track_rule and "40% 60%" in track_rule
    assert "60% 80%" in track_rule and "80% 100%" in track_rule
    assert "width: 1rem" in pin_rule and "height: 1rem" in pin_rule
    assert "border: 0.1875rem solid var(--brand)" in pin_rule
    assert "box-shadow:" in pin_rule and "transform: translate(-50%, -50%)" in pin_rule


def test_editable_table_number_cells_hide_native_spinner_controls():
    styles = Path("app/static/styles.css").read_text(encoding="utf-8")
    assert 'td input[type="number"]' in styles
    assert 'input[type="number"]::-webkit-inner-spin-button' in styles
    assert "appearance: textfield" in styles
    assert "-webkit-appearance: none" in styles


def test_numeric_presentation_uses_central_semantic_precision_without_mutating_calculations():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    core = Path("app/static/ui-core.js").read_text(encoding="utf-8")
    assert "precisionSettings" in source and "numericCategory" in source
    assert "MWUI.formatNumeric" in source and "DEFAULT_DECIMAL_PRECISION" in core
    assert "data-raw-numeric" in source and "data-numeric-category" in source
    assert 'type==="currency"||type==="number"?"text":type' in source


def test_open_historical_detail_tracks_the_authoritative_saved_revision():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    save = source[source.index("async function save"):source.index("function input")]
    detail = source[source.index("function refreshOpenHistoricalDetail"):source.index("function fallbackBidSummaries")]
    assert "refreshOpenHistoricalDetail()" in save
    assert "if(state.dirty||state.saving)await ensureSaved()" in detail
    assert "state.historyDetailCode" in detail and "state.historyDetailLoading" in detail
    assert "result.project_revision" in detail and "state.doc.project.revision" in detail


def test_responsive_theme_wraps_or_scrolls_instead_of_hiding_critical_content():
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    assert "@media (max-width: 65.625rem)" in css
    assert "@media (max-width: 47.5rem)" in css
    assert ".bid-description" in css and "white-space: normal" in css
    assert ".table-wrap" in css and "overflow-x: auto" in css
    general_css = css[:css.index("/* Frame Takeoff: shared Base/ALT estimating worksheet authority. */")]
    assert "text-overflow: ellipsis" not in general_css
    assert "text-overflow: ellipsis" in css and "data-overflow-title" in Path("app/static/app.js").read_text(encoding="utf-8")


def test_new_controlled_project_fields_and_local_deadline_are_rendered():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    assert "New Construction - Curtainwall" in source
    assert 'CONTRACT_TYPES=["Bid to CM/GC","Bid as GC"]' in source
    assert 'WAGE_TYPES=[["Non-PW","Non-PW"],["PW","Prevailing Wage (PW)"]]' in source
    assert '"Bid due date and time","datetime-local"' in source


def test_cost_code_custom_and_server_authoritative_cascade_contracts():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    assert "/cost-codes/custom" in source and "expected_revision" in source
    assert "confirm_cascade:false" in source and "requires_confirmation" in source
    assert "dependency_report" in source and "confirm_cascade:true" in source


def test_quote_selection_and_bid_edit_use_canonical_contracts():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    assert "working_estimate.quote_selection_by_code" in source
    assert 'selected_quote_ids:selected' in source
    assert 'field==="square_feet"' in source
    assert 'source=parsed===null||parsed===""?"unassigned":"manual"' in source
    assert "function synchronizeQuoteSelection" in source
    assert "sameCostCode(row.code,code)&&row.used" in source
    assert 'tableEditor("quotes",columns' in source
    assert "all.splice(last+1,0,row)" not in source
    assert 'isManualQuoteMode(mode)' in source
    assert 'nextValue=values.value==="true"' in source
    assert 'changes:{[values.field]' in source
    assert "confirmed:true" in source
    assert 'const BID_SOURCE_TYPES={quote:"quote",frame_material:"frame"' in source
    assert 'source_type:sourceType,source_id:sourceId' in source
    assert 'source.source_type||source.category||"estimate_line"' not in source
    assert ("lineage.entered_price" in source and "lineage.final_adjusted_value" in source) or ("quoteLineage.entered_price" in source and "quoteLineage.final_adjusted_value" in source)


def test_validation_tooltips_mobile_navigation_and_popovers_keep_accessible_state():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    core = Path("app/static/ui-core.js").read_text(encoding="utf-8")
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    assert 'cell.setAttribute("data-tooltip"' in core
    assert 'cell.removeAttribute("data-tooltip")' in core
    assert "cell.title" not in core
    assert 'attributeFilter: ["data-tooltip"]' in core
    assert 'aria-controls="sidebar" aria-expanded="false"' in html
    assert 'aria-label="Active role"' in html and 'aria-label="Actor identity"' in html
    assert "sidebar.inert=mobile&&!isOpen" in source
    assert "function positionMaterialPicker" in source
    assert 'event.key!=="Escape"||!details.open' in source


def test_authoritative_reconciliation_updates_new_summary_surfaces_without_active_grid_rebuild():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    block = source[source.index("function reconcileCalculatedView"):source.index("function rowInput")]
    for marker in (
        "refreshTableRowStates()", "refreshQuoteGroupSummaries()", "refreshBidPanel()",
        "[data-borrowed-total]", "[data-labor-total]", "[data-door-status]",
        "[data-bid-total]", "[data-page-bid-version]",
    ):
        assert marker in block
    assert "function warningCostCode" in source and "bidWarningsForCode(warnings,summary.code)" in source


def test_quote_groups_preserve_disclosure_and_proposal_links_are_not_nested_controls():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    assert "collapsedQuoteGroups" in source
    assert 'details[data-quote-group]' in source
    proposal = source[source.index("function renderProposal"):source.index("function renderReview")]
    assert 'class="button-link"' in proposal
    assert "<a " in proposal and "<button" not in proposal


def test_project_address_has_dynamic_route_mileage_and_manual_override():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    project = source[source.index("function mileageField") : source.index("function renderScope")]
    assert "data-calculate-mileage" in source
    assert "queueMileageCalculation" in source
    assert "/mileage`" in source
    assert 'data-path="project.miles_from_rogers"' in source
    assert "mileageInput.value=result.mileage.miles" in source
    assert 'step="0.1"' in source
    assert "item.label||item.matched_address" in source
    assert "latitude:item.latitude" in source and "longitude:item.longitude" in source
    assert "attribution:item.attribution" in source
    assert project.count('data-address-search') == 1
    assert 'input("project.mwd_po"' not in project
    for redundant_field in ("project.address_street", "project.address_city", "project.address_state", "project.zip", "project.county"):
        assert f'input("{redundant_field}"' not in project
    mileage = source[source.index("function mileageField") : source.index("function addressSearchInput")]
    assert 'data-tooltip="${esc(detail)}"' in mileage
    assert "<small>" not in mileage


def test_owner_lookup_is_owner_specific_and_fills_reusable_organization_details():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    project = source[source.index("function renderProject") : source.index("function renderScope")]
    assert 'historicalInput("project.owner_name","Owner","owners")' in project
    fill = source[source.index("function fillProjectOwnerFromMaster") : source.index("function selectScopeTableReference")]
    for field in ("owner_name", "owner_organization_id", "owner_legal_name", "owner_address", "owner_website", "owner_phone", "owner_email"):
        assert field in fill
    autocomplete = source[source.index("function bindAutocompletes") : source.index("function completePromotedTableRow")]
    assert 'kind==="owners"&&target.dataset.path==="project.owner_name"' in autocomplete
    assert "fillProjectOwnerFromMaster(item)" in autocomplete


def test_async_saves_and_workspace_transitions_are_project_identity_safe():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    save = source[source.index("async function save") : source.index("function input")]
    assert "projectId=snapshot.project.id" in save
    assert "sequence=++state.saveSequence" in save
    assert "sequence===state.saveSequence&&state.doc?.project?.id===projectId" in save
    assert "if(!isCurrentSave())return" in save
    assert 'result.project?.project?.id!==projectId)throw new Error("The save response did not match the active project.")' in save
    assert "catch(error){if(!isCurrentSave())return" in save
    assert "finally{if(!isCurrentSave())return" in save

    transition = source[source.index("function transitionWorkspaceIdentity") : source.index("function statusBadge")]
    assert "const identityChanged=state.doc?.project?.id!==nextProjectId" in transition
    assert "state.saveSequence++" in transition
    identity_only = transition[transition.index("if(identityChanged)") :]
    for marker in (
        "state.ui.drafts.clear()", "state.ui.pendingCells=new MWUI.PendingCellStore()",
        "state.ui.expandedBid.clear()", "state.collapsedFrameSections.clear()",
        "state.collapsedMaterialSections.clear()", "state.collapsedQuoteGroups.clear()",
    ):
        assert marker in identity_only

    boundaries = {
        "openProject": "async function newProject",
        "newProject": "async function generateTestProject",
        "generateTestProject": "async function duplicate",
        "duplicate": "async function refresh",
        "importJson": "function navigatePage",
    }
    for function_name, end_marker in boundaries.items():
        block = source[source.index(f"function {function_name}") : source.index(end_marker)]
        assert "++state.openProjectRequest" in block
        assert "transitionWorkspaceIdentity(r.project.project.id)" in block
    open_project = source[source.index("async function openProject") : source.index("async function newProject")]
    assert open_project.count("request!==state.openProjectRequest") >= 3


def test_dialog_and_custom_cost_code_mutation_drain_and_guard_project_state():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    dialog = source[source.index("function dialogForm") : source.index("function masterItemLabel")]
    assert 'dialog.returnValue=""' in dialog
    assert 'value="cancel" formnovalidate' in html

    custom = source[source.index("async function openCustomCostCode") : source.index("function addRow")]
    assert "const projectId=state.doc?.project?.id" in custom
    assert custom.index("await ensureSaved()") < custom.index("values.expected_revision=state.doc.project.revision")
    assert "state.doc?.project?.id!==projectId" in custom
    assert "result.project&&result.project.project?.id!==projectId" in custom
    ensure = source[source.index("async function ensureSaved") : source.index("function updateHeader")]
    assert "while(state.saving&&state.doc?.project?.id===projectId)" in ensure


def test_live_estimate_strip_rolls_directionally_without_reflowing_save_status():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    live = source[source.index("function signedMoney") : source.index("function updateHeader")]
    assert "requestAnimationFrame(step)" in live
    assert 'live-tick-${direction}' in live
    assert "prefers-reduced-motion: reduce" in live
    assert "Math.abs(item.delta)>=0.005" in live
    assert 'liveEstimateEntry("base","Base"' in live
    assert "live-estimate-tick-up" in css and "live-estimate-tick-down" in css
    assert ".calculated-dollar-total:not(.data-grid *)" in css
    assert "font-family: var(--font-display)" in css
    assert ".save-pill" in css and "width: 92px" in css
    assert "justify-content: center" in css
    assert "border-bottom: 1px solid var(--ui-border-subtle)" not in css[css.index(".live-estimate-entry > strong"):css.index(".topbar > .mobile-only")]


def test_focused_numeric_cells_keep_configured_display_precision():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    focus_handler = source[source.rindex('document.addEventListener("focusin"'):]
    assert "input.select?.()" in focus_handler
    assert "input.value=input.dataset.rawNumeric" not in focus_handler
