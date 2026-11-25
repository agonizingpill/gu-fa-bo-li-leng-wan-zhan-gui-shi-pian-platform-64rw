from fastapi import APIRouter, Depends, Query

from core.auth import actor, allow
from core.audit import record
from core.db import transaction
from domain import shadows_service as service
from domain.shadows_schemas import BookOrder, OpenRun, SignOrder

router = APIRouter()


@router.get('/shadows')
def list_runs(user=Depends(actor)):
    with transaction() as conn:
        return service.list_runs(conn)


@router.get('/shadows/orders')
def list_orders(run: str | None = Query(default=None), user=Depends(actor)):
    with transaction() as conn:
        return service.list_orders(conn, run)


@router.post('/shadows/open-run')
def open_run(data: OpenRun, user=Depends(actor)):
    allow(user, ('reviewer',))
    with transaction() as conn:
        output = service.open_run(conn, user, data)
        record(conn, user, 'shadows.open_run')
        return output


@router.post('/shadows/book-order')
def book_order(data: BookOrder, user=Depends(actor)):
    allow(user, ('operator', 'reviewer'))
    with transaction() as conn:
        output = service.book_order(conn, user, data)
        record(conn, user, 'shadows.book_order')
        return output


@router.post('/shadows/sign-order')
def sign_order(data: SignOrder, user=Depends(actor)):
    allow(user, ('reviewer',))
    with transaction() as conn:
        output = service.sign_order(conn, user, data)
        record(conn, user, 'shadows.sign_order')
        return output
