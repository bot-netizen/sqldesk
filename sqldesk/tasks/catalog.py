"""
Keeping the catalog current.

The context tools answer from the catalog rather than from a live schema
read, which means an install where nothing ever fills it has tools that
answer with nothing -- and until this existed, filling it was a command
somebody had to remember to run.

It is cheap enough to schedule. `get_schema()` reads the same Redis-cached
copy the schema browser uses and `refresh_schemas` is already keeping that
warm, so on an ordinary run this touches no warehouse at all: it parses SQL
already stored in `queries.query_text` and writes a few hundred rows.
"""

import logging
import time

from sqldesk import models, settings
from sqldesk.ai.catalog.harvest import harvest_data_source
from sqldesk.worker import job

logger = logging.getLogger(__name__)


@job("schemas", timeout=settings.CATALOG_HARVEST_TIMEOUT)
def harvest_catalog(data_source_id):
    """
    One data source, on the `schemas` queue.

    The same queue as schema refreshes on purpose: this is the same kind of
    work against the same sources, and it should queue behind them rather
    than compete with the queries people are waiting for.
    """
    source = models.DataSource.query.get(data_source_id)
    if source is None:
        logger.info("task=harvest_catalog state=skip ds_id=%s reason=gone", data_source_id)
        return

    started = time.time()
    try:
        result = harvest_data_source(source)
    except Exception:
        # One source's catalog failing is not worth losing the others, and
        # it must never be worth losing a worker.
        logger.exception("task=harvest_catalog state=error ds_id=%s", data_source_id)
        return

    logger.info(
        "task=harvest_catalog state=finish ds_id=%s tables=%s queries_mined=%s runtime=%.2f",
        data_source_id,
        result["tables"],
        result["queries_mined"],
        time.time() - started,
    )


def harvest_catalogs():
    """Every data source worth harvesting, one job each."""
    if not settings.FEATURE_AI:
        return

    for source in models.DataSource.query:
        if source.paused:
            logger.info("task=harvest_catalog state=skip ds_id=%s reason=paused", source.id)
        elif source.org.is_disabled:
            logger.info("task=harvest_catalog state=skip ds_id=%s reason=org_disabled", source.id)
        else:
            harvest_catalog.delay(source.id)
