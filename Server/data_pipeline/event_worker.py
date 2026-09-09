"""Small lease-aware event demand worker entry point.

Connector execution is intentionally injected: this module owns claiming and
fencing, while a caller supplies the approved acquisition function.
"""
from adventour_backend.services import event_demand_service as demand


def run_once(backend, acquire, now=None):
    """Claim one job and invoke ``acquire(job)`` outside the DB transaction.

    ``acquire`` is deliberately injected: this foundation performs no connector
    discovery and cannot write provider facts. It must publish through the
    approved event refresh path and return only after its bounded work finishes.
    Its result is ignored; lease fencing controls the completion update.
    """
    with backend.app.app_context():
        job = demand.claim(backend.db, now)
        if job is None:
            backend.db.session.rollback()
            return {'status': 'idle'}
        backend.db.session.commit()
        try:
            acquire(job)
        except Exception as exc:
            demand.finish(backend.db, job['work_key'], job['fencing_token'], success=False, error=exc, now=now)
            backend.db.session.commit()
            return {'status': 'backoff', 'error': type(exc).__name__}
        demand.finish(backend.db, job['work_key'], job['fencing_token'], success=True, now=now)
        backend.db.session.commit()
        return {'status': 'complete', 'work_key': job['work_key']}
