"""Shared error handling for the upload API and command-line entry point."""

import logging
from contextlib import contextmanager

from fastapi import HTTPException
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


@contextmanager
def handle_upload_errors():
    """Translate upload failures while preserving explicit HTTP responses."""
    try:
        yield
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except HttpError as exc:
        logger.warning("YouTube rejected upload with HTTP %s", exc.resp.status)
        raise HTTPException(502, {
            "message": "YouTube rejected the upload.",
            "google_status": exc.resp.status,
        }) from exc
    except Exception as exc:
        logger.error("Upload failed (%s)", type(exc).__name__)
        raise HTTPException(
            502,
            "Upload failed. Check connection and Google authorization; run login again if necessary.",
        ) from exc


def handle_cli_error(parser, error):
    """Report a command failure and exit with the existing nonzero status."""
    parser.exit(1, f"Error: {error}\n")
