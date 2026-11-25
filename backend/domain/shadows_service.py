from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func, select

from core.records import get, insert, need, update
from domain.curves import predict, recomputable
from domain.jigs_model import jigs
from domain.profiles_model import profiles
from domain.shadows_model import shadow_orders, shadow_runs

# 跟跑批次状态
RUNNING = '跟跑中'
CLOSED = '已收尾'
# 跟跑单状态
WAITING = '待签回'
SIGNED = '已签回'
# 收尾结论
REPLACED = '候选接替现用版'
KEPT = '保留现用版'


def _now():
    return datetime.now(timezone.utc)


def _usable(profile, label):
    need(recomputable(profile['curve']), f'{label} {profile["code"]} 缺少可复算参数，不能参与跟跑')


def open_run(conn, user, data):
    """复核员选定弯模、现用版、候选版和观察单数，开一批跟跑。"""
    jig = get(conn, jigs, data.jig, lock=True)
    need(jig['calibrated'], '该机位弯模尚未检定')
    need(data.current_profile != data.candidate_profile, '现用版与候选版不能相同')
    _usable(get(conn, profiles, data.current_profile), '现用版')
    _usable(get(conn, profiles, data.candidate_profile), '候选版')
    # 现用版须与该弯模在役版本一致；弯模尚未登记在役版本时以本次为准登记。
    if jig['current_profile'] is None:
        update(conn, jigs, data.jig, current_profile=data.current_profile)
    else:
        need(jig['current_profile'] == data.current_profile, '所选现用版与该弯模在役版本不符')
    active = conn.execute(select(shadow_runs.c.code).where(
        shadow_runs.c.jig == data.jig, shadow_runs.c.state == RUNNING)).scalar()
    need(active is None, '该弯模已有未收尾的跟跑批次')
    return insert(conn, shadow_runs, code=data.code, jig=data.jig,
                  current_profile=data.current_profile, candidate_profile=data.candidate_profile,
                  target_count=data.target_count, state=RUNNING, collected=0,
                  current_mae=None, candidate_mae=None, decision=None,
                  opened_at=_now(), decided_at=None)


def book_order(conn, user, data):
    """按现用版验行程，同时封存两版对该工况的预测；校验与委托依据用同一版。"""
    # 统一按 弯模 → 批次 顺序加锁，使批次切换与排位互斥。
    head = get(conn, shadow_runs, data.run)
    jig = get(conn, jigs, head['jig'], lock=True)
    run = get(conn, shadow_runs, data.run, lock=True)
    need(run['state'] == RUNNING, '跟跑批次已收尾，不能再排位')
    # 锁定弯模后读取的在役版本必须仍是批次登记的那一版，否则说明已被切换。
    need(jig['current_profile'] == run['current_profile'],
         '该弯模现用版已切换，此跟跑批次失效，不能再排位')
    need(jig['calibrated'], '该机位弯模尚未检定')
    need(350 <= data.heat <= 650 and 1.5 <= data.thick <= 10, '超出试制保温或片厚范围')
    need(data.target > 0, '目标弯度须大于零')
    current = get(conn, profiles, run['current_profile'])
    candidate = get(conn, profiles, run['candidate_profile'])
    _usable(current, '现用版')
    _usable(candidate, '候选版')
    point = {'heat': data.heat, 'thick': data.thick, 'target': data.target}
    current_prediction = predict(current['curve'], point)
    candidate_prediction = predict(candidate['curve'], point)
    # 行程按现用版校验，委托依据（版本、预测、行程）也一并锁定这一版。
    need(max(current_prediction, data.target) <= jig['max_throw'], '夹具有效行程不足，机位未占用')
    # 观察单数即本批排位上限，保证收满时不再有未签回的单被落下。
    booked = conn.execute(select(func.count()).select_from(shadow_orders).where(
        shadow_orders.c.run == run['code'])).scalar()
    need(booked < run['target_count'], '本批观察单数已排满，不能再排位')
    code = data.code or 'SH-' + uuid4().hex[:10]
    return insert(conn, shadow_orders, code=code, run=run['code'], jig=run['jig'],
                  heat=data.heat, thick=data.thick, target=data.target,
                  basis_profile=run['current_profile'], basis_prediction=current_prediction,
                  current_prediction=current_prediction, candidate_prediction=candidate_prediction,
                  basis_throw=jig['max_throw'],
                  sealed_at=_now(), measured=None, signed_at=None, state=WAITING)


def sign_order(conn, user, data):
    """签回跟跑单实弯；重试不重复计入，已排位的单按原依据（封存预测）核算。"""
    head = get(conn, shadow_orders, data.order)
    # 与切换并发：先锁弯模，再锁批次，最后锁单据；三把行锁把同批签回串行化。
    jig = get(conn, jigs, head['jig'], lock=True)
    run = get(conn, shadow_runs, head['run'], lock=True)
    order = get(conn, shadow_orders, data.order, lock=True)
    # 同一单据重试：首次读数已落账就直接回放，不改写读数、不重复计入观察单数。
    if order['state'] == SIGNED:
        return _summary(run, order)
    need(data.measured >= 0, '实弯不能为负')
    # 已排位的单按原依据签回：行程上限取排位时锁定的值，不再受后续重校影响。
    need(data.measured <= order['basis_throw'], '实弯超过排位时的弯模行程')
    need(run['state'] == RUNNING, '跟跑批次已收尾，不能再签回')
    signed = update(conn, shadow_orders, data.order, measured=data.measured,
                    signed_at=_now(), state=SIGNED)
    collected = run['collected'] + 1
    fields = {'collected': collected}
    # 收足观察单才用同批实弯比较两版平均绝对误差；候选更准才接替现用版。
    if collected >= run['target_count']:
        batch = conn.execute(select(shadow_orders).where(
            shadow_orders.c.run == run['code'],
            shadow_orders.c.measured.is_not(None))).mappings().all()
        current_mae = round(sum(abs(row['measured'] - row['current_prediction']) for row in batch) / len(batch), 3)
        candidate_mae = round(sum(abs(row['measured'] - row['candidate_prediction']) for row in batch) / len(batch), 3)
        replaced = candidate_mae < current_mae
        fields.update(state=CLOSED, current_mae=current_mae, candidate_mae=candidate_mae,
                      decision=REPLACED if replaced else KEPT, decided_at=_now())
        if replaced:
            # 与排位共用弯模行锁，切换后新排位看到的就是候选版。
            update(conn, jigs, jig['code'], current_profile=run['candidate_profile'])
    run = update(conn, shadow_runs, run['code'], **fields)
    return _summary(run, signed)


def _summary(run, order):
    # 顶层带上批次状态与结论，便于前端直接回显；明细保留在 run/order 中。
    return {'code': run['code'], 'status': run['decision'] or run['state'],
            'decision': run['decision'],
            'collected': run['collected'], 'target_count': run['target_count'],
            'current_mae': run['current_mae'], 'candidate_mae': run['candidate_mae'],
            'run': run, 'order': order}


def list_runs(conn):
    rows = [dict(row) for row in conn.execute(
        select(shadow_runs).order_by(shadow_runs.c.code)).mappings()]
    for row in rows:
        row['remaining'] = max(row['target_count'] - row['collected'], 0)
    return rows


def list_orders(conn, run=None):
    query = select(shadow_orders).order_by(shadow_orders.c.code)
    if run:
        query = query.where(shadow_orders.c.run == run)
    return [dict(row) for row in conn.execute(query).mappings()]
