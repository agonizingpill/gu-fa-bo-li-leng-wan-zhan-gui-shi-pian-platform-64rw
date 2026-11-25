from datetime import datetime, timezone

from domain import curves
from domain.jigs_model import jigs
from domain.coupons_model import coupons
from domain.profiles_model import profiles
from domain.work_orders_model import work_orders
from domain.shadows_model import shadow_orders, shadow_runs

# 演示试片：编号、保温温度、片厚、目标弯度、冷却弯度。
_COUPONS = [
    ('GP-00', 410, 2, 9, 3.5), ('GP-01', 419, 3, 10, 5.11), ('GP-02', 428, 4, 11, 6.84),
    ('GP-03', 437, 5, 12, 8.69), ('GP-04', 446, 2, 13, 7.7), ('GP-05', 455, 3, 9, 5.0),
    ('GP-06', 464, 4, 10, 6.67), ('GP-07', 473, 5, 11, 8.46), ('GP-08', 482, 2, 12, 7.65),
    ('GP-09', 491, 3, 13, 9.44), ('GP-10', 500, 4, 9, 6.5), ('GP-11', 509, 5, 10, 8.23),
    ('GP-12', 518, 2, 11, 7.6), ('GP-13', 527, 3, 12, 9.33), ('GP-14', 536, 4, 13, 11.18),
    ('GP-15', 545, 5, 9, 8.0), ('GP-16', 554, 2, 10, 7.55), ('GP-17', 563, 3, 11, 9.22),
    ('GP-18', 572, 4, 12, 11.01), ('GP-19', 581, 5, 13, 12.92),
]

# 两版可复算曲线参数（由 sklearn 管线在全量试片上导出）。
# PRO-11 为现用版（弱正则，保留温度线性项），PRO-30 为候选版（强正则，只留交互项）。
PRO_11_CURVE = {
    'features': ['heat', 'thick', 'target'],
    'means': [497.428571, 4.0, 10.857143, 250136.285714, 1994.857143, 5420.214286,
              16.857143, 43.642857, 120.0],
    'scales': [51.972128, 0.92582, 1.456863, 52002.342106, 537.50626, 1057.468553,
               6.998542, 12.245157, 32.204702],
    'coef': [0.22896, 0.0, 0.0, 0.0, 0.0, 1.636141, 0.135809, 0.503582, 0.0],
    'intercept': 8.257143,
    'terms': ['温度', '温度 目标弯度', '片厚^2', '片厚 目标弯度'],
    'held_out': 5,
    'bounds': {'heat': {'min': 410, 'max': 581}, 'thick': {'min': 2, 'max': 5},
               'target': {'min': 9, 'max': 13}},
}
PRO_30_CURVE = {
    'features': ['heat', 'thick', 'target'],
    'means': [497.428571, 4.0, 10.857143, 250136.285714, 1994.857143, 5420.214286,
              16.857143, 43.642857, 120.0],
    'scales': [51.972128, 0.92582, 1.456863, 52002.342106, 537.50626, 1057.468553,
               6.998542, 12.245157, 32.204702],
    'coef': [0.0, 0.0, 0.0, 0.0, 0.281368, 1.717191, 0.0, 0.271666, 0.0],
    'intercept': 8.257143,
    'terms': ['温度 片厚', '温度 目标弯度', '片厚 目标弯度'],
    'held_out': 5,
    'bounds': {'heat': {'min': 410, 'max': 581}, 'thick': {'min': 2, 'max': 5},
               'target': {'min': 9, 'max': 13}},
}

# 跟跑单工况：排位时按现用版验行程，同时封存两版预测。
# 已签回两单的实弯贴近候选版预测，留一单待签回以演示收尾判定。
_SHADOW_ORDERS = [
    ('SH-01', 500, 4, 10, 7.497), ('SH-02', 520, 4, 10, 7.863), ('SH-03', 470, 3, 11, None),
]


def _at(stamp):
    return datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc)


def _shadow_rows():
    rows = []
    for code, heat, thick, target, measured in _SHADOW_ORDERS:
        point = {'heat': heat, 'thick': thick, 'target': target}
        current = curves.predict(PRO_11_CURVE, point)
        rows.append({
            'code': code, 'run': 'SHD-01', 'jig': 'CL-44', 'heat': heat, 'thick': thick,
            'target': target, 'basis_profile': 'PRO-11', 'basis_prediction': current,
            'current_prediction': current,
            'candidate_prediction': curves.predict(PRO_30_CURVE, point),
            'basis_throw': 32.0,
            'sealed_at': _at('2026-11-24T06:30:00'), 'measured': measured,
            'signed_at': None if measured is None else _at('2026-11-24T07:00:00'),
            'state': '待签回' if measured is None else '已签回'})
    return rows


FIXTURES = [
    (jigs, [{'code': 'CL-44', 'spread': 180, 'max_throw': 32, 'calibrated': True,
             'current_profile': 'PRO-11'},
            {'code': 'CL-18', 'spread': 115, 'max_throw': 8, 'calibrated': True,
             'current_profile': None},
            {'code': 'CL-08', 'spread': 140, 'max_throw': 25, 'calibrated': False,
             'current_profile': None}]),
    (coupons, [{'code': code, 'jig': 'CL-44', 'heat': heat, 'thick': thick, 'target': target,
                'measured': measured, 'locked': True}
               for code, heat, thick, target, measured in _COUPONS]),
    (profiles, [{'code': 'PRO-11', 'coupon': 'GP-12', 'prediction': 7.638, 'mae': 0.115,
                 'curve': PRO_11_CURVE, 'token': 'initial-profile'},
                {'code': 'PRO-30', 'coupon': 'GP-12', 'prediction': 7.726, 'mae': 0.26,
                 'curve': PRO_30_CURVE, 'token': 'candidate-profile'}]),
    (work_orders, [{'code': 'JOB-21', 'profile': 'PRO-11', 'jig': 'CL-44',
                    'slot': '11-24 09:30', 'quantity': 2, 'state': '待打样'}]),
    (shadow_runs, [{'code': 'SHD-01', 'jig': 'CL-44', 'current_profile': 'PRO-11',
                    'candidate_profile': 'PRO-30', 'target_count': 3, 'state': '跟跑中',
                    'collected': 2, 'current_mae': None, 'candidate_mae': None,
                    'decision': None, 'opened_at': _at('2026-11-24T06:30:00'),
                    'decided_at': None}]),
    (shadow_orders, _shadow_rows()),
]
