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
    assert "@media(max-width:760px)" in css
    assert "--input:#fffdf3" in css
    assert "--calc:#eef4f2" in css
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
    assert "Add Custom Code" in source
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


def test_frame_takeoff_uses_basic_sections_and_trailing_entry_row():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    core = Path("app/static/ui-core.js").read_text(encoding="utf-8")
    css = Path("app/static/basic.css").read_text(encoding="utf-8")
    assert 'FRAME_TAKEOFF_PRESENTATION = "functional-baseline"' in source
    assert "frame-basic-page-head" in source and "frame-basic-section" in source
    assert "draftRowHtml" in source and "DraftStore" in core
    assert "ensureFrameTrailingRows" not in source
    assert "Trailing frame entry row maintained" not in source
    assert "trailing-row" in source
    assert ".frame-table table{width:1870px" in css
    assert ".frame-basic-section" in css


def test_workspace_pages_have_project_urls_and_browser_history_support():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    assert "function projectPageUrl" in source
    assert "function navigatePage" in source
    assert 'window.addEventListener("popstate"' in source
    assert "history.pushState" in source and "history.replaceState" in source
    assert 'href="${state.doc?projectPageUrl' in source


def test_frontend_assets_use_a_cache_busting_version():
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    assert "/assets/basic.css?v=" in html
    assert "/assets/app.js?v=" in html


def test_polished_stylesheet_is_preserved_but_dormant_during_functional_baseline():
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    assert Path("app/static/styles.css").exists()
    assert 'href="/assets/styles.css' not in html
    assert "preserved polished presentation" in html


def test_frame_tables_use_explicit_scrollable_working_widths():
    css = Path("app/static/basic.css").read_text(encoding="utf-8")
    assert ".table-wrap{max-width:100%;overflow:auto}" in css
    assert ".frame-table table{width:1870px" in css
    assert ".frame-material-list table{width:100%;min-width:900px}" in css


def test_frame_grid_follows_workbook_column_order_and_marks_calculated_cells():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    labels = ["Mark / Type", "Quantity", "Width", "Height", "Square Footage", "Perimeter", "Caulking Passes", "Caulking LF", "Head / Sill", "Head", "Sill", "Jamb", "Type", "Material", "Finish", "Notes", "Installation Materials"]
    frame = source[source.index("function frameTable"):source.index("function materialTable")]
    positions = [frame.index(f'label:"{label}"') for label in labels]
    assert positions == sorted(positions)
    for key in ("square_feet", "perimeter_lf", "caulking_lf", "head_sill_qty"):
        assert f'.calculated.{key}`' in frame
    assert frame.count('class:"calculated numeric"') >= 4


def test_frame_workspace_is_plain_dense_and_scoped_from_shared_shell():
    css = Path("app/static/basic.css").read_text(encoding="utf-8")
    assert "Temporary application-wide functional baseline" in css
    assert ".frame-functional{display:block" in css
    assert ".frame-basic-section" in css
    assert ".frame-table td{height:31px" in css
    assert ".frame-table td input{width:100%;height:26px" in css


def test_installation_materials_expose_existing_inputs_and_results_in_a_basic_table():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/basic.css").read_text(encoding="utf-8")
    assert 'class="frame-material-list"' in source
    assert "<th>Installation material</th><th>Applicable quantity</th>" in source
    assert "takeoff_sections.${si}.tie_back_qty" in source
    assert "takeoff_sections.${si}.backpan_lf" in source
    assert "material_overrides.${r.id}.factor_override" in source
    assert "material_overrides.${esc(r.id)}.rate_override" in source
    assert "override.factor_override??override.factor" in source
    assert "override.rate_override??override.rate" in source
    assert 'legacyPath=path.replace(/_override$/,""' in source
    assert ".frame-material-list table{width:100%;min-width:900px}" in css


def test_bid_tabulation_uses_only_the_shared_ui_draft_row():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    proposal = source[source.index("function renderProposal"):source.index("function renderReview")]
    assert 'tableEditor("bid_tabulations"' in proposal
    assert 'addButton("bid_tabulations"' not in proposal


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
    assert 'changes:{[values.field]' in source
    assert "confirmed:true" in source
    assert 'const BID_SOURCE_TYPES={quote:"quote",frame_material:"frame"' in source
    assert 'source_type:sourceType,source_id:sourceId' in source
    assert 'source.source_type||source.category||"estimate_line"' not in source
    assert "lineage.entered_price" in source and "lineage.final_adjusted_value" in source


def test_project_address_has_dynamic_route_mileage_and_manual_override():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    assert "data-calculate-mileage" in source
    assert "queueMileageCalculation" in source
    assert "/mileage`" in source
    assert 'data-path="project.miles_from_rogers"' in source
    assert 'step="0.1"' in source
    assert "item.label||item.matched_address" in source
    assert "latitude:item.latitude" in source and "longitude:item.longitude" in source
    assert "attribution:item.attribution" in source
