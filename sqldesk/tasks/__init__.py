from rq.connections import pop_connection, push_connection

from sqldesk import rq_redis_connection
from sqldesk.tasks.alerts import check_alerts_for_query
from sqldesk.tasks.failure_report import send_aggregated_errors
from sqldesk.tasks.general import (
    record_event,
    send_mail,
    sync_user_details,
    version_check,
)
from sqldesk.tasks.queries import (
    cleanup_query_results,
    empty_schedules,
    enqueue_query,
    execute_query,
    refresh_queries,
    refresh_schemas,
    remove_ghost_locks,
)
from sqldesk.tasks.schedule import (
    periodic_job_definitions,
    rq_scheduler,
    schedule_periodic_jobs,
)
from sqldesk.tasks.worker import Job, Queue, Worker


def init_app(app):
    app.before_request(lambda: push_connection(rq_redis_connection))
    app.teardown_request(lambda _: pop_connection())
