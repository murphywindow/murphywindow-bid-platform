from pathlib import Path


def test_browser_autosave_is_immediate_change_driven_and_coalesced():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    mark = source[source.index("function markDirty"):source.index("async function save")]
    assert "setTimeout(()=>save(),250)" in mark
    assert "clearTimeout(state.timer)" in mark
    assert "state.pendingChanges.push(change)" in mark
    assert "setInterval" not in source
    save = source[source.index("async function save"):source.index("function input")]
    assert "if(state.saving){state.saveQueued=true;return}" in save
    assert "changes:changesToSave" in save
    assert 'saveState("error"' in save
    assert "reconcileCalculatedView()" in save
    assert "render()" not in save
    assert "supplied.length===1?supplied[0]" in save


def test_refresh_and_browser_close_warn_without_silent_discard():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    assert "state.dirty||state.saveError" in source
    assert 'addEventListener("beforeunload"' in source
    assert "Unsaved project changes remain" in source


def test_invalid_controlled_cells_are_persisted_as_non_authoritative_validation_issues():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    assert "syncPendingControlledValues" in source
    assert "working_estimate.pending_controlled_values" in source
    assert "entered_value:issue.value" in source
