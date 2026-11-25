"""可复算的二次曲线参数。

生产拟合仍由 ``domain.learning`` 的 sklearn Lasso 管线完成；本模块只依赖标准库，
按签注曲线随 ``curve`` 存档的标准化参数与系数，复算任意工况（炉温、片厚、目标弯度）
的弯度。跟跑批次排位时，两版预测都由这里复算后再封存，不依赖 worker 再算一次。

标准化发生在二次特征展开之后，因此 means/scales 长度为 9，与 sklearn 管线口径一致。
"""
FEATURES = ('heat', 'thick', 'target')
FEATURE_LABELS = ('温度', '片厚', '目标弯度')
TERM_COUNT = 9
PARAM_KEYS = ('means', 'scales', 'coef', 'intercept', 'bounds')


def _poly_terms(point):
    """二次（不含偏置）多项式特征，顺序与 PolynomialFeatures(degree=2) 对齐。"""
    x1, x2, x3 = point['heat'], point['thick'], point['target']
    return [
        x1, x2, x3,
        x1 * x1, x1 * x2, x1 * x3,
        x2 * x2, x2 * x3, x3 * x3,
    ]


def recomputable(curve):
    """旧版曲线只存改善说明，缺少复算参数时不能参与跟跑。"""
    if not isinstance(curve, dict) or not all(key in curve for key in PARAM_KEYS):
        return False
    return len(curve['means']) == TERM_COUNT and len(curve['scales']) == TERM_COUNT \
        and len(curve['coef']) == TERM_COUNT


def predict(curve, point):
    """按签注曲线参数复算工况（heat/thick/target）的弯度。"""
    expanded = _poly_terms(point)
    value = curve['intercept'] + sum(
        coef * ((term - mean) / scale)
        for coef, term, mean, scale in zip(curve['coef'], expanded, curve['means'], curve['scales']))
    return round(float(value), 3)


def in_training_range(curve, point):
    """工况的每个特征都落在该曲线训练样本的闭区间包络内。"""
    bounds = curve.get('bounds')
    if not bounds:
        return False
    return all(bounds[name]['min'] <= point[name] <= bounds[name]['max'] for name in FEATURES)


def term_labels():
    x1, x2, x3 = FEATURE_LABELS
    return [x1, x2, x3, f'{x1} {x1}', f'{x1} {x2}', f'{x1} {x3}',
            f'{x2} {x2}', f'{x2} {x3}', f'{x3} {x3}']


def _stats(values):
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    scale = variance ** 0.5
    if scale == 0:  # 与 sklearn StandardScaler 一致：常量列退化为 1。
        scale = 1.0
    return mean, scale


def _solve(matrix, vector):
    """高斯-约当消元求解线性方程组。"""
    size = len(vector)
    aug = [row[:] + [vector[i]] for i, row in enumerate(matrix)]
    for col in range(size):
        pivot = max(range(col, size), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-12:
            raise ValueError('曲线特征矩阵奇异，无法复算')
        aug[col], aug[pivot] = aug[pivot], aug[col]
        pivot_value = aug[col][col]
        aug[col] = [value / pivot_value for value in aug[col]]
        for r in range(size):
            if r == col:
                continue
            factor = aug[r][col]
            aug[r] = [a - factor * b for a, b in zip(aug[r], aug[col])]
    return [aug[i][-1] for i in range(size)]


def fit_bundle(rows, alpha=0.035):
    """演示数据用的确定性岭回归拟合，产物结构与 sklearn 管线导出一致。"""
    if len(rows) < 4:
        raise ValueError('已确认历史少于四张，无法拟合二次曲线')
    raw_columns = [[row[name] for row in rows] for name in FEATURES]
    design = [_poly_terms(row) for row in rows]
    targets = [row['measured'] for row in rows]
    means, scales = [], []
    for column in range(TERM_COUNT):
        mean, scale = _stats([row[column] for row in design])
        means.append(mean)
        scales.append(scale)
    standardized = [[(design[r][c] - means[c]) / scales[c] for c in range(TERM_COUNT)]
                    for r in range(len(rows))]
    gram = [[sum(standardized[r][i] * standardized[r][j] for r in range(len(rows)))
             for j in range(TERM_COUNT)] for i in range(TERM_COUNT)]
    for i in range(TERM_COUNT):
        gram[i][i] += alpha
    rhs = [sum(standardized[r][i] * targets[r] for r in range(len(rows)))
           for i in range(TERM_COUNT)]
    coef = _solve(gram, rhs)
    intercept = sum(targets) / len(rows) - sum(
        c * sum(row[i] for row in standardized) / len(rows) for i, c in enumerate(coef))
    bounds = {name: {'min': min(values), 'max': max(values)}
              for name, values in zip(FEATURES, raw_columns)}
    labels = term_labels()
    return {
        'features': list(FEATURES),
        'means': [round(value, 6) for value in means],
        'scales': [round(value, 6) for value in scales],
        'coef': [round(value, 6) for value in coef],
        'intercept': round(intercept, 6),
        'terms': [label for label, value in zip(labels, coef) if abs(value) > 1e-10],
        'bounds': bounds,
    }
