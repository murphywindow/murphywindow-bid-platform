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
        "--ui-brand: #295b4b", "--table-editable-bg: #ffffff",
        "--table-calculated-bg: #f5f8f7", "--focus-ring: 0 0 0 2px",
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
    assert "applyAuthoritativeCalculationBatch(result.project)" in save
    batch = source[source.index("function applyAuthoritativeCalculationBatch"):source.index("function rowInput")]
    assert "reconcileCalculatedView()" in batch
    assert "render()" not in save
    assert "state.mutationSequence++" in source
    assert "state.mutationSequence===mutationAtStart" in save


def test_installation_material_dialog_recalculates_formula_totals_after_autosave():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    reconcile = source[source.index("function reconcileCalculatedView"):source.index("function rowInput")]
    refresh = source[source.index("function refreshOpenInstallationMaterialDialog"):source.index("const ROW_STATE_CLASSES")]
    assert "refreshOpenInstallationMaterialDialog()" in reconcile
    assert 'dialog.installation-material-dialog[open]' in refresh
    assert "previewMaterialFormulaEditor(control)" in refresh
    assert "data-installation-material-dialog-total" in source
    assert 'pre_tax_material_cost`)}"]`' in source
    assert 'if(commit(true))queueMicrotask(()=>save())' in source
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
    assert "Repeatable frame sections calculate whole-unit area" not in source
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
    assert 'PAGE_SLUGS=Object.freeze({project:"info"})' in source
    assert 'match[2]==="info"||match[2]==="project"?"project"' in source
    for contract in (
        "function updateRouteSearch", "function setScenarioTabRoute", "function applyScenarioRoute",
        "function rememberRouteTrigger", "function restoreRoutedOverlay", "function setPopupRoute",
        "function clearPopupRoute", 'params.get("tab")', 'params.get("section")',
        'params.get("popup")', 'params.get("parentPopup")', 'params.get("parentTrigger")', 'params.get("drawer")',
    ):
        assert contract in source
    assert 'setScenarioTabRoute(tab.dataset.scenarioTabKind,tab.dataset.scenarioTabId)' in source
    assert 'document.addEventListener("click",event=>rememberRouteTrigger(event.target,"click"),true)' in source
    assert 'document.addEventListener("change",event=>rememberRouteTrigger(event.target,"change"),true)' in source
    assert 'if(routeTrigger)setPopupRoute(title,routeTrigger)' in source
    assert 'if(route.popup===popupSlug||route.parentPopup===popupSlug)clearPopupRoute({all:true})' in source
    assert 'if(!refresh&&currentRoute().drawer!==String(code))updateRouteSearch' in source
    assert "applyScenarioRoute(route);render();buildNav();restoreRoutedOverlay(route)" in source


def test_application_chrome_is_fixed_and_workspace_owns_vertical_scrolling():
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    contract = css[css.index("/* Fixed application chrome") :]
    assert "height: 100dvh" in contract
    assert "body {" in contract and "overflow: hidden" in contract
    assert "height: calc(100dvh - var(--topbar-height))" in contract
    assert "main {" in contract and "overflow-y: auto" in contract
    assert ".sidebar {" in contract and "height: 100%" in contract
    assert ".actionbar {" in contract and "position: static" in contract
    assert 'workspaceScroll=document.querySelector("main")' in source
    assert 'document.querySelector("main")?.scrollTo' in source


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
        "function revertBaseMaterialFormula", "function revertAlternateMaterialFormula", "function restoreMaterialFormulaRow",
        "function previewMaterialFormulaEditor", "function materialFormulaSourceValues",
        "function calculateMaterialFormulaTotal", "data-material-source-values", "data-material-rate",
        'class="material-formula-result"', "data-material-rate-input", 'class="material-totals-rail"',
    ):
        assert contract in runtime
    assert 'control.matches("[data-material-custom-quantity]")?"quantity":"multiplier"' in runtime
    assert '["custom","Custom"]' in runtime
    assert "custom_quantity_override" in runtime
    assert "control.value=formatNumeric(value,category)" in runtime
    assert 'number(operand,"multiplier")' in runtime
    assert "source_override" in services and "operator_override" in services and "operand_override" in services
    assert '"calculated_quantity"' in services and '"invalid_installation_material_formula"' in services
    assert ".scenario-frame-workspace .material-formula-editor" in css
    assert ".scenario-frame-workspace .formula-material-grid" in css
    assert ".scenario-frame-workspace .material-totals-rail" in css
    assert 'data-frame-material-total="${si}"' in runtime
    assert 'data-alt-material-total="${esc(section.id)}"' in runtime
    assert "function materialFormulaControlValue" in runtime
    assert "function commitMaterialFormulaControl" in runtime
    assert "function commitCustomMaterialQuantityBeforeRate" in runtime
    assert "function clearBaseMaterialRateOverride" in runtime
    assert 'button.onclick=()=>clearBaseMaterialRateOverride(button)' in runtime
    rate_revert = runtime[runtime.index("function clearBaseMaterialRateOverride") : runtime.index("function positionMaterialFormulaPopover")]
    assert 'dialog.close' not in rate_revert and "render()" not in rate_revert
    assert 'dataset.materialFormulaSource==="custom"' in source
    assert "commitCustomMaterialQuantityBeforeRate(input)" in runtime
    assert 'control.addEventListener("input"' in source
    assert "commitMaterialFormulaControl(control,{restoreInvalid})" in source
    source_options = runtime[runtime.index("const MATERIAL_FORMULA_SOURCES") : runtime.index("const MATERIAL_FORMULA_OPERATORS")]
    for removed_source in ("tie_back_qty", "backpan_lf", "manual_quantity"):
        assert removed_source not in source_options
    assert 'source=MATERIAL_FORMULA_SOURCES.some(([value])=>value===storedSource)?storedSource:"custom"' in runtime
    assert 'if(sourceControl?.value==="custom")commitMaterialFormulaControl(sourceControl,{restoreInvalid})' in source
    assert 'displayedQuantity=source==="custom"?customQuantity:quantity??calculateMaterialFormulaTotal' in runtime
    assert 'data-material-formula-operand' in runtime
    assert 'data-material-formula-operator' in runtime
    assert 'data-material-formula-toggle' in runtime
    assert 'data-material-formula-popup' in runtime
    assert '>Formula</button>' in runtime
    assert 'data-material-formula-unit-label' in runtime
    assert 'materialFormulaUnitLabel(quantity,unitControl.value)' in runtime
    assert "unitLabel.title=materialFormulaUnitTitle(quantity,unitControl.value)" in runtime
    assert '"linear foot","Linear feet (LF)"' in source
    assert '"ft²","Square feet (SF)"' in source
    assert '"each","Each (EA)"' in source
    assert 'function bindMaterialFormulaPopovers' in runtime
    assert 'function positionMaterialFormulaPopover' in runtime
    assert 'popover data-material-formula-popup' in runtime
    assert "operandControl.hidden=custom" not in runtime
    assert "operatorControl.tabIndex=-1" in runtime
    assert "operandControl.tabIndex=-1" in runtime
    assert 'quantityReadonly=source==="custom"?"":"readonly aria-readonly=\\"true\\" tabindex=\\"-1\\""' in runtime
    assert 'customControl.removeAttribute("tabindex")' in runtime
    assert "customControl.tabIndex=-1" in runtime
    assert 'editor.classList.toggle("is-custom",custom)' in runtime
    assert 'formulaHidden=source==="custom"?\'aria-hidden="true" tabindex="-1"\':""' in runtime
    assert ".material-formula-editor.is-custom" in css
    assert "[data-material-formula-operator]" in css
    assert "[data-material-formula-operator-field]" in css
    assert "[data-material-formula-operand-field]" in css
    assert "[data-material-formula-unit-field]" in css
    assert "border-left: 1px solid var(--ui-divider)" in css
    assert "margin-left: 5px" in css and "padding-left: 9px" in css
    assert "display: none" in css
    assert "grid-template-columns: 56px minmax(112px, 1fr)" in css
    assert ".material-formula-popover" in css
    assert "width: max-content" in css
    assert ".material-formula-config-grid" in css and "display: flex" in css
    assert ".material-formula-output [data-material-formula-unit-label]" in css
    assert "grid-template-columns: 88px 72px" in css
    assert "width: 72px" in css
    assert "text-overflow: ellipsis" in css
    assert ".material-formula-editor:not(.is-custom) .material-formula-result" in css
    assert "pointer-events: none" in css and "user-select: none" in css and "caret-color: transparent" in css
    formula_markup = runtime[runtime.index('class="material-formula-popover"') : runtime.index('class="material-formula-output"')]
    assert "material-formula-revert" in formula_markup
    assert "Restore default formula" in formula_markup
    assert ">↶</button>" in formula_markup
    assert ".material-formula-revert:disabled { visibility: visible" in css
    assert 'const total=materialCosts.reduce((sum,value)=>sum+value,0),formatted=money(total)' in runtime
    assert 'data-numeric-category="multiplier"' in runtime
    assert 'data-material-rate-input="${esc(group)}"' in runtime
    assert 'data-numeric-category="currency"' in runtime
    assert 'formatMaterialDollarRateControl(input' in runtime
    assert 'input.dataset.rawNumeric??""' in runtime
    assert 'if(!committed)event.stopImmediatePropagation()' in runtime
    assert 'data-clear-rate-override="${esc(ratePath)}" ${hasRateOverride?"":"disabled"}' in runtime
    assert 'revert.disabled=value===null' in runtime
    assert "<small>Total</small>" not in runtime
    assert "_materialFormulaTimer" not in runtime
    assert 'control.isConnected)control.dispatchEvent(new Event("change",{bubbles:true}))' not in runtime
    assert 'control.addEventListener("input",()=>{commitCustomSource(false);if(commitMaterialFormulaControl(control,{restoreInvalid:false}))markEdited()})' in source
    assert 'control.addEventListener("input",()=>{preview()' not in source
    assert "revertBaseMaterialFormula(button.dataset.revertMaterialFormula,button)" in runtime
    assert "revertAlternateMaterialFormula(button.dataset.altRevertMaterialFormula,button)" in runtime
    restore = runtime[runtime.index("function restoreMaterialFormulaRow") : runtime.index("function revertBaseMaterialFormula")]
    assert ".focus(" not in restore
    assert 'dialog?.open)dialog.close("cancel");revertBaseMaterialFormula' not in runtime
    assert 'dialog?.open)dialog.close("cancel");revertAlternateMaterialFormula' not in runtime
    for attribute in ("data-material-path", "data-material-alt-section-field", "data-material-alt-section-added"):
        assert attribute in runtime
    for heading in (">Material</span>", ">Quantity</span>", ">Rate</span>", ">Cost</span>"):
        assert heading in runtime
    assert "Unit<br>price" not in runtime and "Total<br>cost" not in runtime
    assert runtime.count('class="material-rate-cell"') >= 2
    assert "rate in dollars per" in runtime
    assert "data-material-rate-unit" in runtime
    assert 'class="material-quantity-heading"' in runtime
    assert ".formula-material-grid .material-rate-cell::before" in css
    assert 'content: "$"' in css
    assert ".formula-material-grid .material-quantity-heading" in css
    assert ".formula-material-grid [data-material-rate-unit]" in css
    for technical_heading in ("Installation<br>material", "Quantity<br>formula", "Unit<br>rate", "Extended<br>cost"):
        assert technical_heading not in runtime
    for contract in ("width: 230px", "width: 260px", "width: 220px", "width: 120px", "width: 54px"):
        assert contract in css
    assert "width: 884px; min-width: 884px; max-width: 884px" in css
    assert "grid-template-columns: 230px 260px 220px 120px 54px" in css
    assert "width: calc(100% - 78px) !important" in css
    assert ".material-rate-cell > .override-control" in css
    assert ".material-rate-cell > input" in css
    assert "border: 0" in css and "background: transparent" in css
    material_shell_start = css.rindex(".scenario-frame-workspace .frame-material-list {")
    material_shell = css[material_shell_start : css.index(".scenario-frame-workspace .compact-material-grid {", material_shell_start)]
    assert "border: 0" in material_shell and "border-radius: 0" in material_shell
    assert ".formula-material-grid tr > :first-child { border-left: 1px solid" in css
    assert "grid-template-columns: minmax(72px, 110px) 34px 8px" not in css
    for contract in (
        ".formula-material-grid tr > :first-child",
        ".formula-material-grid thead tr:first-child > th",
        ".formula-material-grid tbody tr:last-child td:first-child",
        ".formula-material-grid tbody tr:last-child td:last-child",
        ":is(.row-actions-heading, .row-action-cell)",
        ".installation-material-dialog [data-add-section-material]",
    ):
        assert contract in css
    assert '<button class="secondary compact-add"' not in runtime
    assert 'rerender:!input.closest(".formula-material-grid")' in source

    for function_name, next_function in (
        ("async function addAlternateSectionMaterialUI", "async function removeAlternateSectionMaterialUI"),
        ("async function addSectionMaterialUI", "async function removeSectionMaterialUI"),
    ):
        dialog_source = source[source.index(function_name) : source.index(next_function, source.index(function_name))]
        for removed_option in ('value="tie_back_qty"', 'value="backpan_lf"', 'value="manual_quantity"'):
            assert removed_option not in dialog_source


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
    assert 'if(page==="bid"||["frames","doors","equipment","borrowed","labor"].includes(page))return RENDER[page]();' in source
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
    assert 'page==="bid"||["frames","doors","equipment","borrowed","labor"].includes(page)' in source
    for contract in (
        "alternateFrameTable", "alternateMaterialTable", "alternateSectionCodePicker",
        'data-alt-grid-add="frames|', "data-alt-section-add", "data-alt-restore",
        "data-alt-frame-material", "data-alt-add-section-material",
        "data-alt-remove-section-material", "changeAlternateMaterialField",
        "bindAlternateScenarioGrids", "pasteAlternateScenarioGrid",
    ):
        assert contract in source
    for field in (
        "square_feet", "perimeter_lf", "caulking_lf", "head_sill_qty",
        "installation_material_ids",
    ):
        assert f'["{field}"' in source
    assert "data-alt-frame-qty-ack" not in source and "toggleAlternateFrameQuantityAcknowledgement" not in source
    assert 'columns=columns.filter(column=>column.key!=="missing_quantity_acknowledged")' in source
    assert '.alternate-frame-grid tbody tr.alt-removed > td > span' in css
    assert '[data-column-key="quantity"]' in css
    assert "min-height: 24px" in css and "height: 24px" in css
    assert "data-alt-frame-output" in source and "refreshAlternateFrameCalculatedView" in source
    alternate_table = source[source.index("function alternateFrameTable"):source.index("function alternateMaterialTableLegacy")]
    assert 'alternateScenarioTable({kind:"frames"' in alternate_table
    shared_table = source[source.index("function alternateScenarioTable"):source.index("function doorScenarioTable")]
    assert 'class="editable-table-shell"' in shared_table
    assert 'class="table-wrap app-table-wrap frame-grid alternate-frame-grid alt-frame-scroll' in shared_table
    assert 'class="data-grid app-data-table"' in shared_table
    assert 'class="data-grid frame-grid alternate-frame-grid"' not in alternate_table
    assert "sharedTableController?.scheduleFocusVisibility(control)" in source
    assert 'control.scrollIntoView({block:"nearest",inline:"nearest"})' not in source
    assert "--frame-mark-width" in css and "--frame-qty-width" in css
    assert ".scenario-frame-workspace .frame-grid td:nth-child(1)" in css
    assert "position: sticky" in css and "var(--calculated)" in css and "var(--input)" in css


