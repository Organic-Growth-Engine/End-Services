"""Global posting API: one request publishes a post to every platform service."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException

from gateway import config
from gateway.jobs import JobStore, run_job
from gateway.schemas import Job, PostRequest


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.jobs = JobStore(config.MAX_JOBS)
    app.state.tasks = set()
    async with httpx.AsyncClient() as client:
        app.state.client = client
        yield
        # Jobs don't survive a restart, so stop waiting on in-flight calls. The
        # platform services keep running and may still finish those posts.
        for task in app.state.tasks:
            task.cancel()
        await asyncio.gather(*app.state.tasks, return_exceptions=True)


app = FastAPI(
    title="Posting gateway",
    version="0.1.0",
    description="Publish one post to YouTube, X and Telegram with a single request.",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, object]:
    return {"status": "ok", "services": config.SERVICE_URLS}


@app.post("/posts", status_code=202, response_model=Job)
async def create_post(post: PostRequest) -> Job:
    """Start publishing to every target and return the job to poll."""
    job = app.state.jobs.create(post)
    task = asyncio.create_task(run_job(job, post, app.state.client))
    # Keep a reference so the task isn't garbage-collected mid-run.
    app.state.tasks.add(task)
    task.add_done_callback(app.state.tasks.discard)
    return job


@app.get("/posts/{job_id}", response_model=Job)
async def get_post(job_id: str) -> Job:
    job = app.state.jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown job id (jobs are lost when the gateway restarts).")
    return job


def run() -> None:
    """Entry point for `uv run gateway`."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uvicorn.run(app, host=config.HOST, port=config.PORT)
