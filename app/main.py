import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from app import db
from app.config import settings
from app.gmail import ESCALATED_LABEL, Gmail
from app.poller import poll_once

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("app.main")


async def poller_background_worker() -> None:
    """Async background task that runs the Gmail poller continuously."""
    logger.info("Background poller task started. Interval: %s seconds", settings.poll_interval_seconds)
    while True:
        try:
            count = await asyncio.to_thread(poll_once)
            if count:
                logger.info("Poller processed %s new message(s)", count)
        except Exception:
            logger.exception("Error during background polling cycle")
        await asyncio.sleep(settings.poll_interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: launch background poller
    worker_task = asyncio.create_task(poller_background_worker())
    logger.info("Application lifespan started: Background worker initialized")
    yield
    # Shutdown: cleanly cancel background task and close DB pool
    logger.info("Shutting down background worker...")
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    db.close_pool()
    logger.info("Application lifespan ended: DB pool closed")


app = FastAPI(
    title="Shree Vishwakarma Furnitures - AI Support API",
    description="Autonomous AI Customer Support System with Multimodal Vision, Vector RAG, and Human-In-The-Loop review",
    version="1.0.0",
    lifespan=lifespan,
)

TEMPLATES_DIR = Path(__file__).parent / "templates"


@app.get("/", response_class=HTMLResponse)
def index() -> RedirectResponse:
    """Redirect root to the engineering case study / blog page."""
    return RedirectResponse(url="/blog")


@app.get("/blog", response_class=HTMLResponse)
@app.get("/case-study", response_class=HTMLResponse)
def get_blog() -> str:
    """Engineering case study and behind-the-scenes architecture walkthrough."""
    blog_file = TEMPLATES_DIR / "blog.html"
    return blog_file.read_text(encoding="utf-8")



@app.get("/health")
def health() -> dict:
    try:
        sections = db.list_sections()
        return {"status": "ok", "database": "connected", "knowledge_sections": len(sections)}
    except Exception as e:
        return {"status": "degraded", "error": str(e)}


@app.get("/api/stats")
def get_stats() -> dict:
    return db.get_stats()


@app.get("/api/tickets")
def list_tickets(status: Literal["open", "answered", "escalated"] | None = None, limit: int = 50) -> list[dict]:
    return db.get_tickets(status=status, limit=limit)


@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: int) -> dict:
    ticket = db.get_ticket_details(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


class ApproveDraftRequest(BaseModel):
    reply_body: str


@app.post("/api/tickets/{ticket_id}/approve")
def approve_ticket(ticket_id: int, req: ApproveDraftRequest) -> dict:
    ticket = db.get_ticket_details(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    gmail = Gmail()
    thread = gmail.get_thread(ticket["gmail_thread_id"])
    if not thread.get("messages"):
        raise HTTPException(status_code=400, detail="No messages found in Gmail thread")

    latest_message = thread["messages"][-1]

    # Send the approved or edited reply to customer
    sent = gmail.send_reply(latest_message, req.reply_body)

    # Record the outbound message in database audit trail
    db.save_message(ticket_id, sent["id"], "out", gmail.address, req.reply_body)

    # Remove escalation label from latest message
    gmail.remove_label(latest_message["id"], ESCALATED_LABEL)

    # Update ticket status to answered
    db.update_ticket(ticket_id, status="answered", draft_reply=req.reply_body)

    return {"status": "success", "message": "Reply sent to customer and ticket resolved"}


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> str:
    """Built-in Human-In-The-Loop Review Dashboard."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Customer Support - Human In The Loop Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        body { font-family: 'Inter', sans-serif; }
    </style>
</head>
<body class="bg-slate-50 text-slate-900 min-h-screen">
    <header class="bg-indigo-900 text-white shadow-md">
        <div class="max-w-7xl mx-auto px-6 py-4 flex justify-between items-center">
            <div>
                <h1 class="text-xl font-bold tracking-tight">Shree Vishwakarma Furnitures</h1>
                <p class="text-xs text-indigo-200">AI Support Agent • Human-In-The-Loop Console</p>
            </div>
            <div class="flex items-center gap-3">
                <a href="/blog" class="text-xs bg-indigo-800 hover:bg-indigo-700 px-3 py-1.5 rounded-lg border border-indigo-700/60 text-indigo-100 font-semibold transition flex items-center gap-1.5">
                    <span>📖 Architecture & Case Study</span>
                </a>
                <div id="stats" class="flex gap-4 text-sm font-medium">
                    <span class="bg-indigo-800/80 px-3 py-1.5 rounded-lg border border-indigo-700/50">Loading stats...</span>
                </div>
            </div>
        </div>
    </header>

    <main class="max-w-7xl mx-auto px-6 py-8 grid grid-cols-1 md:grid-cols-3 gap-6">
        <section class="md:col-span-1 bg-white rounded-xl shadow-sm border border-slate-200 p-4 flex flex-col h-[750px]">
            <div class="flex justify-between items-center mb-4">
                <h2 class="font-semibold text-slate-800">Review Queue</h2>
                <button onclick="loadTickets()" class="text-xs text-indigo-600 hover:text-indigo-800 font-medium">Refresh</button>
            </div>
            <div class="flex gap-1 mb-3 bg-slate-100 p-1 rounded-lg text-xs">
                <button onclick="setFilter('escalated')" id="tab-escalated" class="flex-1 py-1.5 rounded bg-white font-medium shadow-xs text-center text-slate-800">Needs Review</button>
                <button onclick="setFilter('answered')" id="tab-answered" class="flex-1 py-1.5 rounded font-medium text-center text-slate-500">Answered</button>
                <button onclick="setFilter('')" id="tab-all" class="flex-1 py-1.5 rounded font-medium text-center text-slate-500">All</button>
            </div>
            <div id="ticket-list" class="flex-1 overflow-y-auto space-y-2 pr-1">
                <div class="text-sm text-slate-400 p-4 text-center">Loading tickets...</div>
            </div>
        </section>

        <section class="md:col-span-2 bg-white rounded-xl shadow-sm border border-slate-200 p-6 flex flex-col h-[750px]">
            <div id="ticket-empty" class="h-full flex flex-col items-center justify-center text-slate-400 text-sm">
                <svg class="w-12 h-12 mb-3 stroke-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/>
                </svg>
                Select an escalated ticket to review customer conversation and AI draft
            </div>
            <div id="ticket-detail" class="hidden h-full flex flex-col">
                <div class="border-b border-slate-100 pb-4 mb-4 flex justify-between items-start">
                    <div>
                        <span id="detail-badge" class="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 mb-2 inline-block">Escalated</span>
                        <h3 id="detail-subject" class="text-lg font-bold text-slate-900 leading-snug">Subject</h3>
                        <p id="detail-meta" class="text-xs text-slate-500 mt-1">From: user@example.com</p>
                    </div>
                </div>

                <div class="mb-4">
                    <span class="text-xs font-semibold uppercase tracking-wider text-slate-400">Proposed Escalation Reason</span>
                    <div id="detail-action" class="mt-1 p-2.5 bg-amber-50/70 border border-amber-200 rounded-lg text-xs text-amber-900 font-medium">None</div>
                </div>

                <div class="flex-1 overflow-y-auto space-y-3 mb-4 pr-1">
                    <span class="text-xs font-semibold uppercase tracking-wider text-slate-400">Conversation Thread</span>
                    <div id="detail-messages" class="space-y-3"></div>
                </div>

                <div class="border-t border-slate-100 pt-4">
                    <div class="flex justify-between items-center mb-1.5">
                        <label class="text-xs font-semibold uppercase tracking-wider text-slate-500">AI Proposed Draft Reply (Edit before sending)</label>
                    </div>
                    <textarea id="detail-reply" rows="5" class="w-full text-sm border border-slate-300 rounded-lg p-3 focus:outline-none focus:ring-2 focus:ring-indigo-500 font-sans"></textarea>
                    <div class="flex justify-end gap-3 mt-3">
                        <button onclick="approveTicket()" id="btn-approve" class="px-5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-semibold shadow-sm transition">
                            Approve & Dispatch Email
                        </button>
                    </div>
                </div>
            </div>
        </section>
    </main>

    <script>
        let currentFilter = 'escalated';
        let selectedTicketId = null;

        async function fetchStats() {
            try {
                const res = await fetch('/api/stats');
                const data = await res.json();
                document.getElementById('stats').innerHTML = `
                    <span class="bg-indigo-800/80 px-3 py-1.5 rounded-lg border border-indigo-700/50">Total Tickets: ${data.total_tickets}</span>
                    <span class="bg-amber-500/20 text-amber-200 px-3 py-1.5 rounded-lg border border-amber-400/30">Needs Review: ${data.escalated_tickets}</span>
                    <span class="bg-emerald-500/20 text-emerald-200 px-3 py-1.5 rounded-lg border border-emerald-400/30">Answered: ${data.answered_tickets}</span>
                `;
            } catch(e) {}
        }

        async function loadTickets() {
            try {
                const url = currentFilter ? `/api/tickets?status=${currentFilter}` : '/api/tickets';
                const res = await fetch(url);
                const tickets = await res.json();
                const list = document.getElementById('ticket-list');
                if (!tickets.length) {
                    list.innerHTML = `<div class="text-xs text-slate-400 text-center p-6">No tickets in this category</div>`;
                    return;
                }
                list.innerHTML = tickets.map(t => `
                    <div onclick="selectTicket(${t.id})" class="cursor-pointer p-3 rounded-lg border ${selectedTicketId === t.id ? 'border-indigo-600 bg-indigo-50/40' : 'border-slate-100 hover:bg-slate-50'} transition">
                        <div class="flex justify-between items-center mb-1">
                            <span class="text-xs font-semibold text-slate-800 truncate">${t.customer_email}</span>
                            <span class="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded ${t.status === 'escalated' ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'}">${t.status}</span>
                        </div>
                        <div class="text-xs font-medium text-slate-700 truncate">${t.subject || '(No Subject)'}</div>
                        <div class="text-[11px] text-slate-400 mt-1 truncate">${t.category || 'General'}</div>
                    </div>
                `).join('');
            } catch(e) {}
        }

        function setFilter(f) {
            currentFilter = f;
            document.querySelectorAll('[id^="tab-"]').forEach(el => {
                el.classList.remove('bg-white', 'text-slate-800', 'shadow-xs');
                el.classList.add('text-slate-500');
            });
            const activeTab = document.getElementById(f ? `tab-${f}` : 'tab-all');
            if (activeTab) {
                activeTab.classList.add('bg-white', 'text-slate-800', 'shadow-xs');
                activeTab.classList.remove('text-slate-500');
            }
            loadTickets();
        }

        async function selectTicket(id) {
            selectedTicketId = id;
            loadTickets();
            try {
                const res = await fetch(`/api/tickets/${id}`);
                const t = await res.json();
                document.getElementById('ticket-empty').classList.add('hidden');
                document.getElementById('ticket-detail').classList.remove('hidden');

                document.getElementById('detail-subject').innerText = t.subject || '(No Subject)';
                document.getElementById('detail-meta').innerText = `From: ${t.customer_email} • Category: ${t.category || 'N/A'}`;
                document.getElementById('detail-action').innerText = t.proposed_action || 'Review required';

                const badge = document.getElementById('detail-badge');
                badge.innerText = t.status;
                badge.className = `px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase ${t.status === 'escalated' ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'}`;

                const msgs = document.getElementById('detail-messages');
                msgs.innerHTML = t.messages.map(m => `
                    <div class="p-3 rounded-lg text-xs ${m.direction === 'in' ? 'bg-slate-100 text-slate-800' : 'bg-indigo-50 text-indigo-950 border border-indigo-100'}">
                        <div class="font-semibold mb-1 text-[11px] text-slate-500">${m.direction === 'in' ? 'Customer' : 'Support Reply'} (${m.from_address})</div>
                        <div class="whitespace-pre-wrap">${m.body}</div>
                    </div>
                `).join('');

                document.getElementById('detail-reply').value = t.draft_reply || '';
            } catch(e) {}
        }

        async function approveTicket() {
            if (!selectedTicketId) return;
            const reply = document.getElementById('detail-reply').value;
            if (!reply.trim()) {
                alert('Please enter a reply before approving.');
                return;
            }
            const btn = document.getElementById('btn-approve');
            btn.disabled = true;
            btn.innerText = 'Dispatching email...';
            try {
                const res = await fetch(`/api/tickets/${selectedTicketId}/approve`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ reply_body: reply })
                });
                const data = await res.json();
                if (res.ok) {
                    alert('Reply successfully sent to customer!');
                    fetchStats();
                    selectTicket(selectedTicketId);
                } else {
                    alert('Error: ' + data.detail);
                }
            } catch(e) {
                alert('Failed to send reply: ' + e);
            } finally {
                btn.disabled = false;
                btn.innerText = 'Approve & Dispatch Email';
            }
        }

        fetchStats();
        loadTickets();
        setInterval(fetchStats, 15000);
    </script>
</body>
</html>"""
