import asyncio
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import Settings
from .database import Database
from .scraper import AIRScraper, HigherEdJobsScraper

settings=Settings(); database=Database(settings.database); app=FastAPI(title="HigherEdJobs Review")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])

class GroupUpdate(BaseModel): enabled: bool
class JobUpdate(BaseModel): application_status: str | None=None; notes: str | None=None
class RunRequest(BaseModel): group_ids: list[str]=Field(default_factory=list)

@app.get("/api/health")
def health(): return {"ok":True}
@app.get("/api/groups")
def groups(): return database.groups()
@app.patch("/api/groups/{group_id}")
def group_update(group_id:str, body:GroupUpdate):
    if not database.set_group_enabled(group_id,body.enabled): raise HTTPException(404,"Search group not found")
    return {"ok":True}
@app.get("/api/jobs")
def jobs(query:str="", group:str="", sponsorship:str="", application_status:str="", days:str="7", sort:str="newest", page:int=1, source:str="", description:str=""):
    return database.jobs(query,group,sponsorship,application_status,days,sort,max(page,1),source=source,description=description)
@app.patch("/api/jobs/{job_id}")
def job_update(job_id:int, body:JobUpdate):
    if not database.update_job(job_id,body.model_dump(exclude_none=True)): raise HTTPException(404,"Job not found")
    return {"ok":True}
@app.post("/api/jobs/{job_id}/opened")
def opened(job_id:int): database.mark_opened(job_id); return {"ok":True}
@app.get("/api/runs/latest")
def latest_run(source:str=""): return database.latest_run(source or None)
@app.post("/api/runs")
async def run(body:RunRequest): return await HigherEdJobsScraper(database,settings).run(body.group_ids or None)
@app.post("/api/runs/air")
async def run_air(): return await AIRScraper(database,settings).run()
@app.get("/api/sources")
def sources():
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
def reanalyze(): return {"reanalyzed":database.reanalyze()}

frontend=Path(__file__).resolve().parents[2]/"frontend"/"dist"
if frontend.exists(): app.mount("/", StaticFiles(directory=frontend,html=True),name="frontend")
