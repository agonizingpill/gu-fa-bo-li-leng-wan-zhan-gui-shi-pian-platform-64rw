# 古法玻璃冷弯展柜试片台

棠镜玻璃试制组保留每次冷却后的实弯读数，根据材料交互修订曲线并安排唯一试制机位。

## 现场工作与联系人

模拟客户为棠镜玻璃试制组。夹具登记、温区试片、交互项比较、打样委托；夹具有效行程不足拒排且不占机位。

- 弯模与行程 `jigs`，字段为 `spread`（台面跨度 mm）、`max_throw`（最大行程 mm）、`calibrated`（量具在校）、`current_profile`（当前在役曲线版本，跟跑接替后在此改指）。模型约束位于 `backend/domain/jigs_model.py`，规则位于 `jigs_service.py`。
- 温区试片 `coupons`，字段为 `jig`（弯模）、`heat`（保温温度 °C）、`thick`（片厚 mm）、`target`（目标弯度 mm）、`measured`（冷却弯度 mm）、`locked`（已确认）。模型约束位于 `backend/domain/coupons_model.py`，规则位于 `coupons_service.py`。
- 预测曲线签注 `profiles`，字段为 `coupon`（基准试片）、`prediction`（拟合弯度 mm）、`mae`（留出 MAE mm）、`curve`（改善说明，含可复算参数）、`token`（拟合编号）。模型约束位于 `backend/domain/profiles_model.py`，规则位于 `profiles_service.py`。
- 试制工位委托 `work_orders`，字段为 `profile`（依据）、`jig`（工位弯模）、`slot`（机位时段）、`quantity`（试片数）、`state`（状态）。模型约束位于 `backend/domain/work_orders_model.py`，规则位于 `work_orders_service.py`。
- 曲线跟跑批次 `shadow_runs`，字段为 `jig`（弯模）、`current_profile`（现用版）、`candidate_profile`（候选版）、`target_count`（观察单数）、`state`（跟跑中/已收尾）、`collected`（已签回单数）、`current_mae`/`candidate_mae`（两版平均绝对误差）、`decision`（收尾结论）。跟跑单 `shadow_orders`，字段为 `run`（批次）、`heat`/`thick`/`target`（工况）、`basis_profile`（排位时的在役版本）、`current_prediction`/`candidate_prediction`（封存的两版预测）、`basis_throw`（排位时行程上限）、`measured`（实弯）、`state`（待签回/已签回）。模型约束位于 `backend/domain/shadows_model.py`，规则位于 `shadows_service.py`。

团队为模拟的6 人打样组，负责展柜旧式玻璃的冷弯样件。

试制员分开记尺规、片厚和热区读数。换夹具后有效行程容易漏核，两个参数的互相影响难从单列趋势看出，打样回执难追到原试片。

夹具检定和历史试片进入比较工作台，打样师领取附试片依据的委托单。

### 一天的业务操作

1. 08:35 在 CL-08 上校验量具，记录 25 mm 行程。
2. 09:10 用 CL-44 测量 GP-NEW 的 4 mm 玻璃冷却弯度 8.4 mm。
3. 10:20 复核员查验尺规并确认 GP-NEW。
4. 11:10 以 0.035 正则强度计算温区拟合。
5. 13:00 签注 PRO-24，核对留出误差。
6. 14:10 CL-18 有效行程不足，拒绝机位委托；换用 CL-44。
7. 15:00 复核员在曲线页面为 CL-44 开一批跟跑（现用版 PRO-11、候选版 PRO-30、观察单数 3），排位并按现用版验行程，同时封存两版预测。
8. 16:00 逐单签回实弯；收足观察单后比较两版平均绝对误差，候选更准才接替现用版。
9. 16:20 核对 W-0302 完成打样。

## 启动

```sh
cp .env.example .env
docker compose up -d --build --wait
docker compose exec -T backend python -m scripts.seed_demo
```

