"""FastAPI routes for the credit card payoff analysis web application."""

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
    """Render the homepage with a list of saved analyses."""
    analyses = db.get_analyses()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"request": request, "analyses": analyses},
    )


@app.post("/analyses/new", response_class=RedirectResponse)
async def create_new_analysis(request: Request):
    """Create a new analysis and redirect to its detail page."""
    analysis = db.create_analysis()
    return RedirectResponse(f"/analyses/{analysis['id']}", status_code=303)


@app.get("/analyses/{analysis_id}", response_class=HTMLResponse)
async def view_analysis(request: Request, analysis_id: str):
    """Render the full analysis page with bank and credit tables."""
    analysis = db.get_analysis(analysis_id)
    if not analysis:
        return HTMLResponse("Analysis not found", status_code=404)
    accounts = db.get_accounts()
    banks = [a for a in accounts if a["type"] == "bank"]
    credits = [a for a in accounts if a["type"] in ("credit", "loan")]
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
    """Render the accounts management page."""
    accounts = db.get_accounts()
    return templates.TemplateResponse(
        request=request,
        name="accounts.html",
        context={"request": request, "accounts": accounts},
    )


@app.post("/accounts", response_class=HTMLResponse)
async def add_account(request: Request, name: str = Form(...), type: str = Form(...)):
    """Create a new bank or credit account and return the updated account list partial."""
    if type not in ["bank", "credit", "loan"]:
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
    """Delete an account and return the updated account list partial."""
    db.delete_account(account_id)
    accounts = db.get_accounts()
    return templates.TemplateResponse(
        request=request,
        name="partials/_account_list.html",
        context={"request": request, "accounts": accounts},
    )


@app.get("/accounts/{account_id}/edit", response_class=HTMLResponse)
async def edit_account(request: Request, account_id: str):
    """Return the inline edit form partial for an account."""
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
    """Update an account's name and return the updated account list partial."""
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
    """Update an analysis title and return the title partial."""
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
    """Add an account to an analysis and return the updated tables partial."""
    db.add_account_to_analysis(analysis_id, account_id)
    analysis = db.get_analysis(analysis_id)
    accounts = db.get_accounts()
    banks = [a for a in accounts if a["type"] == "bank"]
    credits = [a for a in accounts if a["type"] in ("credit", "loan")]
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
    """Remove an account from an analysis and return the updated tables partial."""
    db.remove_account_from_analysis(analysis_id, account_id)
    analysis = db.get_analysis(analysis_id)
    accounts = db.get_accounts()
    banks = [a for a in accounts if a["type"] == "bank"]
    credits = [a for a in accounts if a["type"] in ("credit", "loan")]
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
    """Update a bank starting balance or credit statement balance in an analysis."""
    db.update_snapshot(analysis_id, account_id, type, amount)
    analysis = db.get_analysis(analysis_id)
    if not analysis:
        return HTMLResponse("Not found", 404)
    accounts = db.get_accounts()
    banks = [a for a in accounts if a["type"] == "bank"]
    credits = [a for a in accounts if a["type"] in ("credit", "loan")]
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
    """Add a payment from a bank account toward a credit card in an analysis."""
    if p_date is None:
        p_date = date.today().isoformat()
    db.add_payment(analysis_id, credit_id, bank_id, amount, p_date)
    analysis = db.get_analysis(analysis_id)
    accounts = db.get_accounts()
    banks = [a for a in accounts if a["type"] == "bank"]
    credits = [a for a in accounts if a["type"] in ("credit", "loan")]

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
    """Delete a payment from an analysis and return the updated tables partial."""
    db.remove_payment(analysis_id, payment_id)
    analysis = db.get_analysis(analysis_id)
    accounts = db.get_accounts()
    banks = [a for a in accounts if a["type"] == "bank"]
    credits = [a for a in accounts if a["type"] in ("credit", "loan")]
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
