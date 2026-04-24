"""
Background scheduler for automatic web source fetching.
Uses APScheduler with a single persistent BackgroundScheduler instance.
State (last run, next run, status) is stored in a JSON file so it
survives Streamlit reruns.
"""

import json
import threading
from datetime import datetime
from pathlib import Path

import streamlit as st
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

import fetch
import ingest

BASE_DIR = Path(__file__).parent.parent
STATE_FILE = BASE_DIR / "data" / "scheduler_state.json"
JOB_ID = "web_fetch"

_lock = threading.Lock()


# ── State persistence ──────────────────────────────────────────────────────────

def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"enabled": False, "interval_hours": 24, "last_run": None,
            "last_status": None, "next_run": None}


def _save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ── The fetch job ──────────────────────────────────────────────────────────────

def _run_fetch_job():
    state = _load_state()
    state["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    state["last_status"] = "running"
    _save_state(state)

    try:
        articles = fetch.fetch_all()
        if articles:
            ingest.ingest_web_articles(articles)
        state["last_status"] = f"ok — {len(articles)} new articles"
    except Exception as e:
        state["last_status"] = f"error: {e}"

    state["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    _save_state(state)


# ── Scheduler singleton (one per Streamlit process) ───────────────────────────

@st.cache_resource
def _get_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.start()

    # Re-add the job if it was enabled before restart
    state = _load_state()
    if state.get("enabled"):
        _add_job(scheduler, state["interval_hours"])

    return scheduler


def _add_job(scheduler: BackgroundScheduler, interval_hours: int):
    if scheduler.get_job(JOB_ID):
        scheduler.remove_job(JOB_ID)
    scheduler.add_job(
        _run_fetch_job,
        trigger=IntervalTrigger(hours=interval_hours),
        id=JOB_ID,
        replace_existing=True,
    )


# ── Public API ─────────────────────────────────────────────────────────────────

def enable(interval_hours: int = 24):
    scheduler = _get_scheduler()
    with _lock:
        _add_job(scheduler, interval_hours)
        state = _load_state()
        state["enabled"] = True
        state["interval_hours"] = interval_hours
        job = scheduler.get_job(JOB_ID)
        state["next_run"] = (
            job.next_run_time.strftime("%Y-%m-%d %H:%M") if job and job.next_run_time else None
        )
        _save_state(state)


def disable():
    scheduler = _get_scheduler()
    with _lock:
        if scheduler.get_job(JOB_ID):
            scheduler.remove_job(JOB_ID)
        state = _load_state()
        state["enabled"] = False
        state["next_run"] = None
        _save_state(state)


def run_now():
    """Trigger a fetch immediately (runs in background thread)."""
    t = threading.Thread(target=_run_fetch_job, daemon=True)
    t.start()


def get_state() -> dict:
    """Return current scheduler state, refreshing next_run from the live job."""
    scheduler = _get_scheduler()
    state = _load_state()
    job = scheduler.get_job(JOB_ID)
    if job and job.next_run_time:
        state["next_run"] = job.next_run_time.strftime("%Y-%m-%d %H:%M UTC")
    return state
