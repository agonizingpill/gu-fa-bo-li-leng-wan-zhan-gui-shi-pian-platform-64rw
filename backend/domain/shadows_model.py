from sqlalchemy import CheckConstraint, Column, DateTime, Float, ForeignKey, Integer, String, Table

from core.db import metadata


# 弯模换曲线前的跟跑批次：复核员选定弯模、现用版、候选版和观察单数。
# 收足观察单后用同批实弯比较两版平均绝对误差，候选更准才接替现用版。
shadow_runs = Table('shadow_runs', metadata,
    Column('code', String(64), primary_key=True),
    Column('jig', String(160), ForeignKey('jigs.code'), nullable=False),
    Column('current_profile', String(160), ForeignKey('profiles.code'), nullable=False),
    Column('candidate_profile', String(160), ForeignKey('profiles.code'), nullable=False),
    # 观察单数：需要收足的跟跑签回单数
    Column('target_count', Integer, nullable=False),
    Column('state', String(160), nullable=False),
    # 已签回的跟跑单数（每单只计一次，重试不累加）
    Column('collected', Integer, nullable=False, default=0),
    Column('current_mae', Float, nullable=True),
    Column('candidate_mae', Float, nullable=True),
    Column('decision', String(160), nullable=True),
    Column('opened_at', DateTime, nullable=False),
    Column('decided_at', DateTime, nullable=True),
    CheckConstraint('target_count between 1 and 20'),
    CheckConstraint('collected >= 0'),
)

# 跟跑单：排位时按现用版验行程，并同时封存两版对该工况的预测；
# 签回时填实弯，重试不重复计入观察单数。
shadow_orders = Table('shadow_orders', metadata,
    Column('code', String(64), primary_key=True),
    Column('run', String(64), ForeignKey('shadow_runs.code'), nullable=False),
    Column('jig', String(160), ForeignKey('jigs.code'), nullable=False),
    Column('heat', Float, nullable=False),
    Column('thick', Float, nullable=False),
    Column('target', Float, nullable=False),
    # 排位当刻锁定的在役版本、两版封存预测与当时的行程上限，签回按此原依据核算
    Column('basis_profile', String(160), ForeignKey('profiles.code'), nullable=False),
    Column('basis_prediction', Float, nullable=False),
    Column('current_prediction', Float, nullable=False),
    Column('candidate_prediction', Float, nullable=False),
    Column('basis_throw', Float, nullable=False),
    Column('sealed_at', DateTime, nullable=False),
    Column('measured', Float, nullable=True),
    Column('signed_at', DateTime, nullable=True),
    Column('state', String(160), nullable=False),
    CheckConstraint('heat > 0'),
    CheckConstraint('thick > 0'),
    CheckConstraint('target > 0'),
    CheckConstraint('measured is null or measured >= 0'),
)
