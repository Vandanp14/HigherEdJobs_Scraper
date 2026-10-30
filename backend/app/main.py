import asyncio
import sys
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import Settings
from .database import Database
from .scraper import AIRScraper, HigherEdJobsScraper

settings=Settings(); database=Database(settings.database, settings.resume); app=FastAPI(title="HigherEdJobs Review")
# Runs execute inside this process, so any run still open at startup was cut off by a stop.
database.close_interrupted_runs()
def relabel_on_startup(db):
    """Saved jobs labelled by an older classifier get the current labels once, without rescraping.
    A failure here must not keep the dashboard from starting."""
    try:
        db.reanalyze(only_outdated=True)
        db.relabel_seniority(only_outdated=True)
        db.rescore_fit(only_outdated=True)
    except Exception as error:
        print(f"Re-labelling saved jobs failed; showing existing labels: {error}", file=sys.stderr)


relabel_on_startup(database)
# Sources with a run in progress; a second run would double the request rate to the same site.
RUNNING: set[str]=set()
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])

class GroupUpdate(BaseModel): enabled: bool
class JobUpdate(BaseModel): application_status: str | None=None; notes: str | None=None
class RunRequest(BaseModel): group_ids: list[str]=Field(default_factory=list)

@app.get("/api/health")
async def health(): return {"ok":True,"app":"higheredjobs-review"}
@app.get("/api/groups")
async def groups(): return database.groups()
@app.patch("/api/groups/{group_id}")
async def group_update(group_id:str, body:GroupUpdate):
    if not database.set_group_enabled(group_id,body.enabled): raise HTTPException(404,"Search group not found")
    return {"ok":True}
@app.get("/api/jobs")
async def jobs(query:str="", group:str="", sponsorship:str="", application_status:str="", days:str="7", sort:str="newest", page:int=1, source:str="", description:str="", due:str="", hide:str=""):
    return database.jobs(query,group,sponsorship,application_status,days,sort,max(page,1),source=source,description=description,due=due,hide=hide)
@app.patch("/api/jobs/{job_id}")
async def job_update(job_id:int, body:JobUpdate):
    if not database.update_job(job_id,body.model_dump(exclude_none=True)): raise HTTPException(404,"Job not found")
    return {"ok":True}
@app.post("/api/jobs/{job_id}/opened")
async def opened(job_id:int): database.mark_opened(job_id); return {"ok":True}
@app.get("/api/runs/latest")
async def latest_run(source:str=""): return database.latest_run(source or None)
async def exclusive(source:str, start):
    if source in RUNNING: raise HTTPException(409,"A run for this source is already in progress")
    RUNNING.add(source)
    try: return await start()
    finally: RUNNING.discard(source)
@app.post("/api/runs")
async def run(body:RunRequest): return await exclusive("higheredjobs", lambda: HigherEdJobsScraper(database,settings).run(body.group_ids or None))
@app.post("/api/runs/air")
async def run_air(): return await exclusive("air", lambda: AIRScraper(database,settings).run())
@app.get("/api/sources")
async def sources():
    return [
        {
            "id": "higheredjobs",
            "name": "HigherEdJobs",
            "description": "Eight keyword searches on HigherEdJobs.",
            "supports_queries": True,
            "enabled": True,
            "run_path": "/api/runs",
            "last_run": database.latest_run("higheredjobs"),
        },
        {
            "id": "air",
            "name": "AIR Career Center",
            "description": "Curated AIR Career Center listings.",
            "supports_queries": False,
            "enabled": True,
            "run_path": "/api/runs/air",
            "last_run": database.latest_run("air"),
        },
    ]
@app.post("/api/reanalyze")
async def reanalyze(): return {"reanalyzed":database.reanalyze()}

frontend=Path(__file__).resolve().parents[2]/"frontend"/"dist"
if frontend.exists(): app.mount("/", StaticFiles(directory=frontend,html=True),name="frontend")
