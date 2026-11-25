import pytest
from sqlalchemy import insert, select

from core.db import transaction
from domain.curves import predict
from domain.jigs_model import jigs
from domain.profiles_model import profiles
from domain.shadows_model import shadow_orders, shadow_runs
from tests.fixtures import world  # noqa: F401


def _profile(code):
    with transaction() as conn:
        return dict(conn.execute(select(profiles).where(
            profiles.c.code == code)).mappings().one())


def test_open_run_records_versions_and_rejects_duplicate(world):
    opened = world.post('/shadows/open-run', json={
        'code': 'SHD-9', 'jig': 'CL-44', 'current_profile': 'PRO-11',
        'candidate_profile': 'PRO-24', 'target_count': 2})
    assert opened.status_code == 200, opened.text
    assert opened.json()['state'] == '跟跑中'
    assert opened.json()['collected'] == 0

    duplicate = world.post('/shadows/open-run', json={
        'code': 'SHD-10', 'jig': 'CL-44', 'current_profile': 'PRO-11',
        'candidate_profile': 'PRO-24', 'target_count': 2})
    assert duplicate.status_code == 409

    mismatched = world.post('/shadows/open-run', json={
        'code': 'SHD-11', 'jig': 'CL-44', 'current_profile': 'PRO-24',
        'candidate_profile': 'PRO-11', 'target_count': 2})
    assert mismatched.status_code == 409


def test_open_run_rejects_unrecomputable_and_unknown_profiles(world):
    with transaction() as conn:
        conn.execute(insert(profiles).values(
            code='PRO-OLD', coupon='GP-00', prediction=7.0, mae=0.9,
            curve={'terms': ['温度']}, token='tok-old'))
    bad = world.post('/shadows/open-run', json={
        'code': 'SHD-9', 'jig': 'CL-44', 'current_profile': 'PRO-OLD',
        'candidate_profile': 'PRO-24', 'target_count': 2})
    assert bad.status_code == 409
    missing = world.post('/shadows/open-run', json={
        'code': 'SHD-9', 'jig': 'CL-44', 'current_profile': 'PRO-11',
        'candidate_profile': 'PRO-404', 'target_count': 2})
    assert missing.status_code == 404


def test_book_order_seals_both_predictions_and_uses_current_for_travel(world):
    world.post('/shadows/open-run', json={
        'code': 'SHD-9', 'jig': 'CL-44', 'current_profile': 'PRO-11',
        'candidate_profile': 'PRO-24', 'target_count': 2})
    booked = world.post('/shadows/book-order', json={
        'run': 'SHD-9', 'heat': 500, 'thick': 4, 'target': 10})
    assert booked.status_code == 200, booked.text
    order = booked.json()
    point = {'heat': 500, 'thick': 4, 'target': 10}
    assert order['basis_profile'] == 'PRO-11'
    assert order['current_prediction'] == predict(_profile('PRO-11')['curve'], point)
    assert order['candidate_prediction'] == predict(_profile('PRO-24')['curve'], point)
    assert order['basis_prediction'] == order['current_prediction']
    assert order['state'] == '待签回'

    # 行程按现用版验：候选版更大也不会被当成拦截依据
    in_range = world.post('/shadows/book-order', json={
        'run': 'SHD-9', 'heat': 545, 'thick': 5, 'target': 12})
    assert in_range.status_code == 200


def test_book_order_rejects_when_current_profile_out_of_travel(world):
    # 目标弯度超过弯模行程，即使现用版预测落在量程内也拒绝
    world.post('/shadows/open-run', json={
        'code': 'SHD-9', 'jig': 'CL-44', 'current_profile': 'PRO-11',
        'candidate_profile': 'PRO-24', 'target_count': 2})
    rejected = world.post('/shadows/book-order', json={
        'run': 'SHD-9', 'heat': 500, 'thick': 4, 'target': 40})
    assert rejected.status_code == 409
    with transaction() as conn:
        assert conn.scalar(select(shadow_orders.c.code).where(
            shadow_orders.c.run == 'SHD-9')) is None


def test_sign_order_counts_once_and_compares_when_full(world):
    world.post('/shadows/open-run', json={
        'code': 'SHD-9', 'jig': 'CL-44', 'current_profile': 'PRO-11',
        'candidate_profile': 'PRO-24', 'target_count': 2})
    first = world.post('/shadows/book-order', json={
        'run': 'SHD-9', 'heat': 500, 'thick': 4, 'target': 10}).json()
    second = world.post('/shadows/book-order', json={
        'run': 'SHD-9', 'heat': 470, 'thick': 3, 'target': 11}).json()

    signed = world.post('/shadows/sign-order', json={
        'order': first['code'], 'measured': 8.0})
    assert signed.status_code == 200, signed.text
    assert signed.json()['collected'] == 1
    assert signed.json()['status'] == '跟跑中'

    # 同单重试不改写读数、不重复计入
    retry = world.post('/shadows/sign-order', json={
        'order': first['code'], 'measured': 9.9})
    assert retry.status_code == 200
    assert retry.json()['collected'] == 1
    with transaction() as conn:
        run = dict(conn.execute(select(shadow_runs).where(
            shadow_runs.c.code == 'SHD-9')).mappings().one())
        stored = conn.scalar(select(shadow_orders.c.measured).where(
            shadow_orders.c.code == first['code']))
    assert run['collected'] == 1
    assert stored == 8.0

    full = world.post('/shadows/sign-order', json={
        'order': second['code'], 'measured': 7.0})
    assert full.status_code == 200, full.text
    result = full.json()
    assert result['collected'] == 2
    assert result['run']['state'] == '已收尾'
    assert result['decision'] in ('候选接替现用版', '保留现用版')
    assert result['current_mae'] is not None and result['candidate_mae'] is not None


def test_signed_orders_compare_against_sealed_predictions_not_new_ones(world):
    """已排位的单按原依据签回：切换后核算仍用封存值。"""
    world.post('/shadows/open-run', json={
        'code': 'SHD-9', 'jig': 'CL-44', 'current_profile': 'PRO-11',
        'candidate_profile': 'PRO-24', 'target_count': 1})
    order = world.post('/shadows/book-order', json={
        'run': 'SHD-9', 'heat': 500, 'thick': 4, 'target': 10}).json()
    # 手工把在役版本改成候选，模拟批次收尾后的切换
    with transaction() as conn:
        conn.execute(jigs.update().where(jigs.c.code == 'CL-44').values(current_profile='PRO-24'))
    signed = world.post('/shadows/sign-order', json={
        'order': order['code'], 'measured': order['current_prediction']})
    assert signed.status_code == 200
    run = signed.json()
    # 实弯恰等于排位时的现用版预测，用封存值核算则现用版误差为零
    assert run['current_mae'] == 0.0
    assert run['run']['state'] == '已收尾'
