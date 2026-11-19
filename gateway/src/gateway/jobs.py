"""In-memory job store and the fan-out that runs one job.

Jobs live only in this process: they are lost on restart and not shared
between workers, so run the gateway as a single process for now. Swap
JobStore for a database / the event bus when the scheduler is built.
"""

import asyncio
import logging
from collections import OrderedDict
from datetime import UTC, datetime
from uuid import uuid4

import httpx

from gateway import adapters, config
from gateway.schemas import (
    PLATFORMS,
    Job,
    JobStatus,
    Platform,
    PostRequest,
    TargetResult,
    TargetStatus,
)

logger = logging.getLogger(__name__)

DETAIL_LIMIT = 2000


def _now() -> datetime:
    return datetime.now(UTC)


class JobStore:
    def __init__(self, max_jobs: int) -> None:
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._max_jobs = max_jobs

    def create(self, post: PostRequest) -> Job:
        job_id = uuid4().hex
        targets = post.targets or list(PLATFORMS)
        job = Job(
            id=job_id,
            created_at=_now(),
            targets={platform: TargetResult() for platform in targets},
        )
        self._jobs[job_id] = job
        self._evict()
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def _evict(self) -> None:
        # Drop the oldest finished jobs; running jobs are never dropped.
        excess = len(self._jobs) - self._max_jobs
        for job_id in [j.id for j in self._jobs.values() if j.finished_at][:max(excess, 0)]:
            del self._jobs[job_id]


async def run_job(job: Job, post: PostRequest, client: httpx.AsyncClient) -> None:
    """Post to every target concurrently and record each outcome on the job."""
    await asyncio.gather(
        *(_run_target(job, platform, post, client) for platform in job.targets)
    )
    statuses = {t.status for t in job.targets.values()}
    if statuses == {TargetStatus.SKIPPED}:
        job.status = JobStatus.SKIPPED
    elif TargetStatus.SUCCEEDED not in statuses:
        job.status = JobStatus.FAILED
    elif TargetStatus.FAILED in statuses:
        job.status = JobStatus.PARTIAL
    else:
        job.status = JobStatus.SUCCEEDED
    job.finished_at = _now()
    logger.info("Job %s finished: %s", job.id, job.status)


async def _run_target(
    job: Job, platform: Platform, post: PostRequest, client: httpx.AsyncClient
) -> None:
    result = job.targets[platform]
    try:
        call = adapters.build_call(platform, post, job.id)
    except adapters.Skip as skip:
        result.status, result.detail = TargetStatus.SKIPPED, str(skip)
        result.finished_at = _now()
        return

    result.status, result.started_at = TargetStatus.RUNNING, _now()
    url = f"{config.SERVICE_URLS[platform]}{call.path}"
    try:
        # No automatic retry: publishing isn't idempotent, so a retry after a
        # timeout could post twice.
        response = await client.post(
            url, params=call.params, json=call.json, timeout=call.timeout
        )
    except httpx.TimeoutException:
        _fail(result, f"{platform} service did not respond within {call.timeout:g}s; "
              "the post may still have been published.")
    except httpx.HTTPError as exc:
        _fail(result, f"Could not reach the {platform} service: {type(exc).__name__}.")
    except Exception:
        logger.exception("Job %s: unexpected error posting to %s", job.id, platform)
        _fail(result, "Unexpected gateway error.")
    else:
        result.http_status = response.status_code
        result.response = _body(response)
        if response.is_success:
            result.status = TargetStatus.SUCCEEDED
        else:
            _fail(result, f"{platform} service returned HTTP {response.status_code}.")
    finally:
        result.finished_at = _now()
        logger.info("Job %s: %s %s", job.id, platform, result.status)


def _fail(result: TargetResult, detail: str) -> None:
    result.status, result.detail = TargetStatus.FAILED, detail


def _body(response: httpx.Response) -> object:
    try:
        return response.json()
    except ValueError:
        return response.text[:DETAIL_LIMIT]
