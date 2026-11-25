from sqlalchemy import Boolean, CheckConstraint, Column, Float, ForeignKey, Integer, JSON, String, Table

from core.db import metadata


jigs = Table('jigs', metadata,
    Column('code', String(64), primary_key=True),
    Column('spread', Float, nullable=False),
    Column('max_throw', Float, nullable=False),
    Column('calibrated', Boolean, nullable=False),
    # 该弯模当前在用的曲线版本（跟跑候选接替后在此改指），空表示尚未登记
    Column('current_profile', String(160), nullable=True),
    CheckConstraint('spread > 0'),
    CheckConstraint('max_throw > 0'),
)
