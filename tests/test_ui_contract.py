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


def test_frame_takeoff_uses_dense_section_grid_and_trailing_entry_row():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    assert "framePageHead" in source and "frame-section-toolbar" in source
    assert "frame-summary-item" in source and "frame-section-identity" in source
    assert "ensureFrameTrailingRows" in source
    assert "Trailing frame entry row maintained" in source
    assert "trailing-row" in source and 'customized?"customized"' in source
    assert ".frame-table table{min-width:1480px;table-layout:fixed" in css
    assert ".frame-table td{height:29px" in css
    assert "@media(max-width:900px)" in css


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


def test_frame_tables_use_bounded_intrinsic_widths_instead_of_stretching():
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    assert "#workspace{width:min(100%,1760px);margin:0 auto}" in css
    assert ".frame-table table{width:1660px;min-width:1660px" in css
    assert ".frame-material-list{width:1120px;max-width:100%" in css


def test_frame_grid_follows_workbook_column_order_and_marks_calculated_cells():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    expected = 'cols=["Spec / Mark","Qty","Width (in)","Height (in)","SF","Perim","Caulk Passes","Caulking LF","Head / Sill","Head","Jamb","Sill","Type","Material","Finish","Notes","Install Mats"]'
    assert expected in source
    for key in ("square_feet", "perimeter_lf", "caulking_lf", "head_sill_qty"):
        assert f'data-frame-line-value="${{si}}:${{ri}}:{key}"' in source
    assert source.count('class="calculated numeric" data-frame-line-value=') >= 4


def test_frame_workspace_uses_comfortable_100_percent_zoom_scale():
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    assert ".nav-item{font-size:14px" in css
    assert ".frame-page-title h1{font-size:31px}" in css
    assert ".frame-table table{width:1660px;min-width:1660px;font-size:12.5px}" in css
    assert ".frame-table td{height:36px" in css
    assert ".frame-table td input{height:30px" in css
    assert ".frame-material-list td input{width:100%;height:27px" in css


def test_installation_materials_use_a_compact_fixed_width_list():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    css = Path("app/static/styles.css").read_text(encoding="utf-8")
    assert 'class="frame-material-list"' in source
    assert "<th>Installation material</th><th>Applicable source</th>" in source
    assert ".frame-material-list table{width:1118px;min-width:1118px" in css
    assert ".frame-material-list th:nth-child(3){width:90px}" in css


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