打开 `http://127.0.0.1:18306`。FastAPI OpenAPI 在 `http://127.0.0.1:19306/docs`。
Compose 运行 Nginx、Python FastAPI、独立 Redis 消费进程、SQL 数据库和 Redis，SQL 与 Redis 使用命名卷。
本机开发时，在 Python 3.11 环境安装 `backend/requirements.txt` 后从 backend 目录运行 `uvicorn core.app:app`。须提供 `DATABASE_URL`、`REDIS_URL`、`JWT_SECRET`，`SEED_DEMO` 控制演示初始化。

| 演示账号 | 权限 |
|---|---|
| operator@demo.test | 提交领域记录和计算请求 |
| reviewer@demo.test | 提交记录并执行有业务约束的复核操作 |
| viewer@demo.test | 浏览业务台账 |

三个本地演示账号均使用 `DemoC0de!2026`。角色在 `backend/core/roles.py` 和 `frontend/src/store.js` 中声明。计算状态在 worker、queueing、API 和同一前端 store 中使用。

## 页面与接口

| 业务任务 | FastAPI 路由 | 页面 |
|---|---|---|
| 弯模与行程 | `/jigs` /jigs/calibrate | `frontend/src/pages/jigs.js` |
| 温区试片 | `/coupons` /coupons/record-coupon，/coupons/witness | `frontend/src/pages/coupons.js` |
| 预测曲线签注 | `/profiles` /profiles/fit-curve，/profiles/sign-profile | `frontend/src/pages/profiles.js` |
| 曲线跟跑 | `/shadows`、/shadows/orders，/shadows/open-run，/shadows/book-order，/shadows/sign-order | `frontend/src/pages/shadows.js` |
| 试制工位委托 | `/work_orders` /work_orders/book-jig，/work_orders/complete | `frontend/src/pages/work_orders.js` |

### 弯模换曲线前的跟跑

换曲线前先跟跑：复核员在曲线页面选弯模、现用版、候选版和观察单数，开一批跟跑（`/shadows/open-run`）。现用版须与该弯模在役版本一致；同一弯模同时只允许一批未收尾的跟跑。

1. **排位**（`/shadows/book-order`）填炉温、片厚和目标弯度。系统按**现用版**复算预测并验行程（`max(现用版预测, 目标弯度) ≤ 弯模行程`），同时封存两版对该工况的预测。行程校验与委托依据锁定同一版：单据记录排位时的在役版本、两版预测与行程上限，此后切换不再改写。本批排位不得超过观察单数。
2. **签回**（`/shadows/sign-order`）填实弯。同一单重试不改写读数、不重复计入观察单数；观察单数按已签回单据去重。
3. **收尾**：收足观察单后才用同批实弯比较两版平均绝对误差，候选版更准（严格小于）才接替现用版，弯模在役版本随之改指候选版，否则保留现用版。已排位的单始终按排位时的原依据核算。
4. **并发**：切换与排位共用弯模行锁。排位在锁内复核在役版本仍为批次登记的现用版，若已被切换则拒绝且不占用观察单数，避免行程校验与委托依据混用两版。

曲线参数随签注曲线一并存档（`curve` 中保存标准化参数与九项二次特征系数），`backend/domain/curves.py` 为纯标准库复算侧，排位时据此复算两版预测；缺少可复算参数的旧曲线不能参与跟跑。

SQL 实体与约束在 `backend/domain` 下维护。前端使用原生 ES modules。核心算子为 PolynomialFeatures + Lasso。算法按温度排序每四条留出一条；训练拟合二次多项式和标准化。报告使用 mm 和可复现特征系数。`work_orders` 与 `jigs` 的演进列由 `backend/core/migrate.py` 在启动时幂等补齐，新表随 `metadata.create_all` 直接建出。

后端测试在 `backend/tests`，用 SQLite 内存库与 fakeredis 运行：在 `backend` 目录执行 `python -m pytest`（先 `pip install -r backend/requirements-dev.txt` 装 `fakeredis`、`pytest`、`httpx`）。

数据为模拟试制记录。工单留在本地数据库供核查。

[MIT](LICENSE)