def test_frame_square_footage_header_explains_per_frame_rounding_in_plain_language():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    frame = source[source.index("function frameTable") : source.index("function alternateScenarioTable")]
    assert "tooltip:frameSquareFootageTooltip()" in frame
    assert "We calculate one frame's square footage, round it up to a whole square foot, then multiply by Qty." in source
    assert "We calculate the full quantity's square footage, then round the total up to a whole square foot." in source
    assert "Width × height × quantity ÷ 144" not in frame
    assert "function mountFrameSquareFootageConfiguration" in source
    assert 'data-frame-square-footage-method' in source
    assert 'candidate.application_settings.frame_square_footage_method=frameMethod' in source


def test_large_base_frame_tables_use_bounded_windowed_dom_rendering():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    core = Path("app/static/ui-core.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    table = source[source.index("const VIRTUAL_TABLE_ROW_THRESHOLD") : source.index("function tableColumn")]
    frame = source[source.index("function frameTable") : source.index("function materialTable")]
    virtual = source[source.index("function renderVirtualTableWindow") : source.index("function bindFrameColumnResizing")]
    paste = source[source.index("function applyTablePaste") : source.index("let sharedTableController")]
    assert "const VIRTUAL_TABLE_ROW_THRESHOLD=120" in table
    assert "const VIRTUAL_TABLE_CELL_THRESHOLD=720" in table
    assert "const VIRTUAL_TABLE_CELL_BUDGET=720" in table
    assert "function virtualTableSettings" in table
    assert "function virtualTableBodyHtml" in table
    assert "canonicalIndexByRow:new Map" in table
    assert 'data-virtualized="true"' in table
    assert "virtualize:true" in frame
    assert "MWUI.virtualWindowStart" in virtual
    assert "requestAnimationFrame(update)" in virtual
    assert "spec.virtualWindowSize" in virtual
    assert 'focused=body.contains(document.activeElement)' in virtual
    assert "replacement?.focus({preventScroll:true})" in virtual
    assert "spec.virtualized?spec.orderedRows" in paste
    assert "virtualWindowStart" in core
    assert "virtualWindowSize" in core
    assert '[data-edit-table][data-virtualized="true"]' in css
    assert "max-height: min(68vh, 48rem)" in css
    assert "contain-intrinsic-size: auto 48rem" in css
    assert 'event.target.closest("[data-duplicate-frame]")' in source
    assert 'table.closest?.(\'[data-virtualized="true"]\')' in core


def test_all_base_and_alternate_takeoff_tables_share_adaptive_virtualization():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    table = source[source.index("function tableEditor") : source.index("function tableColumn")]
    alternate = source[source.index("function alternateScenarioTable") : source.index("function doorScenarioTable")]
    assert "virtualTableSettings(rows.length,columns.length,options.virtualize)" in table
    assert "requested!==false" in source
    assert "rows*columns>VIRTUAL_TABLE_CELL_THRESHOLD" in source
    assert "virtualTableSettings(ordered.length,columns.length)" in alternate
    assert "virtualTableBodyHtml(spec,virtualStart)" in alternate
    assert 'data-virtual-window-size="${spec.virtualWindowSize}"' in alternate
    assert "MWUI.stableSortRows(models,sortStack,columns" in alternate


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
    assert "position: fixed" in frame_css
    assert "resize: both" in frame_css
    assert "max-height: calc(100vh - var(--frame-expanded-top) - 8px)" in frame_css
    assert 'for(const property of ["--frame-expanded-top","--frame-expanded-left","--frame-expanded-width","--frame-expanded-height","width","height"])' in source
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
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    assert 'caulking_passes:null' in source[source.index("function blankFrameRow"):source.index("function normalizeFrameDimension")]
    missing = source[source.index("function frameMissingQuantity"):source.index("function framePageHead")]
    assert "width_inches" in missing and "height_inches" in missing
    assert "frameRowPopulated" not in missing
    semantics = css[css.index("/* Frame row semantics are independent layers") :]
    calculated = semantics.index("tr > td.calculated")
    modified = semantics.index("tr.alt-modified > td:not(.calculated)")
    added = semantics.index("tr.alt-added > td:not(.calculated)")
    removed = semantics.index("tr.alt-removed > td:not(.calculated)")
    assert calculated < modified < added < removed
    assert "background: var(--table-calculated-bg) !important" in semantics
    assert "tr.zero-quantity-row > td:not(.calculated)" not in semantics
    assert "background-color: #f6edcf !important" in semantics
    assert "background-color: #dcefe4 !important" in semantics
    assert "background-color: var(--ui-error-bg) !important" in semantics
    assert "tr.alt-removed > td:not(.row-action-cell)" in semantics
    assert "tr:is(.zero-quantity-row, .alt-removed)" not in semantics
    assert "text-decoration: line-through !important" in semantics
    assert "background-color: transparent !important" in semantics
    assert "tbody tr:is(:hover, :focus-within) > td:not(.calculated)" in semantics
    assert "tbody tr:is(:hover, :focus-within) > td {" not in semantics
    assert "background-image: linear-gradient(rgba(24, 42, 34, 0.055)" in semantics
    assert "box-shadow: inset 0 1px" not in semantics
    assert "border-color: var(--ui-border-strong) !important" in semantics
    assert "box-shadow: none !important" in semantics
    zero_logic = source[source.index("function frameZeroQuantity"):source.index("function frameMissingQuantity")]
    assert 'String(value).trim()!==""' in zero_logic
    assert "Number(value)===0" in zero_logic
    assert "ZERO_ABSENT_QUANTITY_FIELDS" in source
    assert "normalizeZeroAbsentQuantity" in source
    assert "function previewFrameQuantities" not in source
    assert "function applyFrameRowCalculatedPreview" not in source
    assert "function applyAuthoritativeCalculationBatch" in source
    assert "applyAuthoritativeCalculationBatch(result.project)" in source
    assert "state.timer=setTimeout(()=>save(),0)" in source
    assert "state.timer=setTimeout(()=>save(),250)" not in source
    assert 'if(rowElement)refreshAlternateFrameRowPresentation(rowElement,row)' in source
    assert 'rowElement.classList.toggle("zero-quantity-row",frameZeroQuantity(model.effective))' in source
    assert "data-view-alt-changes" in source
    assert "function openAlternateChangesUI" in source
    assert "function alternateChangeRows" in source
    assert "Changes from Base" in source
    assert ".alternate-change-review-table" in css
    assert "function resetAlternateRecord" in source
    assert "function ensureAlternateRevertActions" in source
    assert "data-alt-reset-record" in source
    assert ".alternate-record-revert" in css
    assert "function alternateFrameValuesEqual" in source
    assert "return Number(value)===Number(base)" in source
    assert 'matchesBase=collection==="frames"?alternateFrameValuesEqual(field,value,base[field])' in source
    assert "function formatAlternateNumericControl" in source
    assert "input.value=formatNumeric(value,category)" in source
    assert 'if(model.status==="Removed")return `<span>${esc(shown)}</span>`' in source
    assert "button.onclick=()=>resetAlternateRecord(spec)" in source
    assert "if(hadOverride)delete bucket.overrides[id]" in source
    assert "if(wasRemoved)bucket.removed=[...removed]" in source
    assert "calculated:projectedRow?.calculated??baseRow.calculated" in source
    assert "function alternateOverrideValue" in source
    assert 'Object.hasOwn(value,"value")&&depth++<8' in source
    assert "function normalizeAlternateFrameOverrides" in source
    assert "normalizeAlternateFrameOverrides(frameBucket)" in source
    assert "target[parts.at(-1)]=alternateOverrideValue(change)" in source
    assert 'value&&typeof value==="object"?JSON.stringify(value)' in source
    popout = css[css.index("/* Expanded text editors float above row semantics") :]
    assert ".frame-text-entry-expanded:hover" in popout
    assert ".frame-text-entry-expanded:focus" in popout
    assert "background-color: #fff !important" in popout
    assert ".alt-value-changed {" not in css
    assert ".material-picker > summary" in css
    assert "liveAddedFrame=(projectedRow,added)=>({...projectedRow,...added,calculated:projectedRow?.calculated})" in source
    assert "function refreshAlternateFrameRowPresentation" in source
    assert 'rerender:!input.closest(".alternate-frame-grid")' in source
    assert "Revert modified Frame section to Base" not in source
    assert ".scenario-section.alt-modified { border-left" not in css
    assert ".scenario-section.alt-added { border-left" not in css
    assert ".scenario-section.alt-removed { border-left" not in css
    assert "tr:hover > td:is(:nth-child(1), :nth-child(2))" not in css
    assert "vertical-align: middle" in css

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
    assert "function visiblePasteRows" in core
    assert "MWUI.visiblePasteRows(canonicalRows,visibleRowIds)" in source
    assert "get(spec.collection).indexOf(row)" in source
    assert "correlationId(\"paste\")" in core
    assert "normalizeExact()" in core and "normalizeExact:true" in source


def test_shared_grid_markup_is_semantic_and_preserves_editable_calculated_distinction():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    editor = source[source.index("function persistedTableRowHtml"):source.index("function addButton")]
    calculated = source[source.index("function calculatedTableCell"):source.index("function tableEditor")]
    assert '<table class="data-grid app-data-table"' in editor
    assert '<th scope="col"' in editor
    assert "data-column-key" in editor
    assert "data-output-path" in source
    assert "calculatedTableCell" in editor and "<output " in calculated
    assert 'aria-label="${esc(column.label||field)}"' in source
    assert 'readonly aria-readonly="true"' in source
    assert 'class="trailing-row"' in source


def test_table_calculations_render_missing_values_as_empty_cells():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    calculated = source[source.index("const calculatedCellDisplay") : source.index("const MATERIAL_UNIT_LABELS")]
    draft = source[source.index("function draftRowHtml") : source.index("function tableSortStateKey")]
    shared_cell = source[source.index("function calculatedTableCell") : source.index("function tableEditor")]
    alternate_cell = source[source.index("function alternateCollectionCell") : source.index("function alternateDoorCell")]
    reconciliation = source[source.index("function reconcileCalculatedView") : source.index("function applyAuthoritativeCalculationBatch")]
    frame_refresh = source[source.index("function refreshFrameCalculatedView") : source.index("function refreshOpenInstallationMaterialDialog")]
    alternate_frame_refresh = source[source.index("function refreshAlternateFrameCalculatedView") : source.index("function alternateFrameChangeSummary")]

    assert 'String(value).trim()==="—"?"":value' in calculated
    assert 'aria-label="Calculated after entry"></span>' in draft
    assert 'Calculated after entry">—</span>' not in draft
    assert "calculatedCellDisplay(column.calc(row,index))" in shared_cell
    assert "calculatedCellDisplay(column.calc(row,model.projectionIndex))" in alternate_cell
    assert 'el.closest("table")?calculatedCellDisplay(display):display' in reconciliation
    assert "calculatedCellDisplay(number(value,numericCategory(key)))" in frame_refresh
    assert "calculatedCellDisplay(number(row.effective.calculated?.[key],category))" in alternate_frame_refresh
    assert 'valid&&Number.isFinite(rate)?money(quantity*rate):""' in source
    assert 'const money=(v,category="currency")=>formatNumeric' in source


def test_shared_visual_system_unifies_live_tables_and_frame_variants():
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    visual = css[css.index("/* Cohesive estimating workspace presentation."):]
    for token in (
        "--ui-canvas: #f5f7f6",
        "--ui-sidebar: #f1f5f2",
        "--ui-brand: #295b4b",
        "--ui-border: #dae3df",
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
    assert "width: 100%" in containment
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
    assert "activeScenarioTabByWorkspace:new Map()" in source
    assert 'role="tablist"' in source and 'role="tab"' in source
    assert 'data-scenario-tab-kind' in source and 'data-scenario-tab-scenario' in source
    assert "frames:renderTabbedFrames" in source
    assert ".frame-section-tabs" in css
    assert ".frame-section-tabs::-webkit-scrollbar { display: none; width: 0; height: 0; }" in css
    assert "overflow-y: hidden;\n  border-bottom: 1px solid var(--ui-border);\n  scrollbar-width: none;" in css
    assert ".frame-section-tab.is-active" in css
    assert 'td > :is(input:not([type="checkbox"]), select, textarea)' in css
    assert "line-height: 18px" in css
    assert "td > :is(output, span)" in css
    assert "function alternateNumberLabel" in source
    assert "function alternateTabs()" in source
    tabbed = source[source.index("function renderTabbedFrames") : source.index("function insertAlternateTabsAfterHeader")]
    assert "scenarioSubtabs({kind:\"frames\"" in tabbed
    assert "scenarioTabbedWorkspace({kind:\"frames\"" in tabbed
    assert "alternateTabs(true)" in source[source.index("function scenarioTabbedWorkspace"):source.index("function quoteSelection")]
    assert 'class="frame-section-add-tab"' in tabbed
    assert "＋ New section</button>" in tabbed
    assert "description=" not in tabbed
    assert "<span>${esc(description)}</span>" not in tabbed
    assert ".frame-section-add-tab" in css
    assert 'workspace-toolbar scenario-toolbar' not in tabbed
    assert '"Base takeoff"' not in tabbed
    summary = source[source.index("function frameTabbedSectionHtml") : source.index("function renderTabbedFrames")]
    assert 'scenarioScheduleSection({kind:"frames"' in summary
    assert ".frame-header-commercial .section-metric.primary strong { color: var(--ui-text); }" in css
    shared_section = source[source.index("function scenarioScheduleSection"):source.index("function scenarioTabbedWorkspace")]
    assert '<header class="module-header frame-schedule-summary' in shared_section
    assert '<h2 title="${esc(title)}"' in shared_section
    assert 'class="frame-section-title-row"' in shared_section
    assert "data-toggle-frame" not in summary
    assert "collapsedFrameSections" not in summary
    assert 'status==="Removed"?""' in summary
    assert 'class="frame-lines-heading frame-lines-actions-only"' not in summary
    assert 'data-configure-installation-materials="${esc(materialSpec)}"' in summary
    assert "Configure installation materials" in summary
    assert "alternateMaterialTableWithActions(model):materialTable" not in summary
    assert "data-toggle-materials" not in summary
    assert "<h3>Frame lines</h3>" not in summary
    assert "Tab across, Enter down" not in summary
    assert "Inherited values remain linked" not in summary
    assert "frameTabbedSectionHtml(activeModel,activeIndex,alt)" in tabbed
    assert '<div class="module-actions">' not in summary
    assert 'iconButton("×"' not in summary
    assert 'data-alt-restore="takeoff_sections|' in summary
    summary_css = css[css.index("/* A Frame Spec Section tab already owns schedule navigation.") :]
    assert ".scenario-section > .frame-schedule-summary" in summary_css
    assert "grid-template-columns: minmax(240px, 1fr) 72px 108px 88px 100px" in summary_css
    assert ".frame-schedule-summary .section-history.vertical .history-five-band.compact { width: 68px; }" in summary_css
    assert ".frame-section-description h2" in summary_css
    assert ".frame-section-title-row .compact-frame-add" in summary_css
    assert ".frame-section-title-row .configure-installation-materials" in summary_css
    assert "background: transparent" in summary_css
    assert ".scenario-section > .module-body" in summary_css
    assert 'body=status==="Removed"?"":`<div class="module-body">${alt?alternateFrameTable(model):frameTable(section,model.baseIndex)}</div>`' in summary
    assert "dialog.installation-material-dialog" in css
    assert 'button[value="cancel"] { display: none; }' in css
    assert 'event.target.matches(".formula-material-grid input, .formula-material-grid select")' in source
    assert "event.preventDefault();event.stopPropagation()" in source


def test_alternate_route_refresh_totals_band_and_state_rail_contracts():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    assert 'alternateId:params.get("alternate")' in source
    assert '?alternate=${encodeURIComponent(alternateId)}' in source
    assert 'openProject(route.projectId,false,route.page,"none",route.alternateId)' in source
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
    assert "function syncFrameTotalAlignment" in source
    assert 'total.classList.contains("numeric")?"right":contentStyle.textAlign' in source
    assert 'total.style.justifyContent=alignment==="right"?"flex-end"' in source
    assert "pixels(contentStyle.paddingRight)+pixels(contentStyle.borderRightWidth)" in source
    assert "syncFrameTotalAlignment(grid,rail,headers)" in source
    assert 'grid.matches(".table-wrap")?grid.querySelector(":scope > .frame-totals-rail")' in source
    assert "grid-template-columns:" in totals_css
    assert ".frame-totals-rail > span:nth-child(2)" in totals_css
    assert "background: var(--ui-canvas)" in totals_css
    assert "background: var(--surface)" not in totals_css
    assert "background: transparent" not in totals_css
    assert "background-clip: border-box" in totals_css
    assert "margin-top: 0" in totals_css
    assert "padding-top: 5px" in totals_css
    assert "function bindTransientFrameScrollbars" in source
    assert 'wrap.classList.add("is-horizontal-scrolling")' in source
    assert 'wrap.classList.toggle("is-at-horizontal-end",wrap.scrollWidth-wrap.clientWidth-wrap.scrollLeft<=1)' in source
    assert 'wrap.classList.toggle("is-scrollbar-hovered",nearScrollbar)' in source
    assert ".is-horizontal-scrolling::-webkit-scrollbar-thumb" in css
    assert ".is-scrollbar-hovered::-webkit-scrollbar-thumb" in css
    assert ".table-wrap::-webkit-scrollbar { height: 0; background: transparent; }" in css
    assert ".table-wrap.is-scrollbar-hovered::-webkit-scrollbar { height: 7px; background: var(--ui-canvas); }" in css
    assert "scrollbar-width: none" in css
    assert ".table-wrap::-webkit-scrollbar-thumb:hover" in css
    assert "scrollbar-color: var(--ui-border-strong) var(--ui-canvas)" in css
    assert "height: 7px; background: var(--ui-canvas)" in css
    assert "border: 1px solid var(--ui-canvas)" in css
    assert "background-clip: padding-box" in css
    assert ".frame-table .table-wrap:hover::-webkit-scrollbar-thumb" not in css
    assert ":is(table.frame-grid, .frame-grid > table)" in css
    assert ":is(table.frame-grid, .frame-grid > table) tr > :first-child { border-left: 1px solid var(--ui-border); }" in css
    assert ".frame-table .table-wrap" in css and "border: 0 !important" in css
    assert '.querySelectorAll(".scenario-frame-workspace .frame-table .table-wrap")' in source
    assert ".frame-totals-rail > span:first-child { border-left: 0 !important" in css
    assert ".frame-grid tbody tr:last-child td:first-child { border-bottom-left-radius: 5px; }" in css
    assert "border-right: 1px solid var(--ui-border);\n  border-left: 1px solid var(--ui-border);" in css
    assert ".table-wrap.is-at-horizontal-end .frame-grid :is(th, td):nth-child(18) { border-left: 0; }" in css
    assert ".frame-grid tbody :is(th, td):nth-child(18) { background: var(--ui-surface); }" in css
    assert "All editable cells share one surface" in css
    assert ".frame-grid tbody td:not(.calculated, .row-action-cell)" in css
    assert ".frame-grid tbody td:is(:nth-child(1), :nth-child(2)) { isolation: isolate; }" in css
    assert "z-index: calc(var(--z-sticky-cell) + 7)" in css
    assert "background-clip: border-box" in css
    assert ".frame-grid tbody .row-action-cell" in css
    assert ".scenario-section:is(.alt-modified, .alt-added, .alt-removed)" not in css


def test_alternates_page_uses_plain_language_side_by_side_comparison_without_internal_record_ids():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    backend = Path("app/alternates.py").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    comparison = source[source.index("function alternateRecordLabel") : source.index("function alternateBaseRows")]
    workspace = source[source.index("function renderAlternatesWorkspace") : source.index("function alternateSummary")]

    assert "function alternateComparisonHtml" in comparison
    assert '<table class="data-grid alternate-diff-table alternate-matrix-table"' in comparison
    assert '<th scope="col">Cost Item / Location / Field</th><th scope="col">Base</th>' in comparison
    assert "alternate-line-number" not in comparison
    assert "Open cost item" not in comparison
    assert 'status:"Changed"' in comparison
    assert 'return record.code?String(record.code):ALT_CHANGE_AREAS[collection]||"Record"' in comparison
    assert 'return "Travel allowance"' in comparison
    assert "alternateComparisonMatrixHtml(all)" in workspace
    assert 'head("Alternates")+alternateTabs()' not in workspace
    assert "Base and Alternates" in workspace
    assert 'row.get("id")' not in backend[backend.index("def _record_label") : backend.index("def scope_of_change")]
    assert 'return "Travel allowance"' in backend
    assert ".alternate-diff-table" in css
    assert ".alternate-diff-table th:first-child { width:38%; }" not in css
    assert 'const ALT_CHANGE_ORDER=["quotes","takeoff_sections","frames","doors","equipment","borrowed_lites","labor_estimates","travel_estimates","line_markup_overrides"]' in source
    assert 'return rows.sort(' in comparison
    assert "function alternateChangeTargetAttributes" in comparison
    assert "data-alt-change-link" in comparison
    assert "function openAlternateChangeTarget" in comparison
    assert 'line_markup_overrides:"bid"' in comparison
    assert 'setScenarioActiveTab("frames"' in comparison
    assert 'setScenarioActiveTab(page' in comparison
    assert 'bindAlternateChangeLinks(dialog)' in comparison
    assert "bindAlternateChangeLinks();" in source
    assert ".alternate-diff-table tr.alt-changed" not in css
    assert "function alternateMatrixRows" in comparison
    assert "function alternateMatrixValue" in comparison
    assert "function alternateMatrixRenderedRows" in comparison
    assert "function alternateComparisonMatrixHtml" in comparison
    assert 'data-alt-change-alternate="${esc(scenario)}"' in comparison
    assert '"diff-old"' in comparison and '"diff-new"' in comparison
    assert '"diff-modified"' in comparison
    assert "const ALT_SYSTEM_FIELD_PATTERN=" in source
    assert "function alternateKnownEditableDefinitions" in source
    assert "doorTableColumns().filter(column=>!column.calc)" in source
    assert "equipmentTableColumns().filter(column=>!column.calc)" in source
    assert "borrowedTableColumns().filter(column=>!column.calc)" in source
    assert "laborTableColumns().filter(column=>!column.calc)" in source
    assert "function alternateEditableDefinitions" in source
    assert "function alternateEstimatorFacingField" in source
    assert "function alternateValuesEquivalent" in source
    assert "function comprehensiveAlternateChangeRows" in comparison
    assert "function alternateInstallationMaterialChangeRows" in comparison
    assert "function alternateMaterialOverrideChangeRows" in comparison
    assert "alternateEstimatorFacingField(field,alternateRaw)" in comparison
    assert 'if(typeof value==="object")return""' in source
    assert "data-show-unchanged-alternates" in workspace
    assert "showUnchangedAlternates" in source
    assert "function alternateFinancialSummary" in source
    assert "selling_value_delta" in source
    assert ".alternate-matrix-table { font-size:.78rem; }" in css
    assert "min-width:6.5rem" in css
    assert ".alternate-matrix-table .diff-old" in css
    assert ".alternate-matrix-table .diff-new" in css
    assert ".alternate-matrix-table .diff-modified" in css
    assert ".alternate-matrix-table .diff-zero" in css
    assert ".diff-modified .alternate-diff-token" in css
    assert "color-mix(in srgb,var(--ui-warning) 28%,transparent)" in css
    assert ".diff-new .alternate-diff-token" not in css
    assert ".diff-old .alternate-diff-token" not in css
    assert ".alternate-matrix-table tbody tr:is(:hover,:focus-within) > td.diff-old" in css
    assert ".alternate-matrix-table tbody tr:is(:hover,:focus-within) > td.diff-new" in css
    assert ".alternate-matrix-table tbody tr:is(:hover,:focus-within) > td.diff-modified" in css
    assert ".alternate-matrix-table tbody tr:is(:hover,:focus-within) > td.diff-zero" in css
    assert "var(--ui-warning-bg)" in css
    assert "counter-reset:alternate-diff-line" not in css
    assert 'function alternateMatrixIdentityCells(row)' in comparison
    assert "function alternateSignedDelta" not in comparison
    assert "function alternateChangeOperation" in comparison
    assert 'change.status==="Added"' in comparison
    assert 'change.status==="Removed"' in comparison
    assert "return alternateDiffDisplay(change.alternate)" in comparison
    assert "comparisonNumericDelta" not in comparison
    assert 'if(!change)return"<td></td>"' in comparison
    assert 'baseCell=row.baseExists===false?' in comparison
    assert 'baseValue=row.base||""' in comparison
    assert "—" not in comparison
    assert 'if(change.status==="Removed")return\'<td class="diff-old"></td>\'' in comparison
    assert "function alternateInlineDiff" in comparison
    assert "MWUI.comparisonChangedSegment(baseValue,alternateValue)" in comparison
    assert 'options=change.status==="Added"?{}:{baseValue:change.base}' in comparison
    assert "{highlight:true}" not in comparison
    assert 'oldRow=' not in comparison and 'newRow=' not in comparison
    assert 'if(!changed[index])return"<td></td>"' in comparison
    assert 'columnCount=alternates.length+2' in comparison
    assert "function alternateWholeItemGroups" in comparison
    assert "function alternateWholeItemKey" in comparison
    assert "function alternateOutlineButton" in comparison
    assert "function alternateLineMatchesRow" in comparison
    assert "function alternateGroupPriceDelta" in comparison
    assert "function alternateGroupBaseTotal" in comparison
    assert "function alternatePriceImpact" in comparison
    assert 'amount<0?`−${money(Math.abs(amount))}`:money(Math.abs(amount))' in comparison
    assert 'tone=impact>0?"diff-new":impact<0?"diff-old":"diff-zero"' in comparison
    assert 'operation==="Added"?"diff-new"' not in comparison
    assert 'tone=impact>0?"diff-new":impact<0?"diff-old":"diff-zero"' in comparison[comparison.index("function alternateOutlineRow"):comparison.index("function alternateFieldCountDetail")]
    assert "alt.calculated?.effective_estimate?.lines" in comparison
    assert 'class="alternate-price-impact' in comparison
    assert 'class="alternate-price-impact alternate-base-total"' in comparison
    assert "baseTotal:alternateGroupBaseTotal(areaRows)" in comparison
    assert "baseTotal:alternateGroupBaseTotal(location.rows,{item:true})" in comparison
    assert 'operationLabel=' not in comparison
    assert 'if(change.status==="Removed")return""' in comparison
    assert 'return\'<td class="diff-old"></td>\'' in comparison
    assert "function alternateRowsState" in comparison
    assert "function alternateOperationImpact" not in comparison
    assert "states:alternates.map(alt=>alternateRowsState(areaRows,alt))" in comparison
    assert 'item:String(record?.mark||"Frame line").trim()' in comparison
    assert 'kind:"item"' in comparison
    assert "function alternateFieldEntryOrder" in source
    assert "function alternateComparisonRowSort" in source
    assert "rows.sort(alternateComparisonRowSort)" in comparison
    assert ".alternate-item-row .alternate-outline-toggle" in css
    assert ".alternate-item-field-row .alternate-field-outline" in css
    assert '"Entire item added"' not in comparison
    assert '"Entire item removed"' not in comparison
    assert "box-shadow:inset 3px 0" not in css[css.index(".alternate-matrix-table .diff-old") : css.index(".alternate-matrix-table .alternate-base-absent")]
    assert ".alternate-matrix-table .diff-new { background:var(--ui-success-bg); color:var(--ui-success); }" in css
    assert "> :not(.diff-old):not(.diff-new):not(.diff-modified):not(.diff-zero)" in css
    assert "tr.alternate-logical-change:nth-child(even)" in css
    assert "tr.alt-unchanged:nth-child(even)" in css
    assert "tbody tr > :nth-child(2):not(.diff-old):not(.diff-new):not(.diff-modified):not(.diff-zero)" in css
    assert "background:color-mix(in srgb,var(--ui-surface-muted) 76%,var(--ui-surface))" in css
    assert ".alternate-matrix-table thead :nth-child(2)" in css
    assert "border-right-color:var(--table-sticky-divider)" in css
    assert "border-left:1px solid var(--ui-border-strong)" not in css[css.index(".alternate-matrix-table tbody tr > :nth-child(2)"):css.index(".alternate-location-row .alternate-outline-toggle")]
    assert "function alternateAssignedName" in source
    assert "function alternateNameTooltip" in source
    assert '<span${alternateNameTooltip(alt)}>${esc(alternateLabel(alt))}</span>' in comparison
    assert 'class="alternate-field-outline"' in comparison
    assert 'data-alt-outline-toggle="${esc(key)}"' in comparison
    assert "expandedAlternateOutline:new Set()" in source
    assert "function alternateOutlineExpanded" in comparison
    assert "alternateOutlineExpanded(areaKey)" in comparison
    assert "alternateOutlineExpanded(locationKey)" in comparison
    assert "alternateOutlineExpanded(itemKey)" in comparison
    assert "knownAlternateOutline:new Set()" in source
    assert "state.ui.knownAlternateOutline.clear()" in source
    assert "state.ui.showUnchangedAlternates=false" in source
    assert "expanded:areaExpanded" in comparison
    assert "expanded:locationExpanded,hidden:!areaExpanded" in comparison
    assert 'hidden?"hidden ":""' in comparison
    assert '!areaExpanded||!locationExpanded||!itemExpanded' in comparison
    assert "state.ui.expandedAlternateOutline.add(key)" in source
    assert "state.ui.expandedAlternateOutline.delete(key)" in source
    assert "[data-alt-outline-toggle]" in source
    assert 'data-alt-outline-ancestors="${esc(ancestors)}"' in comparison
    assert '`${areaKey} ${locationKey} ${itemKey}`' in comparison
    assert 'style="width:max(100%,${tableWidth}rem)"' in comparison
    assert ".alternate-outline-toggle small::before" in css
    assert "flex-direction:column" not in css[css.index(".alternate-outline-toggle") : css.index(".alternate-source-highlight")]
    assert "Formula Value" not in comparison
    assert 'operand_override:"Formula Input"' in comparison
    assert "function alternateInferredDefinition" in source
    assert "function alternateComparisonRow" in source
    assert "function alternateFrameSectionLabel" in comparison
    assert 'itemKey:`frame-${record?.id||record?.mark||"unknown"}`' in comparison
    assert 'record:String(record?.code||"No Cost Code")' in comparison
    assert 'itemKey:`quote-${record?.id||label}`' in comparison
    assert 'item:`Installation Material · ${material?.name||"Material"}`' in comparison
    assert 'const recordKey=String(row.recordKey||row.record)' in comparison
    assert 'const groupKey=String(row.itemKey||row.item)' in comparison
    assert 'area:"Frame sections",collection:"takeoff_sections"' in comparison
    assert 'presentation=alternateFieldPresentation(collection,record,definition.key,definition,area,label)' in comparison
    assert 'typeof value!=="object"' in source
    assert 'typeof value!=="object"||Array.isArray(value)' not in source
    assert "function alternateBaseMaterialInventoryRows" in comparison
    assert "function alternateBaseMarkupInventoryRows" in comparison
    assert 'for(const record of records)for(const definition of definitions)' in comparison
    assert 'if(definition.nested)continue' in comparison
    assert 'baseRaw,alternateRaw:null,status:"Inherited"' in comparison
    assert 'return change?{value:alternateChangeOperation(change)' in comparison
    assert 'state.config?.hardware_groups' in source
    assert 'data-tooltip="${esc(tooltip)}"' in comparison
    assert "function alternateMaterialSourceElement" in comparison
    assert "materialId=button.dataset.altChangeMaterial" in comparison
    assert ".alternate-source-highlight" in css
    assert "Summary colors show price direction; detail colors show the input operation." in workspace
    assert ".alternate-price-impact { color:var(--ui-text); font-variant-numeric:tabular-nums; text-align:left !important; }" in css
    assert ".alternate-price-impact .alternate-matrix-value-link { font-weight:600; text-align:left; }" in css


def test_working_bid_ancestry_banner_is_not_rendered():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    assert "Current Working Bid · Based on" not in source
    context = source[source.index("function updateProposalContext") : source.index("async function openHistoricalProposal")]
    assert 'box.hidden=true' in context
    assert 'className="proposal-context working-branch"' not in context


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


def test_add_row_persists_multiple_blanks_and_blank_keyboard_rows_do_not_disappear_on_blur():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    add_blank = source[source.index("function addBlankTableRow") : source.index("function handleManualAddressChange")]
    assert "promoteTableDraft" in add_blank
    assert 'uuid("add-row")' in add_blank
    assert "state.ui.activeDraftTables.delete(tableId)" in add_blank
    assert "state.ui.drafts.delete(tableId)" in add_blank
    assert 'if(add)addBlankTableRow(add.dataset.tableAddRow)' in source
    assert "dismissEmptyFrameDraft" not in source
    assert ">Draft<" not in source


def test_fully_empty_base_rows_delete_without_confirmation_and_alt_blank_deletion_stays_direct():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    empty_check = source[source.index("function tableRecordIsEmpty") : source.index("async function deleteRow")]
    delete_row = source[source.index("async function deleteRow") : source.index("function csiSearch")]
    remove_alt = source[source.index("function removeAlternateAdded") : source.index("function setNestedValue")]
    assert "candidate.collection===path" in empty_check
    assert "JSON.stringify(value)===JSON.stringify(defaultValue)" in empty_check
    assert 'value===null||value===undefined||value===""||value===false' in empty_check
    assert '!tableRecordIsEmpty(path,prior)&&!confirm(' in delete_row
    assert "confirm(" not in remove_alt


def test_doors_use_one_full_field_table_definition_across_base_and_alternates():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    columns = source[source.index("function doorTableColumns") : source.index("function doorScenarioModels")]
    scenario = source[source.index("function doorScenarioModels") : source.index("function renderEquipment")]
    for key in (
        "code", "door_number", "mark", "leaf_quantity", "width_inches",
        "height_inches", "type", "material", "finish", "description",
        "glass", "style", "rails", "hardware_group_id", "fire_rating", "notes",
    ):
        assert f'key:"{key}"' in columns
    assert "function alternateDoorCell" in scenario
    assert "function doorScenarioTable" in scenario
    assert 'tableEditor("doors",columns' in scenario
    assert 'alternateScenarioTable({kind:"doors"' in scenario
    assert 'function groupedScenarioColumns(columns,groupKey="code")' in source
    assert 'columns.filter(column=>column.key!==groupKey)' in source
    assert source.count("groupedScenarioColumns(doorTableColumns())") == 2
    assert 'data-alt-added="${esc(collection)}|' in scenario
    assert 'data-alt-field="${esc(collection)}|' in scenario
    assert 'class="data-grid app-data-table"' in scenario
    assert 'function doorCostCodeTabs' in scenario
    assert 'scenarioCostCodeTabs("doors",models,alt)' in scenario
    assert 'data-scenario-cost-code-edit="${esc(kind)}"' in source
    assert 'data-alt-grid-add="doors|' in scenario
    assert 'rowsProvider:()=>(state.doc.doors||[]).filter' in scenario
    assert 'defaults:{...defaultRowFor("doors"),code:activeCode}' in scenario
    assert 'activeScenarioTabByWorkspace:new Map()' in source
    assert 'setScenarioActiveTab(kind,scenarioKey,code)' in source
    assert 'function addAlternateScenarioGridRow' in source
    assert '["frames","doors","equipment","borrowed","labor"].includes(page)' in source
    assert 'function renderTabbedDoors()' in scenario
    assert 'scenarioTabbedWorkspace({kind:"doors"' in scenario
    assert 'scenarioScheduleSection({kind:"doors"' in scenario
    assert 'class="module-body"' in scenario
    assert 'doors:renderTabbedDoors' in source
    assert 'Configured hardware groups' not in scenario
    assert "function bindAlternateScenarioGrids" in source
    assert "function pasteAlternateScenarioGrid" in source
    assert 'bindAlternateScenarioGrids();' in source
    assert '.scenario-door-workspace .scenario-section' not in css
    assert 'class="frame-section-tab-item ${active?"is-active":""}' in source
    assert '<small>${count}</small>' not in scenario
    assert ".frame-section-tabs" in css
    assert ".scenario-door-workspace .door-cost-code-tabs" not in css
    assert "Door and hardware records preserve handoff detail." not in source
    assert "calc:" not in columns


def test_grouped_door_tables_hide_cost_code_without_changing_door_data_or_inheritance():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    schema = source[source.index("function doorTableColumns") : source.index("function doorScenarioModels")]
    table = source[source.index("function doorScenarioTable") : source.index("function doorCostCodeTabs")]
    alternate_grid = source[source.index("function alternateScenarioGridDefinition") : source.index("function focusAlternateScenarioGridCell")]
    assert 'key:"code",label:"Cost Code"' in schema
    assert "const columns=groupedScenarioColumns(doorTableColumns())" in table
    assert 'columns=kind==="doors"?groupedScenarioColumns(doorTableColumns()):scenarioGroupColumns(kind)' in alternate_grid
    assert 'defaults:{...defaultRowFor("doors"),code:activeCode}' in table
    assert 'const row={...scenarioGroupDefaults(kind,group),id:uuid(config.prefix)}' in alternate_grid


def test_equipment_borrowed_and_labor_use_the_shared_frame_scenario_workspace():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    for kind in ("equipment", "borrowed", "labor"):
        assert f'{kind}:{{collection:' in source
        assert f'classes:`scenario-${{kind}}-workspace`' in source or kind == "labor" and 'classes:"scenario-labor-workspace"' in source
        assert f'kind:"{kind}"' in source or kind in ('equipment', 'borrowed')
    assert 'function renderEquipment(){return renderCostCodeScenarioWorkspace("equipment")}' in source
    assert 'function renderBorrowed(){return renderCostCodeScenarioWorkspace("borrowed")}' in source
    assert 'function renderLabor()' in source
    for helper in (
        "scenarioSubtabs", "scenarioScheduleSection", "scenarioTabbedWorkspace",
        "scenarioCollectionModels", "scenarioCollectionTable", "alternateScenarioTable",
        "alternateScenarioGridDefinition", "bindAlternateScenarioGrids",
    ):
        assert helper in source
    assert '["doors","equipment","borrowed","labor"].includes(kind)' in source
    assert 'scenarioSectionMeta(models,alt,config.singular,config.plural)' in source
    assert 'secondary:scenarioSectionMeta(models,alt,"labor row","labor rows")' in source


def test_equipment_and_borrowed_group_by_cost_code_without_repeating_the_group_column():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    equipment = source[source.index("function equipmentTableColumns") : source.index("function borrowedTableColumns")]
    borrowed = source[source.index("function borrowedTableColumns") : source.index("function laborTableColumns")]
    assert 'key:"code",label:"Cost Code"' in equipment
    assert 'key:"calculated_cost",label:"Extended cost"' in equipment
    assert 'key:"code",label:"Cost Code"' in borrowed
    assert 'key:"calculated_square_feet",label:"Calculated ft²"' in borrowed
    assert 'if(kind==="equipment")return groupedScenarioColumns(equipmentTableColumns())' in source
    assert 'if(kind==="borrowed")return groupedScenarioColumns(borrowedTableColumns())' in source
    assert 'scenarioCostCodeTabs(kind,allModels,alt)' in source
    assert 'defaults.code=group||""' in source
    assert 'data-scenario-cost-code-edit="${esc(kind)}"' in source


def test_takeoff_tables_share_semantic_column_sizing_and_one_action_rail():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    layout = source[source.index("const WORKSHEET_COLUMN_WIDTHS") : source.index("function defaultRowFor")]
    editor = source[source.index("function tableEditor") : source.index("function tableColumn")]
    alternate = source[source.index("function alternateScenarioTable") : source.index("function doorScenarioTable")]

    for key in ("description", "quantity", "duration", "duration_unit", "delivery_direction", "rate", "delivery", "calculated_cost", "taxable", "notes"):
        assert f"{key}:" in layout
    assert "function worksheetColumnStyle" in layout
    assert "function worksheetTableStyle" in layout
    assert "function worksheetColGroup" in layout
    assert "function worksheetActionStyle" in layout
    assert "data-unified-worksheet-table" in layout
    assert "worksheetColumnStyle(c)" in editor
    assert "worksheetTableStyle(columns,actionWidth)" in editor
    assert "worksheetColGroup(columns,actionWidth)" in editor
    assert "worksheetActionStyle(columns,actionWidth)" in editor
    assert 'class="row-action-cell" data-draft-actions' in source
    assert "worksheetColumnStyle(column)" in alternate
    assert "worksheetTableStyle(columns)" in alternate
    assert "worksheetActionStyle(columns)" in alternate
    assert source.count('actionLabel:"Actions"') >= 2
    assert "table[data-unified-worksheet-table] :is(.row-actions-heading, .row-action-cell)" in css
    assert "overflow: hidden" in css


def test_equipment_has_one_locked_110000_subtab_while_alternate_scenarios_remain_available():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    config = source[source.index("const SCENARIO_COLLECTION_CONFIG") : source.index("const SCENARIO_PROJECTION_KEYS")]
    tabs = source[source.index("function scenarioCostCodeTabs") : source.index("function quoteSelection")]
    editor = source[source.index("async function editScenarioCostCodeUI") : source.index("async function addFrameCostCodeUI")]

    assert 'equipment:{collection:"equipment"' in config
    assert 'fixedTabCodes:["11 00 00"]' in config
    assert "fixedCodes=config.fixedTabCodes" in tabs
    assert 'model.status==="Removed"' in tabs
    assert "emptyScenarioSections" in tabs
    assert 'data-scenario-section-add="${esc(kind)}"' in tabs
    assert 'editAction:(item,label)=>`<button type="button" class="frame-section-tab-edit"' in tabs
    assert '${fixedCodes?"Edit":"Change"}' in tabs
    assert "if(!config)return" in editor
    assert "fixed=Boolean(config.fixedTabCodes)" in editor
    assert "lockCode:fixed" in editor
    assert 'confirmLabel:fixed?"Done":' in editor
    assert 'scenarioCostCodeTabs(kind,allModels,alt)' in source
    assert "alternateTabs(true)" in source[source.index("function scenarioTabbedWorkspace") : source.index("const SCENARIO_COLLECTION_CONFIG")]
    assert 'data-alt-grid-add="${kind}|${esc(activeCode)}"' in source


def test_equipment_rows_select_controlled_rate_descriptions_and_fill_rate_and_delivery():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    equipment = source[source.index("function equipmentRateRecords") : source.index("function borrowedTableColumns")]
    columns = equipment[equipment.index("function equipmentTableColumns") :]

    assert "state.config?.equipment_rates||[]" in equipment
    assert 'key:"description",label:"Equipment",type:"select",values:equipmentRateOptions(),controlled:"equipment_rate"' in columns
    assert columns.index('key:"duration_unit"') < columns.index('key:"delivery_direction"') < columns.index('key:"rate"') < columns.index('key:"delivery"')
    assert 'values:[["two_way","Two-way"],["one_way","One-way"]]' in columns
    assert 'delivery_direction:"two_way"' in source
    assert 'equipment:{quantity:null,duration:null,duration_unit:null,delivery_direction:"two_way"' in source
    assert 'const unit=String(row.duration_unit||"").trim().toLowerCase()' in equipment
    assert 'function equipmentDefaultDurationUnit(description)' in equipment
    assert 'defaultsUnit=trigger==="description"&&!preserveUnit' in equipment
    assert 'effective=defaultsUnit?{...row,duration_unit:defaultUnit}:row' in equipment
    assert 'if(defaultsUnit)updates.duration_unit=defaultUnit' in equipment
    assert 'for(const field of ["duration_unit","delivery_direction","rate","delivery"])' in equipment
    assert 'deliveryKey=direction==="one_way"?"delivery_one_way":"delivery"' in equipment
    assert 'sourceUnit==="month"&&unit==="day"' in equipment
    assert "Number(reference.base_rate)/30" in equipment
    assert "may not be accurate" in equipment
    assert "Contact ${vendor} for verification" in equipment
    assert "send new rates to the Systems Administrator" in equipment
    assert "equipment-rate-warning" in equipment
    assert 'spec?.collection==="equipment"&&["description","duration_unit","delivery_direction","rate"].includes(field)' in source
    assert 'kind==="equipment"&&["description","duration_unit","delivery_direction"].includes(column.key)' in source


def test_equipment_rate_autofill_uses_shared_base_draft_paste_and_alternate_paths():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    assert 'if(spec.collection==="equipment"&&row.description)Object.assign(row,equipmentRateUpdates(row,"description"))' in source
    assert 'spec.collection==="equipment"&&items.some(item=>' in source
    assert 'if(items.some(item=>item.field==="rate"))delete updates.rate' in source
    assert 'if(items.some(item=>item.field==="delivery"))delete updates.delivery' in source
    assert 'preserveUnit:hasDescription&&hasUnit' in source
    assert 'if(collection==="equipment"&&["description","duration_unit","delivery_direction","rate"].includes(field))' in source
    assert 'column.after?.(model.effective,model.projectionIndex)' in source
    assert 'column.after?.(row,actualIndex)' in source
    assert '.equipment-rate-warning' in css


def test_equipment_rate_warning_distinguishes_calculated_and_manual_rates():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    equipment = source[source.index("function equipmentRateValuesEqual") : source.index("function equipmentTableColumns")]
    commit = source[source.index("function commitTableCell") : source.index("function promoteTableDraft")]
    alternate = source[source.index("function changeAlternateField") : source.index("function setAlternateRemoved")]

    assert "function equipmentRateValuesEqual(value,expected)" in equipment
    assert "manual=hasEntered&&!equipmentRateValuesEqual(entered,resolved.rate)" in equipment
    assert 'kind:"manual",label:"Manual rate"' in equipment
    assert 'kind:"calculated",label:"Calculated rate"' in equipment
    assert "This manually entered Equipment rate" in equipment
    assert "Send the verified rate to the Systems Administrator to update global Rates." in equipment
    assert 'data-equipment-rate-warning="${esc(warning.kind)}"' in equipment
    assert '["description","duration_unit","delivery_direction","rate"].includes(field)' in commit
    assert 'if(field!=="rate")setEquipmentRowUpdates' in commit
    assert alternate.count('["description","duration_unit","delivery_direction","rate"].includes(field)') >= 2
    assert 'if(field!=="rate")for(const [updateField,updateValue]' in alternate
    assert 'if(field!=="rate")Object.assign(row,equipmentRateUpdates(row,field))' in alternate


def test_labor_has_only_fixed_type_tabs_and_keeps_cost_code_as_first_table_column():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    columns = source[source.index("function laborShiftDisplay") : source.index("const LABOR_TYPES")]
    renderer = source[source.index("function renderLabor()") : source.index("function historyTooltip")]
    assert 'const LABOR_TYPES=["Field","Shop","Design"]' in source
    assert columns.index('key:"code",label:"Cost Code"') < columns.index('key:"labor_type",label:"Labor type"')
    assert 'groupedScenarioColumns(laborTableColumns(),"labor_type")' in source
    assert 'items:LABOR_TYPES' in renderer
    assert 'identity:type=>type,label:type=>type' in renderer
    assert 'scenarioCostCodeTabs("labor"' not in source
    assert 'defaults.labor_type=group' in source
    assert 'defaults.code=(state.doc.cost_codes||[]).find(row=>row.status!=="inactive")?.code||""' in source
    assert 'data-labor-preset="4:10"' in source
    assert 'setAlternateScenarioDeltaValue(alt,"labor_estimates",model' in source
    assert 'function laborShiftDisplay(row)' in columns
    assert 'return hours>0&&days>0?row.shift_configuration||`${days}x${hours}`:""' in columns
    preset = source[source.index("function applyLaborPreset") : source.index("async function editBidSource")]
    assert 'row.workdays_per_week=days;row.hours_per_worker_per_day=hours' in preset
    assert 'path:`labor_estimates.${index}`' in preset
    assert preset.count("markDirty(") == 1


def test_alternate_grouped_tables_use_authoritative_calculated_row_projections():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    backend = Path("app/alternates.py").read_text(encoding="utf-8")
    for key in ("effective_equipment", "effective_borrowed_lites", "effective_labor_estimates"):
        assert key in source
        assert f'"{key}": deepcopy' in backend
    assert "function alternateScenarioProjectionPath" in source
    assert 'data-output-path="${esc(path)}"' in source
    assert "refreshScenarioGroupSummaries()" in source


def test_frame_and_doors_share_the_same_tab_module_table_and_keyboard_authorities():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    frame = source[source.index("function frameTabbedSectionHtml") : source.index("function insertAlternateTabsAfterHeader")]
    doors = source[source.index("function doorCostCodeTabs") : source.index("function equipmentTableColumns")]
    for helper in ("scenarioSubtabs", "scenarioScheduleSection", "scenarioTabbedWorkspace"):
        assert helper in frame
        assert helper in doors or helper == "scenarioSubtabs" and 'scenarioCostCodeTabs("doors"' in doors
    assert 'alternateScenarioTable({kind:"frames"' in source
    assert 'alternateScenarioTable({kind:"doors"' in source
    assert 'className:"frame-grid door-grid"' in source
    for behavior in (
        "MWUI.nextEditablePosition", "MWUI.arrowNavigationIntent",
        "MWUI.mapClipboard", "addAlternateScenarioGridRow",
        "focusAlternateScenarioGridCell", "sharedTableController?.scheduleFocusVisibility",
    ):
        assert behavior in source[source.index("function focusAlternateGridControl"):source.index("async function createAlternateUI")]
    door_section = source[source.index("function doorTabbedSectionHtml") : source.index("function renderTabbedDoors")]
    assert "doorStatusHtml" not in door_section
    assert "statusBadge" not in door_section
    assert 'scenarioSectionMeta(models,alt,"door")' in door_section
    assert ".scenario-frame-workspace .scenario-section > .scenario-schedule-no-summary" in css
    assert source.count('class="frame-section-tab-edit"') == 2
    assert 'document.querySelectorAll("[data-frame-section-code-edit]")' in source
    assert 'document.querySelectorAll("[data-scenario-cost-code-edit]")' in source


def test_door_cost_code_tab_edit_moves_base_and_alternate_rows_with_existing_persistence_semantics():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    editor = source[source.index("async function editScenarioCostCodeUI") : source.index("async function addFrameCostCodeUI")]
    assert 'config=SCENARIO_COLLECTION_CONFIG[kind]' in editor
    assert 'chooseFrameSectionCostCodeUI({title:fixed?`Edit ${config.label} Spec Section`:`Change ${config.label} Cost Code`' in editor
    assert "allowDelete:true" in editor
    assert 'setScenarioActiveTab(kind,scenarioKey,code)' in editor
    assert 'scenarioCollectionModels(config.collection,alt).filter(model=>sameCostCode(model.effective?.code,currentCode))' in editor
    assert 'setAlternateScenarioDeltaValue(alt,config.collection,model,{key:"code"},code)' in editor
    assert 'commitAlternateMutation(alt,prior,`${alt.key} ${config.label} Cost Code group changed`)' in editor
    assert 'row.code=code' in editor
    assert 'path:`${config.collection}.${index}.code`' in editor
    assert 'reason:`${config.label} Cost Code changed from tab`' in editor
    assert 'correlation_id:correlation' in editor


def test_grouped_takeoff_pencil_delete_clears_base_rows_and_uses_alternate_row_states():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    deletion = source[source.index("async function deleteScenarioCostCodeGroup") : source.index("async function editScenarioCostCodeUI")]
    editor = source[source.index("async function editScenarioCostCodeUI") : source.index("async function addFrameCostCodeUI")]

    assert 'confirmDialog(`Delete ${config.label} Spec Section`' in deletion
    assert '"Delete section"' in deletion
    assert 'The Cost Code remains available to other takeoffs.' in deletion
    assert 'Base remains unchanged.' in deletion
    assert 'activeModels.filter(model=>model.status==="Added")' in deletion
    assert 'if(model.status!=="Added")removedIds.add(String(model.effective.id))' in deletion
    assert 'bucket.removed=[...removedIds]' in deletion
    assert 'remaining=rows.filter(row=>!sameCostCode(row.code,currentCode))' in deletion
    assert 'markDirty({path:config.collection,prior,new:remaining' in deletion
    assert 'allowDelete:true' in editor
    assert 'lockCode:fixed' in editor
    assert 'if(code===FRAME_DELETE_SECTION){await deleteScenarioCostCodeGroup(kind,currentCode,config,alt);return}' in editor


def test_fixed_equipment_spec_section_keeps_its_code_locked_but_exposes_pencil_delete():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    tabs = source[source.index("function scenarioCostCodeTabs") : source.index("function quoteSelection")]
    chooser = source[source.index("async function chooseFrameSectionCostCodeUI") : source.index("async function deleteScenarioCostCodeGroup")]
    editor = source[source.index("async function editScenarioCostCodeUI") : source.index("async function addFrameCostCodeUI")]

    assert 'data-scenario-cost-code-edit="${esc(kind)}"' in tabs
    assert 'title="${fixedCodes?"Edit Section":"Change Cost Code"}"' in tabs
    assert 'lockCode=false' in chooser
    assert 'This ${esc(subject)} uses a fixed Cost Code.' in chooser
    assert '${lockCode?"disabled":""}' in chooser
    assert '${lockCode?"":frameAddCostCodeOption()}' in chooser
    assert 'if(lockCode)return currentCode||null' in chooser
    assert 'title:fixed?`Edit ${config.label} Spec Section`' in editor
    assert "allowDelete:true,lockCode:fixed" in editor


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
    assert ".frame-section-tab-edit" in css


def test_empty_scenario_subtabs_render_without_calling_item_identity():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    selector = source[source.index("function scenarioActiveTab") : source.index("function scenarioSubtabs")]
    assert 'const key=scenarioTabStoreKey(kind,scenarioKey),first=items[0]' in selector
    assert 'if(!first){setScenarioActiveTab(kind,scenarioKey,"");return ""}' in selector
    assert "identity(items[0])" not in selector


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
    assert "canonicalIndexByRow:new Map" in source
    assert "function bindStaticTableSorting" in source and "staticRowGroups" in source
    sort_binding = source[source.index("function bindTableSorting"):source.index("function staticCellValue")]
    assert "bindTableSorting" in source and "markDirty" not in sort_binding
    assert ".table-sort-button" in css and ".app-data-table" in css

    quote = source[source.index("function quoteTable"):source.index("function quoteGroupSummary")]
    rendered = source[source.index("function renderQuotes"):source.index("function frameSectionName")]
    assert 'key:"code",label:"Cost Code"' not in quote
    assert 'defaults:{...defaultRowFor("quotes"),code:activeCode' in quote
    assert 'id:`quotes-${historicalKey(activeCode)||"unassigned"}`' in quote
    assert "rowsProvider:()=>(state.doc.quotes||[]).filter" in quote
    assert 'kind:"quotes"' in rendered
    assert 'ariaLabel:"Quote Cost Codes"' in rendered
    assert "Each Cost Code has its own Quote tab" in rendered

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
        ("renderTabbedDoors", 'scenarioTabbedWorkspace({kind:"doors"'),
        ("renderEquipment", 'renderCostCodeScenarioWorkspace("equipment")'),
        ("renderLabor", 'scenarioTabbedWorkspace({kind:"labor"'),
    ):
        block = source[source.index(f"function {renderer}"):]
        assert marker in block[:12000]
    assert 'statusBadge("Controlled","controlled")' in source
    assert 'statusBadge("Project override","override"' in source or 'statusBadge("Override","override"' in source
    assert '"acknowledged-exception":"incomplete-row"' in source
    assert "Credit is applied before Surcharge" in source


def test_quote_schedule_header_has_an_independent_non_collapsing_grid():
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    assert '.quote-workspace [data-scenario-section-kind="quotes"] > .frame-schedule-summary' in css
    assert "grid-template-columns: minmax(18rem, 1fr) auto;" in css
    assert ".quote-workspace .frame-schedule-summary > .frame-section-description" in css
    assert "grid-column: 2 !important;" in css
    assert "overflow-wrap: normal;" in css
    assert "white-space: nowrap;" in css


def test_quote_square_feet_can_revert_to_combined_takeoff_default():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    services = Path("app/services.py").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    quote = source[source.index("function quoteSquareFeetIsTakeoffDefault") : source.index("function quoteGroupSummary")]
    assert "function quoteSquareFeetRevertAction" in quote
    assert 'data-revert-quote-square-feet="${esc(row.id)}"' in quote
    assert "function setQuoteSquareFeetRevertState" in quote
    assert 'setQuoteSquareFeetRevertState(rowId,source==="manual")' in source
    assert "function revertQuoteSquareFeet" in quote
    assert 'quote.square_feet_source="takeoff_default"' in quote
    assert "Restore ft² from Frames and Borrowed Lites" in quote
    assert 'button.onclick=()=>revertQuoteSquareFeet(button.dataset.revertQuoteSquareFeet)' in source
    assert 'takeoff_default = area_by_code.get(code_key, Decimal(0))' in services
    assert 'quote_area_source in {"frame_default", "takeoff_default"}' in services
    assert ".quote-square-feet-revert" in css
    assert ".quote-square-feet-revert:disabled" in css


def test_input_tables_do_not_add_leading_cell_status_flair():
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    rule = css[css.index("/* Row status is communicated by the row surface") :]
    assert ":is(table.data-grid, table.app-data-table) tbody tr:is(" in rule
    for state_class in (
        ".trailing-row", ".incomplete-row", ".acknowledged-exception",
        ".has-rate-override", ".has-override", ".manually-selected",
        ".automatically-selected", ".alt-added", ".alt-modified", ".alt-removed",
    ):
        assert state_class in rule
    assert "> td:first-child" in rule
    assert "box-shadow: none !important;" in rule


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
    project = source[source.index("function renderProject") : source.index("function renderScope")]
    assert 'data-wage-selection' in source
    assert '<option value="non_pw"' in source
    assert 'PW — ${county}' in source
    assert 'input("project.wage_data_id"' not in project
    assert 'input("project.wage_type"' not in project
    assert 'normalizedCountyName(left.county)===projectCounty' in source
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
    assert 'event.key!=="Escape"||!details?.open' in source


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
    assert 'data-path="project.miles_from_minneapolis"' in source
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
    assert 'historicalInput("project.owner_name","Organization","owners")' in project
    fill = source[source.index("function fillProjectOwnerFromMaster") : source.index("function selectScopeTableReference")]
    for field in ("owner_name", "owner_organization_id", "owner_legal_name", "owner_address", "owner_website", "owner_phone", "owner_email"):
        assert field in fill
    autocomplete = source[source.index("function bindAutocompletes") : source.index("function completePromotedTableRow")]
    assert 'kind==="owners"&&target.dataset.path==="project.owner_name"' in autocomplete
    assert "fillProjectOwnerFromMaster(item)" in autocomplete


def test_project_record_information_architecture_parties_dates_and_phones():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    project = source[source.index("function renderProject") : source.index("function renderScope")]
    for field in (
        "name", "project_number", "abbreviation", "estimator", "project_manager",
        "project_type", "building_type", "contract_type", "tax_exempt", "tax_rate_id",
        "frame_sealant_colors", "owner_name", "owner_legal_name", "owner_address",
        "owner_website", "owner_phone", "owner_email", "general_contractor",
        "general_contractor_address", "construction_manager", "construction_manager_address",
        "architect", "architect_address", "engineer", "engineer_address", "walkthrough",
        "bid_due_date", "start_date", "completion_date", "final_completion_date",
        "plan_source", "addenda_count", "notes",
    ):
        assert f'project.{field}' in project
    assert 'input("project.completion_date","Substantial completion date","date")' in project
    assert 'input("project.final_completion_date","Final completion date","date")' in project
    assert 'input("project.walkthrough","Walkthrough date and time","datetime-local")' in project
    for field in ("architect_address", "engineer_address", "general_contractor_address", "construction_manager_address"):
        assert f'input("project.{field}"' in project
    assert 'key:"address",label:"Address"' in project
    assert 'key:"custom_role"' not in project
    assert '["Owner","Architect","Vendor","Engineer","GC","CM","Custom"]' not in source
    assert 'key:"office_phone",label:"Office phone",type:"tel"' in project
    assert 'key:"mobile_phone",label:"Mobile phone",type:"tel"' in project
    assert "function formatPhoneNumber" in source
    assert "function parsePhoneNumber" in source
    assert 'inputmode="numeric" autocomplete="tel" maxlength="14"' in source
    assert 'numericType=type==="currency"||type==="number"||column.dimension' in source
    assert 'display=type==="tel"?formatPhoneNumber(shown)' in source
    for removed_setup_field in ("proposal_scope", "proposal_inclusions", "proposal_exclusions", "fabrication_due_date", "fabrication_start_date"):
        assert f'input("project.{removed_setup_field}"' not in project
    assert "Participants and proposal language" not in project
    for heading in (
        "Project Identity", "Project Details", "Project Team", "Dates &amp; Milestones",
        "Solicitation / Bid Information", "Project Notes",
    ):
        assert heading in project
    assert (
        project.index("Project Identity")
        < project.index("Project Details")
        < project.index("Project Team")
        < project.index("Dates &amp; Milestones")
        < project.index("Solicitation / Bid Information")
        < project.index("Project Notes")
    )
    assert 'projectRecordValue("Project status",humanStatus(projectStatus)' in project
    assert 'projectRecordValue("Job address county",state.doc.project.county' in project
    assert project.index('input("project.name","Project name")') < project.index('input("project.project_manager","Murphy project manager")')
    assert 'class="project-internal-responsibility" aria-label="Murphy internal project responsibility"' in project
    assert 'historicalInput("project.estimator","Murphy estimator","estimators")' in project
    assert 'input("project.project_manager","Murphy project manager")' in project
    assert "project-internal-heading" not in project
    assert project.index("${addressSearchInput()}") < project.index('historicalInput("project.estimator","Murphy estimator","estimators")') < project.index("Project Details")
    assert project.index('projectParty("Owner"') < project.index('class="project-contacts"') < project.index("Dates &amp; Milestones")
    for party in ("Owner", "General Contractor", "Construction Manager", "Architect / Designer", "Engineer"):
        assert f'projectParty("{party}"' in project
    assert '"No project contacts recorded.",{addLabel:"Add contact"}' in project
    for layout_class in (
        "project-detail-type", "project-detail-building", "project-detail-contract",
        "project-detail-tax-rate", "project-detail-mileage", "project-detail-colors",
        "project-milestone-datetime", "project-milestone-date",
        "project-solicitation-source", "project-solicitation-addenda",
    ):
        assert f'class="{layout_class}' in project or f' {layout_class}"' in project
    for first, second in (
        ('key:"organization",label:"Organization"', 'key:"address",label:"Address"'),
        ('key:"address",label:"Address"', 'key:"name",label:"Contact"'),
        ('key:"name",label:"Contact"', 'key:"position",label:"Title"'),
        ('key:"position",label:"Title"', 'key:"office_phone",label:"Office phone",type:"tel"'),
    ):
        assert project.index(first) < project.index(second)
    assert "function fillProjectParticipantFromMaster" in source
    assert 'kind==="organizations"&&target.dataset.path?.startsWith("project.")' in source


def test_project_record_layout_is_dense_readable_and_responsive():
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    shared_controls = css[css.index("/* Shared non-worksheet fields") : css.index("/* Project Information is a durable record")]
    project_css = css[css.index("/* Project Information is a durable record") :]
    for selector in (
        ".project-record", ".project-identity-grid", ".project-details-grid",
        ".project-party-grid", ".project-party-fields", ".project-milestone-grid",
        ".project-solicitation-grid",
    ):
        assert selector in project_css
    for variable in (
        "--project-grid-columns: repeat(12, minmax(0, 1fr));",
        "--project-column-gap: 8px;", "--project-row-gap: 4px;",
        "--project-field-height: 28px;", "--project-label-height: 12px;",
        "--project-label-gap: 2px;", "--project-section-padding: 8px 10px 9px;",
    ):
        assert variable in project_css
    assert "grid-template-columns: var(--project-grid-columns);" in project_css
    assert ".project-party-column {\n  grid-column: span 4;" in project_css
    assert ".project-milestone-datetime { grid-column: span 3; }" in project_css
    assert ".project-milestone-date { grid-column: span 2; }" in project_css
    assert ".project-party-fields > .field:first-child" in project_css
    assert ".project-party:not(.project-party-owner) .project-party-fields > .field:nth-child(2)" in project_css
    assert "max-width: 67rem" not in project_css
    assert "max-width: 44rem" not in project_css
    assert '@media (max-width: 80rem)' in project_css
    assert '@media (max-width: 55rem)' in project_css
    assert '@media (max-width: 47.5rem)' in project_css
    assert ".project-identity-name input" in project_css
    assert ".project-internal-responsibility" in project_css
    assert "align-self: end;" in project_css
    assert ".project-internal-heading" not in project_css
    assert ".project-contacts .table-add-row" in project_css
    assert "background: transparent;" in project_css
    assert ".project-detail-mileage { grid-column: span 2; }" in project_css
    assert ".project-detail-colors { grid-column: span 4; }" in project_css
    assert "background-color: var(--ui-surface-muted" in project_css
    assert "background-color: var(--ui-surface-strong" in project_css
    assert ".project-record .field" in project_css
    assert ".project-record .editable-table-shell" in project_css
    assert ".field :is(input:not([type=\"checkbox\"], [type=\"radio\"]), select, textarea)" in shared_controls
    assert "background-color: var(--ui-surface-muted);" in shared_controls
    assert "background-color: var(--ui-surface-strong);" in shared_controls


def test_borrowed_lites_keep_location_before_mark_and_shared_grid_behavior():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    core = Path("app/static/ui-core.js").read_text(encoding="utf-8")
    borrowed = source[source.index("function borrowedTableColumns") : source.index("function laborShiftDisplay")]
    assert 'key:"location",label:"Location"' in borrowed
    assert 'key:"mark",label:"Mark"' in borrowed
    assert borrowed.index('key:"location"') < borrowed.index('key:"mark"')
    assert 'function renderBorrowed(){return renderCostCodeScenarioWorkspace("borrowed")}' in source
    assert "applyPaste:applyTablePaste" in source
    assert 'rootElement.addEventListener("paste", this.onPaste)' in core


def test_shared_tables_support_contiguous_selection_normalized_single_cell_paste_and_colgroups():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    core = Path("app/static/ui-core.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    controller = core[core.index("class TableController") : core.index("class AutocompleteController")]
    for contract in (
        "onPointerDown", "onPointerOver", "selectCell(cell, extend", "selectionAnchor",
        "table-cell-selected", "table-row-selected", "onCopy(event)", "onSelectStart",
        "suppressNativeSelection", "table-range-selecting", "selectionCellFrom", "selectionCellAtPoint",
        "onPointerMove", "scheduleSelectionAutoScroll", "edgeAutoScrollDelta",
    ):
        assert contract in controller
    assert 'td[data-column-key]' in controller
    assert "this.rangeSelecting = true" in controller
    assert "this.selectionCellAtPoint(table, this.pointerClientX, this.pointerClientY) || this.selectionCellFrom(event)" in controller
    assert 'if (text === undefined) return' in controller
    assert "worksheetColGroup(columns,actionWidth)" in source
    assert 'col[data-column-key="${CSS.escape(key)}"]' in source
    assert "function bindGlobalGridSelection" in source
    assert "bindGlobalGridSelection();" in source
    assert "const selectableCell=target=>" in source
    assert "const nearestCell=(table,x,y)=>" in source
    assert "MWUI.edgeAutoScrollDelta" in source
    assert "function tableSelectionCopyMatrix" in source
    assert "copyRange:tableSelectionCopyMatrix" in source
    assert "spec.orderedRows||spec.rows?.()||[]" in source
    assert "this.options.copyRange?." in core
    assert "bindFrameTextExpansion();" not in source
    assert ".table-cell-selected" in css
    assert ".table-range-selecting" in css and "user-select: none !important" in css
    assert ".scenario-frame-workspace .frame-grid tbody td" in css
    assert "position: static !important" in css
    assert "left: auto !important" in css and "right: auto !important" in css
    assert "max-width: 100%" in css and "box-sizing: border-box" in css


def test_quotes_use_cost_code_header_tabs_and_takeoff_sections_are_not_forced():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    quotes = source[source.index("function renderQuotes") : source.index("function frameSectionName")]
    scenario_tabs = source[source.index("function scenarioCostCodeTabs") : source.index("function quoteSelection")]
    scenario_render = source[source.index("function renderCostCodeScenarioWorkspace") : source.index("function renderEquipment")]
    assert 'scenarioSubtabs({kind:"quotes"' in quotes
    assert 'quoteTable(activeCode)' in quotes
    assert 'data-table-add-row="${esc(`quotes-' in quotes
    assert 'for(const row of state.doc.cost_codes||[])if(row.status!=="inactive")' not in scenario_tabs
    assert "state.ui.emptyScenarioSections" in scenario_tabs
    assert 'data-scenario-section-add="${esc(kind)}"' in scenario_tabs
    assert "tabs.activeCode?costCodeScenarioSection" in scenario_render
    assert "async function addScenarioSpecSectionUI" in source
    assert "Spec Section deleted" in source


def test_frame_section_tab_order_is_explicit_and_independent_of_cost_code_edits():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    assert "function nextFrameTabOrder" in source
    assert "function orderedFrameSectionModels" in source
    assert "tab_order:nextFrameTabOrder()" in source
    tabbed = source[source.index("function renderTabbedFrames") : source.index("function insertAlternateTabsAfterHeader")]
    assert "orderedFrameSectionModels(" in tabbed
    editor = source[source.index("async function editFrameSectionCostCodeUI") : source.index("function addRow")]
    assert ".tab_order" not in editor


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
def test_frame_numeric_columns_are_clamped_to_their_rendered_values_only():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    assert 'const FRAME_NUMERIC_COLUMN_KEYS=new Set(["quantity","leaf_quantity","width_inches","height_inches","square_feet","perimeter_lf","caulking_passes","caulking_lf","head_sill_qty"])' in source
    assert "function frameNumericColumnMinimum" in source
    assert "const minimums={quantity:62" in source
    assert "context.measureText(text).width" not in source[source.index("function frameNumericColumnMinimum"):source.index("function setFrameColumnWidth")]
    assert "function syncFrameTotalAlignment" in source
    assert "Math.max(frameNumericColumnMinimum(workspace||root,key),Math.round(width))" in source
    assert "function enforceFrameNumericColumnMinimums" in source
    assert "FRAME_NUMERIC_COLUMN_KEYS.has(key)" in source
    assert 'workspace.addEventListener("input"' in source
    assert '"mark"' not in source[source.index("const FRAME_NUMERIC_COLUMN_KEYS"):source.index("function storedFrameColumnWidths")]
