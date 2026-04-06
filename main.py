from datetime import date

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from mangum import Mangum

import database as db

app = FastAPI(title="Credit Card Balance Overview")
templates = Jinja2Templates(directory="templates")

handler = Mangum(app)  # For AWS Lambda deployment


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    analyses = db.get_analyses()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"request": request, "analyses": analyses},
    )


@app.post("/analyses/new", response_class=RedirectResponse)
async def create_new_analysis(request: Request):
    analysis = db.create_analysis()
    return RedirectResponse(f"/analyses/{analysis['id']}", status_code=303)


@app.get("/analyses/{analysis_id}", response_class=HTMLResponse)
async def view_analysis(request: Request, analysis_id: str):
    analysis = db.get_analysis(analysis_id)
    if not analysis:
        return HTMLResponse("Analysis not found", status_code=404)
    accounts = db.get_accounts()
    banks = [a for a in accounts if a["type"] == "bank"]
    credits = [a for a in accounts if a["type"] == "credit"]
    return templates.TemplateResponse(
        request=request,
        name="analysis.html",
        context={
            "request": request,
            "analysis": analysis,
            "banks": banks,
            "credits": credits,
        },
    )


@app.get("/accounts", response_class=HTMLResponse)
async def list_accounts(request: Request):
    accounts = db.get_accounts()
    return templates.TemplateResponse(
        request=request,
        name="accounts.html",
        context={"request": request, "accounts": accounts},
    )


@app.post("/accounts", response_class=HTMLResponse)
async def add_account(request: Request, name: str = Form(...), type: str = Form(...)):
    if type not in ["bank", "credit"]:
        return HTMLResponse("Invalid account type", status_code=400)
    db.create_account(name, type)
    accounts = db.get_accounts()
    return templates.TemplateResponse(
        request=request,
        name="partials/_account_list.html",
        context={"request": request, "accounts": accounts},
    )


@app.post("/accounts/{account_id}/delete", response_class=HTMLResponse)
async def delete_account(request: Request, account_id: str):
    db.delete_account(account_id)
    accounts = db.get_accounts()
    return templates.TemplateResponse(
        request=request,
        name="partials/_account_list.html",
        context={"request": request, "accounts": accounts},
    )


@app.get("/accounts/{account_id}/edit", response_class=HTMLResponse)
async def edit_account(request: Request, account_id: str):
    account = db.get_account(account_id)
    if not account:
        return HTMLResponse("Account not found", status_code=404)
    return templates.TemplateResponse(
        request=request,
        name="partials/_account_edit.html",
        context={"request": request, "account": account},
    )


@app.post("/accounts/{account_id}/update", response_class=HTMLResponse)
async def update_account_route(
    request: Request, account_id: str, name: str = Form(...)
):
    db.update_account(account_id, name)
    accounts = db.get_accounts()
    return templates.TemplateResponse(
        request=request,
        name="partials/_account_list.html",
        context={"request": request, "accounts": accounts},
    )


@app.post("/analyses/{analysis_id}/update_title", response_class=HTMLResponse)
async def update_analysis_title(
    request: Request, analysis_id: str, title: str = Form(...)
):
    db.save_analysis(analysis_id, {"title": title})
    analysis = db.get_analysis(analysis_id)
    return templates.TemplateResponse(
        request=request,
        name="partials/_analysis_title.html",
        context={"request": request, "analysis": analysis},
    )


@app.post("/analyses/{analysis_id}/add_account", response_class=HTMLResponse)
async def add_account_to_analysis_route(
    request: Request, analysis_id: str, account_id: str = Form(...)
):
    db.add_account_to_analysis(analysis_id, account_id)
    analysis = db.get_analysis(analysis_id)
    accounts = db.get_accounts()
    banks = [a for a in accounts if a["type"] == "bank"]
    credits = [a for a in accounts if a["type"] == "credit"]
    return templates.TemplateResponse(
        request=request,
        name="partials/_analysis_full_tables.html",
        context={
            "request": request,
            "analysis": analysis,
            "banks": banks,
            "credits": credits,
        },
    )


@app.post("/analyses/{analysis_id}/remove_account", response_class=HTMLResponse)
async def remove_account_from_analysis_route(
    request: Request, analysis_id: str, account_id: str = Form(...)
):
    db.remove_account_from_analysis(analysis_id, account_id)
    analysis = db.get_analysis(analysis_id)
    accounts = db.get_accounts()
    banks = [a for a in accounts if a["type"] == "bank"]
    credits = [a for a in accounts if a["type"] == "credit"]
    return templates.TemplateResponse(
        request=request,
        name="partials/_analysis_full_tables.html",
        context={
            "request": request,
            "analysis": analysis,
            "banks": banks,
            "credits": credits,
        },
    )


@app.post("/analyses/{analysis_id}/update_snapshot", response_class=HTMLResponse)
async def update_snapshot(
    request: Request,
    analysis_id: str,
    account_id: str = Form(...),
    amount: float = Form(...),
    type: str = Form(...),
):
    db.update_snapshot(analysis_id, account_id, type, amount)
    analysis = db.get_analysis(analysis_id)
    if not analysis:
        return HTMLResponse("Not found", 404)
    accounts = db.get_accounts()
    banks = [a for a in accounts if a["type"] == "bank"]
    credits = [a for a in accounts if a["type"] == "credit"]
    return templates.TemplateResponse(
        request=request,
        name="partials/_analysis_full_tables.html",
        context={
            "request": request,
            "analysis": analysis,
            "banks": banks,
            "credits": credits,
        },
    )


@app.post("/analyses/{analysis_id}/payments", response_class=HTMLResponse)
async def add_payment(
    request: Request,
    analysis_id: str,
    credit_id: str = Form(...),
    bank_id: str = Form(...),
    amount: float = Form(...),
    p_date: str = Form(default=None),
):
    if p_date is None:
        p_date = date.today().isoformat()
    db.add_payment(analysis_id, credit_id, bank_id, amount, p_date)
    analysis = db.get_analysis(analysis_id)
    accounts = db.get_accounts()
    banks = [a for a in accounts if a["type"] == "bank"]
    credits = [a for a in accounts if a["type"] == "credit"]

    return templates.TemplateResponse(
        request=request,
        name="partials/_analysis_full_tables.html",
        context={
            "request": request,
            "analysis": analysis,
            "banks": banks,
            "credits": credits,
        },
    )


@app.post(
    "/analyses/{analysis_id}/payments/{payment_id}/delete", response_class=HTMLResponse
)
async def remove_payment(request: Request, analysis_id: str, payment_id: str):
    db.remove_payment(analysis_id, payment_id)
    analysis = db.get_analysis(analysis_id)
    accounts = db.get_accounts()
    banks = [a for a in accounts if a["type"] == "bank"]
    credits = [a for a in accounts if a["type"] == "credit"]
    return templates.TemplateResponse(
        request=request,
        name="partials/_analysis_full_tables.html",
        context={
            "request": request,
            "analysis": analysis,
            "banks": banks,
            "credits": credits,
        },
    )
