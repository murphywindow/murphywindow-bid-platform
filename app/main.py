from __future__ import annotations

import io
import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

from .persistence import ConflictError, JsonStore, PersistenceError
from .generator import generate_test_project
from .mileage import MileageError, calculate_driving_mileage
from .schema import CONFIG_VERSION, default_configuration, duplicate_project, new_project, now, test_project, uid
from .services import (
    DomainError, ROLES, activate, audit, bump_bid_version, calculate_project, create_change_order,
    job_data, provisional_closeout, redact, reestimate_contract, require,
    save_sov, submit, update_change_order_status,
)

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("MURPHY_BID_DATA_DIR", BASE_DIR / "data"))
STATIC_DIR = BASE_DIR / "app" / "static"
store = JsonStore(DATA_DIR)


def ensure_seed() -> None:
    path = store.configurations / f"{CONFIG_VERSION}.json"
    if not path.exists():
        store.save_configuration(default_configuration())
    test_id = "prj_00000000000000000000000000004320"
    if not store.project_path(test_id).exists():
        doc = test_project()
        calculate_project(doc, store.load_configuration(CONFIG_VERSION))
        store.save_project(doc, -1)
    else:
        # Update only the untouched generated sandbox to the new owner reference.
        # Any user edit (bid sequence > 0 or file revision > 1) makes it ineligible.
        doc, _ = store.load_project(test_id)
        bid_sequence = int(doc["project"].get("bid_version", {}).get("sequence", 0))
        if doc["project"].get("configuration_id") != CONFIG_VERSION and bid_sequence == 0 and int(doc["project"].get("revision", 0)) == 1:
            prior_config = doc["project"].get("configuration_id")
            doc["project"]["configuration_id"] = CONFIG_VERSION
            doc.setdefault("configuration_lineage", []).append({"configuration_id": CONFIG_VERSION, "adopted_at": now(), "actor": "System seed migration"})
            calculate_project(doc, store.load_configuration(CONFIG_VERSION))
            bump_bid_version(doc, "owner_cost_code_reference_adopted")
            audit(doc, "System seed migration", "Systems Administrator", "project", test_id, "configuration_adopted",
                  {"configuration_id": prior_config}, {"configuration_id": CONFIG_VERSION}, "Untouched test project adopted owner-provided cost-code reference")
            store.save_project(doc, 1)


ensure_seed()
app = FastAPI(title="Murphy Window Bid Platform", version="1.0.0", docs_url="/api/docs", redoc_url=None)


