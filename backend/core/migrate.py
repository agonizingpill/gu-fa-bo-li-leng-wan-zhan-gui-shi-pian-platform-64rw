"""演示库的最小幂等迁移：``metadata.create_all`` 不会给已存在的表补列，
这里先补建缺失的表，再对既有表执行 ADD COLUMN；全新库由 create_all 直接建出完整结构。"""
from sqlalchemy import inspect, text

from core.db import engine, metadata

COLUMN_PATCHES = {
    'jigs': [
        ('current_profile', 'VARCHAR(160)'),
    ],
}


def upgrade():
    # 先注册全部表模型并补建缺失的表（含新表 shadow_runs / shadow_orders）。
    from domain import jigs_model, coupons_model, profiles_model, work_orders_model  # noqa: F401
    from domain import shadows_model  # noqa: F401
    metadata.create_all(engine)
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, columns in COLUMN_PATCHES.items():
            if table not in existing:
                continue
            present = {column['name'] for column in inspector.get_columns(table)}
            for name, ddl in columns:
                if name not in present:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'))
