from sqlalchemy import select

from core.queueing import submit, result
from core.records import get, insert, need, scan, update
from domain.jigs_model import jigs
from domain.coupons_model import coupons
from domain.curves import recomputable
from domain.profiles_model import profiles
from domain.work_orders_model import work_orders


def fit_curve(conn, user, data):
    coupon = get(conn, coupons, data.coupon)
    need(coupon['locked'], '试片尚未经过尺规见证')
    need(.001 <= data.penalty <= .3, '正则强度超出试制档范围')
    history = [item for item in scan(conn, coupons) if item['locked'] and item['code'] != data.coupon]
    need(len(history) >= 12, '已确认历史少于十二张')
    return submit(user, {'history':history,'coupon':coupon,'penalty':data.penalty})


def sign_profile(conn, user, data):
    run = result(user, data.token)
    target, metric = run['input']['coupon'], run['result']
    current = get(conn, coupons, target['code'])
    need(current == target, '试片与拟合快照不相容')
    need(metric['prediction'] > 0 and metric['mae'] < 5, '曲线超过台面验证误差预算')
    # 跟跑排位要按曲线复算两版预测，缺少参数的结果不能签注。
    need(recomputable(metric), '拟合结果缺少可复算参数，请重新发起拟合')
    # 随曲线归档可复算参数，跟跑批次排位时据此复算两版预测。
    curve = {'terms':metric['terms'], 'held_out':metric['held_out'], 'features':metric['features'],
             'means':metric['means'], 'scales':metric['scales'], 'coef':metric['coef'],
             'intercept':metric['intercept'], 'bounds':metric['bounds']}
    return insert(conn, profiles, code=data.code, coupon=target['code'], prediction=metric['prediction'],
        mae=metric['mae'], curve=curve, token=data.token)
