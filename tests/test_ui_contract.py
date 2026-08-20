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
        "--brand: #164a3d", "--input: #fffdf3", "--calculated: #eef4f2",
        "--focus-ring", "--motion-fast", "--z-tooltip", "--z-drawer",
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


def test_frame_takeoff_uses_compact_meaningful_modules_and_trailing_entry_row():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    core = Path("app/static/ui-core.js").read_text(encoding="utf-8")
    assert 'FRAME_TAKEOFF_PRESENTATION = "production-compact"' in source
    assert "frame-module" in source and "module-identity" in source
    assert '[code,description,"Take Off"]' in source
    for label in ("SF", "Install materials", "Material $/SF", "Subtotal"):
        assert label in source
    assert "Rows</small>" not in source
    assert "draftRowHtml" in source and "DraftStore" in core
    assert "ensureFrameTrailingRows" not in source
    assert "Trailing frame entry row maintained" not in source
    assert "trailing-row" in source


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
    labels = ["Mark / Type", "Qty", "Width", "Height", "SF", "Perim.", "Caulk passes", "Caulk LF", "Head / Sill", "Head", "Sill", "Jamb", "Type", "Material", "Finish", "Notes", "Install mats"]
    frame = source[source.index("function frameTable"):source.index("function materialTable")]
    positions = [frame.index(f'label:"{label}"') for label in labels]
    assert positions == sorted(positions)
    assert frame.count('class:"calculated numeric"') >= 4
    assert frame.count("tooltip:") >= 7
    assert 'label:"Qty OK"' in frame


def test_frame_workspace_uses_shared_dense_production_primitives():
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    for selector in (".frame-module", ".module-header", ".section-metrics", ".material-config"):
        assert selector in css
    assert "work-module frame-module" in source
    assert "section-metrics" in source
    assert "material-config" in source
    assert "frameSubtotalRow" in source and 'class="frame-subtotal-row"' in source
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


def test_bid_worksheet_exposes_components_subtotals_and_alt_navigation_without_bottom_detail():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    worksheet = source[source.index("function renderBidWorksheet"):source.index("function renderProposalLegacy")]
    for heading in ("Direct Cost", "Markup %", "Markup $", "Selling Value", "Total SF", "$/SF", "Historical"):
        assert heading in worksheet
    assert "bidWorksheetComponentRows" in source
    assert "bidWorksheetSourceRows" in source
    assert "bid-subtotal-row" in worksheet and "bid-grand-total" in source
    assert "effective_estimate" in worksheet
    assert "alternateTabs()+bidAlternateContext" in worksheet
    assert 'if(page==="bid"||page==="frames")return RENDER[page]();' in source
    assert 'alternateCommercialPanel("Alternate detail")' not in source
    assert "insertAlternateTabsAfterHeader(RENDER[page]())" in source
    assert "rerenderPreservingControl(\"data-alt-tab\",target)" in source
    for selector in (".bid-worksheet", ".bid-component-row", ".bid-subtotal-row", ".bid-grand-total", ".history-compact"):
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
        "installation_material_ids", "missing_quantity_acknowledged",
    ):
        assert f'["{field}"' in source
    assert "data-alt-frame-output" in source and "refreshAlternateFrameCalculatedView" in source
    assert "--frame-mark-width" in css and "--frame-qty-width" in css
    assert ".scenario-frame-workspace .frame-grid td:nth-child(1)" in css
    assert "position: sticky" in css and "var(--calculated)" in css and "var(--input)" in css


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
    assert "parseClipboardMatrix" in core and "mapClipboard" in core
    assert "correlationId(\"paste\")" in core
    assert "normalizeExact()" in core and "normalizeExact:true" in source


def test_shared_grid_markup_is_semantic_and_preserves_editable_calculated_distinction():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    editor = source[source.index("function tableEditor"):source.index("function addButton")]
    calculated = source[source.index("function calculatedTableCell"):source.index("function tableEditor")]
    assert '<table class="data-grid">' in editor
    assert '<th scope="col"' in editor
    assert "data-column-key" in editor
    assert "data-output-path" in source
    assert "calculatedTableCell" in editor and "<output " in calculated
    assert 'aria-label="${esc(column.label||field)}"' in source
    assert 'readonly aria-readonly="true"' in source
    assert 'class="trailing-row"' in source


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


def test_analogous_estimating_modules_share_compact_surfaces_and_status_language():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    for renderer, marker in (
        ("renderQuotes", "work-module quote-group"),
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
    assert "data-raw-numeric" in source and "input.dataset.rawNumeric" in source
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
    assert "text-overflow: ellipsis" not in css


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
    assert "state.doc.quotes.push(row)" in source
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
    dialog = source[source.index("function dialogForm") : source.index("function masterItemLabel")]
    assert 'dialog.returnValue=""' in dialog

    custom = source[source.index("async function openCustomCostCode") : source.index("function addRow")]
    assert "const projectId=state.doc?.project?.id" in custom
    assert custom.index("await ensureSaved()") < custom.index("values.expected_revision=state.doc.project.revision")
    assert "state.doc?.project?.id!==projectId" in custom
    assert "result.project&&result.project.project?.id!==projectId" in custom
    ensure = source[source.index("async function ensureSaved") : source.index("function updateHeader")]
    assert "while(state.saving&&state.doc?.project?.id===projectId)" in ensure
