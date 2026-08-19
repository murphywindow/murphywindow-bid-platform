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
    assert 'data-cost-code-index="${i}"' in source
    assert "matchingScopeReferences" in source
    assert "chooseScopeReference" in source
    assert 'rowInput(`cost_codes.${i}.description`' in source
    assert "description filled and remains editable" in source


def test_frame_autosave_refreshes_in_place_and_enter_inserts_a_focused_row():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    assert 'if(state.page==="frames")refreshFrameCalculatedView();else render()' in source
    assert "data-frame-line-value" in source
    assert "Frame row inserted with Enter" in source
    assert "section.lines.splice(nextIndex,0,newRow)" in source
    assert "next.focus()" in source


def test_frame_takeoff_uses_basic_sections_and_trailing_entry_row():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    assert 'FRAME_TAKEOFF_PRESENTATION = "functional-baseline"' in source
    assert "frame-basic-page-head" in source and "frame-basic-section" in source
    assert "ensureFrameTrailingRows" in source
    assert "Trailing frame entry row maintained" in source
    assert "trailing-row" in source and 'customized?"customized"' in source
    assert ".frame-functional .frame-table table{width:1870px;min-width:1870px" in css
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
    assert "/assets/styles.css?v=" in html
    assert "/assets/app.js?v=" in html


def test_frame_tables_use_explicit_scrollable_working_widths():
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    assert "#workspace{width:min(100%,1760px);margin:0 auto}" in css
    assert ".frame-functional .frame-table table{width:1870px;min-width:1870px" in css
    assert ".frame-functional .frame-material-list{width:100%;max-width:100%" in css


def test_frame_grid_follows_workbook_column_order_and_marks_calculated_cells():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    expected = 'cols=["Mark / Type","Quantity","Width","Height","Square Footage","Perimeter","Caulking Passes","Caulking LF","Head / Sill","Head","Sill","Jamb","Type","Material","Finish","Notes","Installation Materials"]'
    assert expected in source
    for key in ("square_feet", "perimeter_lf", "caulking_lf", "head_sill_qty"):
        assert f'data-frame-line-value="${{si}}:${{ri}}:{key}"' in source
    assert source.count('class="calculated numeric" data-frame-line-value=') >= 4


def test_frame_workspace_is_plain_dense_and_scoped_from_shared_shell():
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    assert ".nav-item{font-size:14px" in css
    assert ".frame-functional{display:block" in css
    assert ".frame-basic-section" in css and "box-shadow:none" in css
    assert ".frame-functional .frame-table td{height:32px" in css
    assert ".frame-functional .frame-table td input{width:100%;height:27px" in css


def test_installation_materials_expose_existing_inputs_and_results_in_a_basic_table():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    assert 'class="frame-material-list"' in source
    assert "<th>Installation material</th><th>Applicable quantity</th>" in source
    assert "takeoff_sections.${si}.tie_back_qty" in source
    assert "takeoff_sections.${si}.backpan_lf" in source
    assert ".frame-functional .frame-material-list table{width:100%;min-width:960px" in css


def test_frame_dimensions_accept_natural_units_and_rows_can_be_duplicated():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    assert "function normalizeFrameDimension" in source
    assert "4f 6in" in source and "inputmode=\"decimal\"" in source
    assert "data-duplicate-frame" in source and "Frame row duplicated" in source


def test_frame_grid_has_live_workbook_aligned_subtotals():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    assert "<tfoot><tr><th>Subtotal</th>" in source
    for key in ("quantity", "square_feet", "perimeter_lf", "caulking_lf", "head_sill_qty"):
        assert f'data-frame-section-value="${{si}}:{key}"' in source
    assert "querySelectorAll(`[data-frame-section-value=" in source
    assert ".frame-table tfoot th,.frame-table tfoot td" in css


def test_project_address_has_dynamic_route_mileage_and_manual_override():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    assert "data-calculate-mileage" in source
    assert "queueMileageCalculation" in source
    assert "/mileage`" in source
    assert 'data-path="project.miles_from_rogers"' in source
    assert 'step="0.1"' in source
