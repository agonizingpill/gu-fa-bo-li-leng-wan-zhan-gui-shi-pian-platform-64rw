import threading

import pytest
from sqlalchemy import create_engine, event, insert, select

import core.db as db
from core.db import transaction
from domain.curves import fit_bundle
from domain.coupons_model import coupons
from domain.jigs_model import jigs
from domain.profiles_model import profiles
from domain.shadows_model import shadow_orders

RUN = {'code': 'SHD-9', 'jig': 'CL-44', 'current_profile': 'PRO-11',
       'candidate_profile': 'PRO-24', 'target_count': 5}


def _seed():
    history = [{'heat': 410 + i * 9, 'thick': 2 + i % 4, 'target': 9 + i % 5,
                'measured': 4.0 + i * 0.35} for i in range(20)]
    with transaction() as conn:
        conn.execute(insert(jigs).values(code='CL-44', spread=180, max_throw=32,
                                         calibrated=True, current_profile='PRO-11'))
        conn.execute(insert(coupons).values(code='GP-00', jig='CL-44', heat=410, thick=2,
                                            target=9, measured=3.5, locked=True))
        conn.execute(insert(profiles).values(code='PRO-11', coupon='GP-00', prediction=7.6,
                                             mae=0.4, curve=fit_bundle(history, 0.01), token='tok-11'))
        conn.execute(insert(profiles).values(code='PRO-24', coupon='GP-00', prediction=7.7,
                                             mae=0.3, curve=fit_bundle(history, 0.9), token='tok-24'))


@pytest.fixture()
def file_engine(tmp_path):
    """多连接文件库：WAL + busy timeout，模拟 Postgres 下的行锁等待。"""
    url = f'sqlite+pysqlite:///{tmp_path}/concurrency.db'
    engine = create_engine(url, connect_args={'timeout': 15, 'check_same_thread': False})

    @event.listens_for(engine, 'connect')
    def _wal(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute('PRAGMA journal_mode=WAL')
        cur.execute('PRAGMA busy_timeout=15000')
        cur.close()

    previous = db.engine
    db.engine = engine
    from domain import jigs_model, coupons_model, profiles_model, work_orders_model  # noqa: F401
    from domain import shadows_model  # noqa: F401
    db.metadata.create_all(engine)
    _seed()
    yield engine
    db.engine = previous
    engine.dispose()


class Client:
    """每个线程一条独立连接，模拟多人同时提交。"""

    def __enter__(self):
        from fastapi.testclient import TestClient
        from core.app import app
        from core import auth
        app.dependency_overrides[auth.actor] = lambda: {'sub': 'reviewer@demo.test', 'role': 'reviewer'}
        self._client = TestClient(app)
        self._client.__enter__()
        return self._client

    def __exit__(self, *exc):
        self._client.__exit__(*exc)


def _open_run(client):
    client.post('/shadows/open-run', json=RUN)


def test_concurrent_retry_signs_once(file_engine):
    """并发重复签回：同一单只计一次观察单数，另一请求被拒。"""
    with Client() as client:
        _open_run(client)
        order = client.post('/shadows/book-order', json={
            'run': 'SHD-9', 'heat': 500, 'thick': 4, 'target': 10}).json()

    barrier = threading.Barrier(2)
    outcomes = []

    def retry():
        with Client() as client:
            barrier.wait()
            outcomes.append(client.post('/shadows/sign-order', json={
                'order': order['code'], 'measured': 8.0}).status_code)

    threads = [threading.Thread(target=retry) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert outcomes == [200, 200]
    with transaction() as conn:
        assert conn.scalar(select(shadow_orders.c.measured).where(
            shadow_orders.c.code == order['code'])) == 8.0


def test_booking_during_switch_is_consistent(file_engine):
    """切换与排位并发：单据要么被切换挡下，要么按排位时的现用版整单落账。"""
    with Client() as client:
        _open_run(client)
    barrier = threading.Barrier(2)

    def book():
        with Client() as client:
            barrier.wait()
            client.post('/shadows/book-order', json={
                'run': 'SHD-9', 'heat': 500, 'thick': 4, 'target': 10})

    def switch():
        with Client() as client:
            barrier.wait()
            with transaction() as conn:
                conn.execute(jigs.update().where(jigs.c.code == 'CL-44').values(
                    current_profile='PRO-24'))

    threads = [threading.Thread(target=book), threading.Thread(target=switch)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    with transaction() as conn:
        rows = conn.execute(select(shadow_orders).where(
            shadow_orders.c.run == 'SHD-9')).mappings().all()
        jig = dict(conn.execute(select(jigs).where(
            jigs.c.code == 'CL-44')).mappings().one())
    for row in rows:
        # 依据与封存的现用版预测同源，绝不混成候选版
        assert row['basis_profile'] == 'PRO-11'
        assert row['current_prediction'] == row['basis_prediction']
    assert jig['current_profile'] == 'PRO-24'