@app.middleware("http")
async def prevent_stale_frontend(request: Request, call_next):
    """The local UI is developed in place; browsers must not reuse old shells/assets."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith(("/projects/", "/assets/", "/api/")):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


def identity(x_actor: str = Header("Local User"), x_role: str = Header("Estimator")) -> tuple[str, str]:
    if x_role not in ROLES:
        raise HTTPException(400, detail={"code": "invalid_role", "message": f"Unknown local role: {x_role}"})
    return x_actor.strip() or "Local User", x_role


def fail(exc: Exception) -> None:
    if isinstance(exc, DomainError):
        status = 403 if exc.code == "forbidden" else (409 if exc.code in {"duplicate_activation"} else 422)
        raise HTTPException(status, detail={"code": exc.code, "message": str(exc), "details": exc.details}) from exc
    if isinstance(exc, ConflictError):
        raise HTTPException(409, detail={"code": "concurrent_edit", "message": str(exc)}) from exc
    if isinstance(exc, PersistenceError):
        raise HTTPException(500, detail={"code": "persistence_error", "message": str(exc)}) from exc
    raise exc


def load(project_id: str) -> tuple[dict, dict]:
    doc, _ = store.load_project(project_id)
    config = store.load_configuration(doc["project"]["configuration_id"])
    return doc, config


def save_command(doc: dict, expected_revision: int, actor: str, role: str, operation: str) -> dict:
    audit(doc, actor, role, "project", doc["project"]["id"], operation, None, {"lifecycle_state": doc["project"]["lifecycle_state"]}, operation.replace("_", " ").title())
    return store.save_project(doc, expected_revision)


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "http_error", "message": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content={"error": detail})


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "data_directory": str(DATA_DIR), "schema_version": "1.0.0"}


@app.get("/api/roles")
def roles() -> dict:
    return {"roles": ROLES}


@app.get("/api/projects")
def projects(actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    return {"projects": store.list_projects()}


@app.post("/api/projects")
def create_project(payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        require(role, "edit_estimate")
        doc = new_project(payload.get("name", "Untitled Project"), actor, role)
        config = store.load_configuration(CONFIG_VERSION)
        calculate_project(doc, config)
        return {"project": redact(store.save_project(doc, -1), role)}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/generate-test")
def generate_project_for_testing(payload: dict = Body(default={}), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    """Create a persisted, curated synthetic draft. An optional seed makes its content reproducible."""
    actor, role = actor_role
    try:
        require(role, "edit_estimate")
        config = store.load_configuration(CONFIG_VERSION)
        doc = generate_test_project(config, actor, role, payload.get("seed"))
        calculate_project(doc, config)
        saved = store.save_project(doc, -1)
        generated = saved["project"].get("test_generation", {})
        return {
            "project": redact(saved, role),
            "generation": {
                **generated,
                "counts": {
                    "contacts": len(saved.get("contacts", [])), "cost_codes": len(saved.get("cost_codes", [])),
                    "quotes": len(saved.get("quotes", [])), "frame_sections": len(saved.get("takeoff_sections", [])),
                    "frame_rows": sum(len(section.get("lines", [])) for section in saved.get("takeoff_sections", [])),
                    "doors": len(saved.get("doors", [])), "equipment": len(saved.get("equipment", [])),
                    "borrowed_lites": len(saved.get("borrowed_lites", [])), "labor_lines": len(saved.get("labor_estimates", [])),
                },
            },
        }
    except Exception as exc:
        fail(exc)


@app.get("/api/projects/{project_id}")
def get_project(project_id: str, recover: bool = False, actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        doc, recovered_from = store.load_project(project_id, recover=recover)
        if recovered_from:
            audit(doc, actor, role, "project", project_id, "recovery_preview", None, {"backup": recovered_from}, "Primary JSON was invalid")
        return {"project": redact(doc, role), "recovered_from": recovered_from, "backups": store.backup_names(project_id)}
    except Exception as exc:
        fail(exc)


@app.put("/api/projects/{project_id}")
def save_project(project_id: str, payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        require(role, "edit_estimate")
        incoming = payload["project"]
        if incoming.get("project", {}).get("id") != project_id:
            raise DomainError("Project identifier does not match route.")
        expected = int(payload.get("expected_revision", incoming["project"].get("revision", 0)))
        current, config = load(project_id)
        # Client editing never receives authority to mutate immutable/lifecycle collections.
        protected = ("estimate_revisions", "reviews", "submissions", "proposal_artifacts", "award", "contract_allocations", "change_orders", "sov_lines", "closeout", "audit_events", "configuration_lineage")
        for key in protected:
            incoming[key] = deepcopy(current.get(key))
        incoming["project"]["configuration_id"] = current["project"]["configuration_id"]
        incoming["project"]["bid_version"] = deepcopy(current["project"].get("bid_version"))
        prior_digest = {"name": current["project"].get("name"), "working_total": current.get("working_estimate", {}).get("totals", {}).get("selling_value")}
        calculate_project(incoming, config)
        changes = payload.get("changes") or []
        if len(changes) > 10000:
            raise DomainError("A single save cannot record more than 10,000 datapoint changes.")
        count = len(changes) or max(1, int(payload.get("data_point_changes", 1)))
        bump_bid_version(incoming, "data_point_change", amount=count)
        correlation = payload.get("correlation_id") or uid("cor")
        if changes:
            for change in changes:
                path = str(change.get("path", "unknown"))[:500]
                audit(incoming, actor, role, "project_datapoint", project_id, "data_point_change",
                      {"path": path, "value": change.get("prior")}, {"path": path, "value": change.get("new")},
                      str(change.get("reason") or "Datapoint modified")[:1000], correlation)
        else:
            audit(incoming, actor, role, "project", project_id, "edit_save", prior_digest,
                  {"name": incoming["project"].get("name"), "working_total": incoming["working_estimate"]["totals"].get("selling_value"), "data_point_changes": count},
                  payload.get("reason", "Project inputs changed"), correlation)
        saved = store.save_project(incoming, expected)
        return {"project": redact(saved, role), "saved_at": saved["project"]["updated_at"]}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/mileage")
def calculate_project_mileage(project_id: str, payload: dict = Body(default={}), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        require(role, "edit_estimate")
        doc, _ = load(project_id)
        expected = int(payload.get("expected_revision", doc["project"].get("revision", 0)))
        address = str(payload.get("address") or doc["project"].get("address") or "").strip()
        zip_code = str(payload.get("zip") or doc["project"].get("zip") or "").strip()
        query = address if not zip_code or zip_code in address else f"{address}, {zip_code}"
        prior_result = doc["project"].get("mileage_calculation")
        if prior_result and prior_result.get("input_address", "").lower() == query.lower() and not payload.get("force"):
            return {"project": redact(doc, role), "mileage": prior_result, "cached": True}
        latest_config = store.load_configuration(CONFIG_VERSION)
        settings = latest_config.get("application_settings", {}).get("mileage", {})
        result = calculate_driving_mileage(query, settings)
        prior = {"miles_from_rogers": doc["project"].get("miles_from_rogers"), "mileage_calculation": prior_result}
        doc["project"]["miles_from_rogers"] = result["miles"]
        doc["project"]["mileage_calculation"] = {**result, "settings_configuration_id": latest_config["id"]}
        bump_bid_version(doc, "mileage_calculated")
        audit(doc, actor, role, "project_datapoint", project_id, "mileage_calculated", prior,
              {"miles_from_rogers": result["miles"], "mileage_calculation": doc["project"]["mileage_calculation"]},
              "Driving mileage calculated from job address to configured Rogers origin")
        saved = store.save_project(doc, expected)
        return {"project": redact(saved, role), "mileage": result, "cached": False}
    except MileageError as exc:
        fail(DomainError(str(exc), "mileage_lookup_failed"))
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/duplicate")
def duplicate(project_id: str, payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        require(role, "edit_estimate")
        source, config = load(project_id)
        doc = duplicate_project(source, payload.get("name") or f"{source['project']['name']} Copy", actor, role)
        calculate_project(doc, config)
        return {"project": redact(store.save_project(doc, -1), role)}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/archive")
def archive(project_id: str, payload: dict = Body(default={}), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        require(role, "archive")
        doc, _ = load(project_id)
        expected = doc["project"]["revision"]
        prior = doc["project"].get("archived", False)
        doc["project"]["archived"] = bool(payload.get("archived", True))
        bump_bid_version(doc, "archive_change")
        audit(doc, actor, role, "project", project_id, "archive" if doc["project"]["archived"] else "unarchive", prior, doc["project"]["archived"], payload.get("reason", "Archive Project"))
        return {"project": redact(store.save_project(doc, expected), role)}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/import")
def import_project(payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        require(role, "edit_estimate")
        doc = payload.get("project_document")
        if not isinstance(doc, dict) or doc.get("schema_version") != "1.0.0" or "project" not in doc:
            raise DomainError("Import must be a Murphy Window project JSON document with schema_version 1.0.0.")
        doc = deepcopy(doc)
        if payload.get("as_duplicate", True):
            doc = duplicate_project(doc, payload.get("name") or f"{doc['project'].get('name', 'Imported')} Import", actor, role)
        config = store.load_configuration(doc["project"].get("configuration_id", CONFIG_VERSION))
        calculate_project(doc, config)
        audit(doc, actor, role, "project", doc["project"]["id"], "import", None, {"source": payload.get("source", "JSON upload")}, "Project JSON import")
        return {"project": redact(store.save_project(doc, -1), role)}
    except Exception as exc:
        fail(exc)


@app.get("/api/projects/{project_id}/export")
def export_project(project_id: str, actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> Response:
    actor, role = actor_role
    try:
        require(role, "export")
        doc, _ = load(project_id)
        content = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
        return Response(content, media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{project_id}.json"'})
    except Exception as exc:
        fail(exc)


@app.get("/api/projects/{project_id}/job-data")
def export_job_data(project_id: str, actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        require(role, "export")
        doc, _ = load(project_id)
        return job_data(redact(doc, role))
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/backup")
def backup(project_id: str, actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        path = store.manual_backup(project_id)
        doc, _ = load(project_id)
        expected = doc["project"]["revision"]
        bump_bid_version(doc, "manual_backup")
        audit(doc, actor, role, "project", project_id, "backup", None, {"backup": path.name}, "Manual backup")
        store.save_project(doc, expected)
        return {"backup": path.name}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/recover")
def recover(project_id: str, payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        recovered = store.restore_backup(project_id, payload["backup"])
        expected = recovered["project"]["revision"]
        bump_bid_version(recovered, "recovery")
        audit(recovered, actor, role, "project", project_id, "recover", None, {"backup": payload["backup"]}, payload.get("reason", "Recover valid backup"))
        recovered = store.save_project(recovered, expected)
        return {"project": redact(recovered, role)}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/reviews")
def add_review(project_id: str, payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        require(role, "review")
        doc, _ = load(project_id)
        expected = doc["project"]["revision"]
        review = {"id": uid("revw"), "revision_id": payload.get("revision_id"), "reviewer": actor, "reviewer_role": role, "decision": payload.get("decision", "reviewed"), "comment": payload.get("comment", ""), "timestamp": now(), "evidence_status": "pending_policy"}
        doc["reviews"].append(review)
        bump_bid_version(doc, "review_recorded")
        audit(doc, actor, role, "review", review["id"], "review", None, review, payload.get("comment", "Bid review"))
        return {"project": redact(store.save_project(doc, expected), role), "review": review}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/submit")
def submit_project(project_id: str, payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        doc, config = load(project_id)
        expected = doc["project"]["revision"]
        result = submit(doc, config, actor, role, payload)
        return {"project": redact(store.save_project(doc, expected), role), "submission": result}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/activate")
def activate_project(project_id: str, payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        doc, _ = load(project_id)
        expected = doc["project"]["revision"]
        result = activate(doc, actor, role, payload)
        return {"project": redact(store.save_project(doc, expected), role), "award": result}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/contract/reestimate")
def contract_reestimate(project_id: str, payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        doc, _ = load(project_id)
        expected = doc["project"]["revision"]
        result = reestimate_contract(doc, actor, role, payload)
        return {"project": redact(store.save_project(doc, expected), role), "allocation": result}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/change-orders")
def change_order(project_id: str, payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        doc, config = load(project_id)
        expected = doc["project"]["revision"]
        result = create_change_order(doc, config, actor, role, payload)
        saved = store.save_project(doc, expected)
        return {"project": redact(saved, role), "change_order": redact({"change_orders": [result]}, role)["change_orders"][0]}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/change-orders/{order_id}/status")
def change_order_status(project_id: str, order_id: str, payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        doc, _ = load(project_id)
        expected = doc["project"]["revision"]
        result = update_change_order_status(doc, actor, role, order_id, payload)
        saved = store.save_project(doc, expected)
        return {"project": redact(saved, role), "change_order": redact({"change_orders": [result]}, role)["change_orders"][0]}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/sov")
def sov(project_id: str, payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        doc, _ = load(project_id)
        expected = doc["project"]["revision"]
        result = save_sov(doc, actor, role, payload)
        return {"project": redact(store.save_project(doc, expected), role), "sov": result}
    except Exception as exc:
        fail(exc)


@app.post("/api/projects/{project_id}/closeout")
def closeout(project_id: str, payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        doc, _ = load(project_id)
        expected = doc["project"]["revision"]
        result = provisional_closeout(doc, actor, role, payload)
        return {"project": redact(store.save_project(doc, expected), role), "closeout": result}
    except Exception as exc:
        fail(exc)


@app.get("/api/projects/{project_id}/proposal/{artifact_id}.pdf")
def proposal_pdf(project_id: str, artifact_id: str, download: bool = False, actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> Response:
    try:
        doc, _ = load(project_id)
        artifact = next((a for a in doc["proposal_artifacts"] if a["id"] == artifact_id), None)
        if not artifact:
            raise DomainError("Proposal artifact not found.")
        stream = io.BytesIO()
        pdf = SimpleDocTemplate(stream, pagesize=LETTER, leftMargin=.65*inch, rightMargin=.65*inch, topMargin=.55*inch, bottomMargin=.65*inch,
                                title=f"Proposal - {artifact['project_name']}", author="Murphy Window & Sunroom")
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name="Brand", parent=styles["Title"], textColor=colors.white, fontName="Helvetica-Bold", fontSize=18, leading=22, spaceAfter=0))
        styles.add(ParagraphStyle(name="ProposalTitle", parent=styles["Heading1"], textColor=colors.HexColor("#164A3D"), fontName="Helvetica-Bold", fontSize=20, leading=24, spaceBefore=14, spaceAfter=12))
        styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], textColor=colors.HexColor("#164A3D"), fontName="Helvetica-Bold", fontSize=11, leading=14, spaceBefore=12, spaceAfter=5))
        styles.add(ParagraphStyle(name="BodySmall", parent=styles["BodyText"], fontName="Helvetica", fontSize=9, leading=13, textColor=colors.HexColor("#293B36")))
        styles.add(ParagraphStyle(name="Amount", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=24, leading=29, textColor=colors.white, alignment=2))
        styles.add(ParagraphStyle(name="AmountWords", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=colors.white, alignment=2))
        story = []
        brand = Table([[Paragraph("MURPHY WINDOW &amp; SUNROOM", styles["Brand"]), Paragraph("BID PROPOSAL", ParagraphStyle("BrandRight", parent=styles["Brand"], fontSize=10, alignment=2))]], colWidths=[4.5*inch, 2.05*inch])
        brand.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#164A3D")),("BOX",(0,0),(-1,-1),0,colors.HexColor("#164A3D")),("LEFTPADDING",(0,0),(-1,-1),16),("RIGHTPADDING",(0,0),(-1,-1),16),("TOPPADDING",(0,0),(-1,-1),14),("BOTTOMPADDING",(0,0),(-1,-1),14),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
        story += [brand, Paragraph(escape(artifact["project_name"]), styles["ProposalTitle"])]
        info = [
            ["PROJECT NUMBER", artifact.get("project_number") or "Not assigned", "BID VERSION", artifact.get("bid_version", {}).get("display", "Not versioned")],
            ["PROJECT ADDRESS", artifact.get("project_address") or "Not provided", "BID DUE", artifact.get("bid_due_date") or "Not provided"],
            ["OWNER", artifact.get("owner_name") or "Not provided", "ADDENDA", str(artifact.get("addenda", 0))],
        ]
        info_rows = [[Paragraph(f"<b>{escape(str(a))}</b><br/><font color='#66766F'>{escape(str(b))}</font>", styles["BodySmall"]), Paragraph(f"<b>{escape(str(c))}</b><br/><font color='#66766F'>{escape(str(d))}</font>", styles["BodySmall"])] for a,b,c,d in info]
        info_table = Table(info_rows, colWidths=[3.275*inch,3.275*inch])
        info_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#F1F5F3")),("INNERGRID",(0,0),(-1,-1),.4,colors.HexColor("#D6E0DC")),("BOX",(0,0),(-1,-1),.6,colors.HexColor("#CAD7D2")),("LEFTPADDING",(0,0),(-1,-1),12),("RIGHTPADDING",(0,0),(-1,-1),12),("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8),("VALIGN",(0,0),(-1,-1),"TOP")]))
        story += [info_table, Spacer(1, 12)]
        amount_table = Table([[Paragraph("BASE BID", ParagraphStyle("AmountLabel", parent=styles["BodyText"], textColor=colors.white, fontName="Helvetica-Bold", fontSize=9)), Paragraph(f"${float(artifact['amount']):,.2f}", styles["Amount"])], [Paragraph("", styles["BodySmall"]), Paragraph(escape(artifact["written_amount"]), styles["AmountWords"])]], colWidths=[1.25*inch,5.3*inch])
        amount_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#276D5A")),("SPAN",(0,0),(0,1)),("LEFTPADDING",(0,0),(-1,-1),14),("RIGHTPADDING",(0,0),(-1,-1),14),("TOPPADDING",(0,0),(-1,0),10),("BOTTOMPADDING",(0,0),(-1,-1),8),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
        story += [amount_table]
        for key, title in (("scope","Scope of Work"),("inclusions","Inclusions"),("exclusions","Exclusions")):
            story.append(KeepTogether([Paragraph(title, styles["Section"]), Paragraph(escape(artifact.get(key) or "None stated."), styles["BodySmall"])]))
        story += [Spacer(1, 18), Paragraph("Artifact verification", styles["Section"]),
                  Paragraph(f"Immutable artifact: {escape(artifact['id'])}<br/>Source revision: {escape(artifact['revision_id'])}<br/>SHA-256: {escape(artifact['sha256'])}", ParagraphStyle("Verification", parent=styles["BodySmall"], fontSize=7, leading=10, textColor=colors.HexColor("#75837E"), wordWrap="CJK"))]
        def footer(canvas, document):
            canvas.saveState(); canvas.setStrokeColor(colors.HexColor("#D6E0DC")); canvas.line(document.leftMargin, .42*inch, LETTER[0]-document.rightMargin, .42*inch)
            canvas.setFont("Helvetica", 7); canvas.setFillColor(colors.HexColor("#66766F")); canvas.drawString(document.leftMargin, .25*inch, f"{artifact.get('bid_version',{}).get('display','BID')} - Immutable proposal {artifact['id']}")
            canvas.drawRightString(LETTER[0]-document.rightMargin, .25*inch, f"Page {document.page}"); canvas.restoreState()
        pdf.build(story, onFirstPage=footer, onLaterPages=footer)
        version = artifact.get("bid_version", {}).get("display", "bid").replace(".", "-")
        project_label = artifact.get("project_number") or doc["project"].get("abbreviation") or project_id
        safe_label = "".join(c for c in str(project_label) if c.isalnum() or c in "_-") or project_id
        disposition = "attachment" if download else "inline"
        return Response(stream.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f'{disposition}; filename="proposal-{safe_label}-{version}.pdf"', "X-Proposal-Artifact": artifact["id"]})
    except Exception as exc:
        fail(exc)


@app.get("/api/configurations")
def configurations(actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    _, role = actor_role
    values = store.list_configurations()
    if role not in {"General Manager", "President", "Project Manager", "Systems Administrator"}:
        for value in values:
            value["pco"] = {"status": value.get("pco", {}).get("status", "pending"), "restricted": True}
    return {"configurations": values}


@app.post("/api/configurations")
def create_configuration(payload: dict = Body(...), actor_role: tuple[str, str] = __import__("fastapi").Depends(identity)) -> dict:
    actor, role = actor_role
    try:
        require(role, "configuration")
        source = store.load_configuration(payload.get("source_id", CONFIG_VERSION))
        config = deepcopy(payload.get("configuration", source))
        if "csi_references" not in config:
            config["csi_references"] = deepcopy(source.get("csi_references", []))
            config["cost_code_reference"] = deepcopy(source.get("cost_code_reference"))
        config["id"] = uid("cfg")
        config["version"] = max((int(c.get("version", 0)) for c in store.list_configurations()), default=0) + 1
        config["created_at"] = now(); config["created_by"] = actor; config["status"] = "draft"
        config.setdefault("audit_events", []).append({"id": uid("aud"), "timestamp": now(), "actor": actor, "role": role, "operation": "configuration_create", "reason": payload.get("reason", "New effective-dated configuration")})
        store.save_configuration(config)
        return {"configuration": config}
    except Exception as exc:
        fail(exc)


app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str) -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
