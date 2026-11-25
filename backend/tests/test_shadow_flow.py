import pytest
from sqlalchemy import select

from core.db import transaction
from domain.jigs_model import jigs
from domain.shadows_model import shadow_orders, shadow_runs
from tests.fixtures import world  # noqa: F401


def _run(code, count=2):
    return {'code': code, 'jig': 'CL-44', 'current_profile': 'PRO-11',
            'candidate_profile': 'PRO-24', 'target_count': count}


def test_signing_full_batch_hands_over_and_keeps_orders_on_basis(world):
    """收足观察单后候选接替现用版，且已排位的单仍保有排位时的依据。"""
    world.post('/shadows/open-run', json=_run('SHD-9', count=2))
    orders = [world.post('/shadows/book-order', json={
        'run': 'SHD-9', 'heat': 500, 'thick': 4, 'target': 10}).json() for _ in range(2)]
    # 先制造一批与候选版更贴近的实弯
    for order in orders:
        world.post('/shadows/sign-order', json={
            'order': order['code'], 'measured': order['candidate_prediction']})
    with transaction() as conn:
        run = dict(conn.execute(select(shadow_runs).where(
            shadow_runs.c.code == 'SHD-9')).mappings().one())
        jig = dict(conn.execute(select(jigs).where(
            jigs.c.code == 'CL-44')).mappings().one())
        stored = conn.execute(select(shadow_orders).where(
            shadow_orders.c.run == 'SHD-9')).mappings().all()
    assert run['candidate_mae'] == 0.0
    assert run['decision'] == '候选接替现用版'
    assert jig['current_profile'] == 'PRO-24'
    # 已签回的单保留排位时的现用版依据，不被切换改写
    for row in stored:
        assert row['basis_profile'] == 'PRO-11'
        assert row['basis_prediction'] == row['current_prediction']


def test_booking_beyond_observation_count_is_rejected(world):
    """观察单数是本批排位上限，排满后拒绝新单，收尾时不会漏签。"""
    world.post('/shadows/open-run', json=_run('SHD-9', count=1))
    assert world.post('/shadows/book-order', json={
        'run': 'SHD-9', 'heat': 500, 'thick': 4, 'target': 10}).status_code == 200
    assert world.post('/shadows/book-order', json={
        'run': 'SHD-9', 'heat': 470, 'thick': 3, 'target': 11}).status_code == 409


def test_closed_run_rejects_new_orders(world):
    world.post('/shadows/open-run', json=_run('SHD-9', count=1))
    order = world.post('/shadows/book-order', json={
        'run': 'SHD-9', 'heat': 500, 'thick': 4, 'target': 10}).json()
    world.post('/shadows/sign-order', json={
        'order': order['code'], 'measured': order['candidate_prediction']})
    rejected = world.post('/shadows/book-order', json={
        'run': 'SHD-9', 'heat': 500, 'thick': 4, 'target': 10})
    assert rejected.status_code == 409


def test_switch_blocks_further_booking_on_stale_run(world):
    """切换与排位互斥：在役版本改走后，旧批次不能再排位。"""
    world.post('/shadows/open-run', json=_run('SHD-9', count=2))
    with transaction() as conn:
        conn.execute(jigs.update().where(jigs.c.code == 'CL-44').values(current_profile='PRO-24'))
    blocked = world.post('/shadows/book-order', json={
        'run': 'SHD-9', 'heat': 500, 'thick': 4, 'target': 10})
    assert blocked.status_code == 409
    with transaction() as conn:
        assert conn.scalar(select(shadow_orders.c.code).where(
            shadow_orders.c.run == 'SHD-9')) is None


def test_sign_back_uses_throw_locked_at_booking(world):
    """已排位的单按原依据签回：弯模之后重校，行程仍按排位时的上限核定。"""
    world.post('/shadows/open-run', json=_run('SHD-9', count=2))
    order = world.post('/shadows/book-order', json={
        'run': 'SHD-9', 'heat': 500, 'thick': 4, 'target': 10}).json()
    assert order['basis_throw'] == 32
    # 排位后弯模重校到更小行程，单据仍按排位时的 32 mm 核定
    with transaction() as conn:
        conn.execute(jigs.update().where(jigs.c.code == 'CL-44').values(max_throw=6))
    signed = world.post('/shadows/sign-order', json={
        'order': order['code'], 'measured': 8.0})
    assert signed.status_code == 200, signed.text
