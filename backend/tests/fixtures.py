import pytest


@pytest.fixture()
def world(client):
    """一套可复算的两版曲线、一副已检定弯模与一条在途跟跑批次。"""
    from sqlalchemy import insert
    from core.db import transaction
    from domain.curves import fit_bundle
    from domain.jigs_model import jigs
    from domain.coupons_model import coupons
    from domain.profiles_model import profiles
    from domain.work_orders_model import work_orders

    # 用确定性岭回归造两版可复算参数：弱正则（现用）与强正则（候选）
    history = [{'heat': 410 + i * 9, 'thick': 2 + i % 4, 'target': 9 + i % 5,
                'measured': 4.0 + i * 0.35} for i in range(20)]
    current_curve = fit_bundle(history, alpha=0.01)
    candidate_curve = fit_bundle(history, alpha=0.9)

    with transaction() as conn:
        conn.execute(insert(jigs).values(code='CL-44', spread=180, max_throw=32,
                                         calibrated=True, current_profile='PRO-11'))
        conn.execute(insert(jigs).values(code='CL-18', spread=115, max_throw=8,
                                         calibrated=True, current_profile=None))
        conn.execute(insert(coupons).values(code='GP-00', jig='CL-44', heat=410, thick=2,
                                            target=9, measured=3.5, locked=True))
        conn.execute(insert(profiles).values(code='PRO-11', coupon='GP-00', prediction=7.6,
                                             mae=0.4, curve=current_curve, token='tok-11'))
        conn.execute(insert(profiles).values(code='PRO-24', coupon='GP-00', prediction=7.7,
                                             mae=0.3, curve=candidate_curve, token='tok-24'))
        conn.execute(insert(work_orders).values(code='JOB-21', profile='PRO-11', jig='CL-44',
                                                slot='11-24 09:30', quantity=2, state='待打样'))
    return client
