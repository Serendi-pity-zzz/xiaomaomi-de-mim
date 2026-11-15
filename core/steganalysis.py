"""C：隐写统计检测（LSB 值对卡方分析 + RS 辅助特征）。

模块只依赖 Pillow 与标准库；由组长在 core/service.py 中适配，不直接改前端协议。

核心方法
--------
对分析区域内的 RGB 样本统计 256 级直方图，把相邻灰度值 (2i, 2i+1) 看作一个
“值对”。LSB 替换保持值对总数不变，只会把样本在偶/奇两个值之间搬运：
未嵌入时两值通常相差很大，完全替换后接近相等（Westfeld 型值对效应）。

统计量采用经典卡方攻击的定义（每个值对只累计一项，等价于 Pearson 统计量的
一半）::

    r = Σ (n_even - n_odd)² / (2 * (n_even + n_odd))

再扣除全局载荷比特偏置项 ``2N(b - 0.5)²``（b 为区域内 LSB 为 1 的比例），
得到 ``r_adj``。文本载荷的 0/1 比例通常不是 0.5，若不扣除该项，全容量嵌入
也会被误判为“干净”。随后按经典惯例用自由度 k-1 的卡方上尾概率作为 0~1
分数 ``score``（越高越可疑）。该分数不是后验概率，也不是严格 p 值，阈值由
``steganalysis_calibration.json`` 中的实测校准数据给出。

RS 特征（Fridrich 型分组翻转，组大小 4，掩码 (0,1,1,0) 及其相反数）只作为
辅助证据输出，不参与判定：本项目载体的平坦色块与二维码 0/255 饱和值会破坏
RS 的模型假设，实测显示其统计量随载荷下降但无法单独给出稳定阈值。

局限见 ``LIMITATIONS`` 与 ``docs/C_隐写统计检测_算法与结果.md``。
"""
from __future__ import annotations

import hashlib
import json
import math
import platform
import sys
from pathlib import Path

from PIL import Image

__all__ = [
    'METHOD_CHI_SQUARE',
    'METHOD_RS',
    'DEFAULT_CALIBRATION_FILENAME',
    'LIMITATIONS',
    'analyze',
    'calibration_id',
    'chi_square_sf',
    'load_calibration',
    'rs_features',
]

METHOD_CHI_SQUARE = 'chi_square'
METHOD_RS = 'rs'
DEFAULT_CALIBRATION_FILENAME = 'steganalysis_calibration.json'
DEFAULT_THRESHOLD = 0.5
MIN_SAMPLES = 256
_CALIBRATION_SCHEMA = 'steganalysis-calibration/1'

LIMITATIONS = [
    'score 是卡方统计量的上尾分数，不是“含密概率”或后验概率。',
    '只能发现值对分布被均衡化的证据；秘密较短、位置置乱或自适应算法可能保持原分布而检测不到。',
    '区域内值对数量 k 很小时自由度低，灵敏度有限；区域选错或改用整图分析会稀释信号。',
    'LSB 已经近似随机的载体（噪声图、部分截图、二次保存图）与全量嵌入在统计上不可区分，可能误报。',
    '需约定并保护分析区域；本模块不推断区域，也不验证区域是否被裁剪或缩放。',
    'PNG 无损前提；JPEG、缩放、滤镜会改变值对统计，结论不适用。',
    '密钥只影响嵌入位置，不影响本统计检验；检测不需要密钥。',
]

# RS 辅助特征：组大小 4，固定掩码，提取端与本模块均按行优先、逐通道分组。
_RS_GROUP = 4
_RS_MASK = (0, 1, 1, 0)
_RS_NEG_MASK = tuple(-m for m in _RS_MASK)


# --------------------------------------------------------------------------
# 卡方分布上尾概率（正则化不完全 Gamma），避免引入 SciPy 依赖
# --------------------------------------------------------------------------
def _gammainc_series(a: float, x: float) -> float:
    """下不完全 Gamma 的级数展开 P(a, x)，要求 x < a + 1。"""
    ap = a
    total = 1.0 / a
    delta = total
    for _ in range(1000):
        ap += 1.0
        delta *= x / ap
        total += delta
        if abs(delta) <= abs(total) * 1e-15:
            break
    return total * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gammainc_continued_fraction(a: float, x: float) -> float:
    """上不完全 Gamma 的连分式 Q(a, x)，要求 x >= a + 1。"""
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) <= 1e-15:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def chi_square_sf(statistic: float, degrees_of_freedom: int) -> float:
    """自由度为 df 的卡方分布上尾概率 P(χ² >= statistic)。

    与 ``scipy.stats.chi2.sf`` 的误差在 1e-12 量级（见单元测试）。
    """
    if degrees_of_freedom <= 0:
        raise ValueError('自由度必须为正整数')
    if not math.isfinite(statistic):
        raise ValueError('统计量必须是有限数值')
    if statistic <= 0.0:
        return 1.0
    a = degrees_of_freedom / 2.0
    x = statistic / 2.0
    if x < a + 1.0:
        value = 1.0 - _gammainc_series(a, x)
    else:
        value = _gammainc_continued_fraction(a, x)
    return min(1.0, max(0.0, value))


# --------------------------------------------------------------------------
# 输入校验与分析区域
# --------------------------------------------------------------------------
def _require_image(image) -> Image.Image:
    if not isinstance(image, Image.Image):
        raise ValueError('image 必须是已打开的 Pillow 图像')
    return image.convert('RGB')


def _normalise_region(image: Image.Image, region):
    """返回 (x, y, w, h)；region=None 表示整幅图。"""
    width, height = image.size
    if region is None:
        return 0, 0, width, height, 'whole_image'
    if not isinstance(region, (tuple, list)) or len(region) != 4:
        raise ValueError('region 必须是 (x, y, width, height) 四元组')
    values = []
    for item in region:
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError('region 的四个分量都必须是整数')
        values.append(item)
    x, y, w, h = values
    if w <= 0 or h <= 0:
        raise ValueError('region 的 width 和 height 必须为正')
    if x < 0 or y < 0:
        raise ValueError('region 的 x、y 不能为负')
    if x + w > width or y + h > height:
        raise ValueError('region 超出图像边界')
    return x, y, w, h, 'region'


def _region_dict(x: int, y: int, w: int, h: int) -> dict:
    return {'x': x, 'y': y, 'width': w, 'height': h}


# --------------------------------------------------------------------------
# 值对统计
# --------------------------------------------------------------------------
def _histogram(data: bytes, stride: int = 1, offset: int = 0) -> tuple[list[int], int, int]:
    hist = [0] * 256
    ones = 0
    for index in range(offset, len(data), stride):
        value = data[index]
        hist[value] += 1
        ones += value & 1
    return hist, len(range(offset, len(data), stride)), ones


def _pair_statistics(hist: list[int]) -> dict:
    """经典卡方攻击统计量：只统计总数非零的值对。"""
    r = 0.0
    pairs = []
    for value in range(0, 256, 2):
        even_count = hist[value]
        odd_count = hist[value + 1]
        total = even_count + odd_count
        if total == 0:
            continue
        r += (even_count - odd_count) ** 2 / (2.0 * total)
        pairs.append({
            'values': [value, value + 1],
            'even': even_count,
            'odd': odd_count,
        })
    return {'r': r, 'pair_count': len(pairs), 'pairs': pairs}


def _chi_square_detail(hist: list[int], samples: int, ones: int) -> dict:
    stats = _pair_statistics(hist)
    pair_count = stats['pair_count']
    if samples <= 0:
        return {'ok': False, 'reason': '分析区域为空', 'pair_count': 0}
    if pair_count < 2:
        return {
            'ok': False,
            'reason': '区域内非空值对少于 2 个，无法进行卡方检验',
            'pair_count': pair_count,
            'classic_statistic': stats['r'],
        }
    if samples < MIN_SAMPLES:
        return {
            'ok': False,
            'reason': f'样本数 {samples} 少于最少 {MIN_SAMPLES}，统计量不可靠',
            'pair_count': pair_count,
            'classic_statistic': stats['r'],
        }
    if ones == 0 or ones == samples:
        return {
            'ok': False,
            'reason': '区域 LSB 全为 0 或全为 1，全局偏置修正退化，卡方检验不可判定',
            'pair_count': pair_count,
            'classic_statistic': stats['r'],
        }
    one_ratio = ones / samples
    bias = 2.0 * samples * (one_ratio - 0.5) ** 2
    adjusted = max(0.0, stats['r'] - bias)
    degrees_of_freedom = pair_count - 1
    score = chi_square_sf(adjusted, degrees_of_freedom)
    return {
        'ok': True,
        'classic_statistic': stats['r'],
        'bias_correction': bias,
        'statistic': adjusted,
        'lsb_one_ratio': one_ratio,
        'pair_count': pair_count,
        'degrees_of_freedom': degrees_of_freedom,
        'score': score,
        'pairs': stats['pairs'],
    }


# --------------------------------------------------------------------------
# RS 辅助特征（不参与判定）
# --------------------------------------------------------------------------
def _flip_one(value: int) -> int:
    """F1：0↔1, 2↔3, ..., 254↔255。"""
    return value ^ 1


def _flip_negative(value: int) -> int:
    """F-1：-1↔0, 1↔2, ...；0 与 255 无有效配对，保持原值。"""
    if value == 0 or value == 255:
        return value
    return value + 1 if value & 1 else value - 1


def _rs_counts_plane(values: bytes, mask: tuple[int, ...]) -> dict:
    regular = singular = unchanged = groups = 0
    for start in range(0, len(values) - _RS_GROUP + 1, _RS_GROUP):
        group = values[start:start + _RS_GROUP]
        base = abs(group[1] - group[0]) + abs(group[2] - group[1]) + abs(group[3] - group[2])
        flipped = []
        for value, m in zip(group, mask):
            if m == 1:
                flipped.append(_flip_one(value))
            elif m == -1:
                flipped.append(_flip_negative(value))
            else:
                flipped.append(value)
        changed = (abs(flipped[1] - flipped[0]) + abs(flipped[2] - flipped[1])
                   + abs(flipped[3] - flipped[2]))
        groups += 1
        if changed > base:
            regular += 1
        elif changed < base:
            singular += 1
        else:
            unchanged += 1
    return {'regular': regular, 'singular': singular, 'unchanged': unchanged, 'groups': groups}


def rs_features(image, region=None) -> dict:
    """RS 辅助特征。返回计数、比例与 d = R - S；不给出嵌入率估计。

    仅作为辅助证据：本项目载体的平坦色块和 0/255 饱和值使 RS 的理论假设不成立，
    模块不据其做判定，也不报告未经检验的“嵌入率”。
    """
    image = _require_image(image)
    x, y, w, h, scope = _normalise_region(image, region)
    plane = image.crop((x, y, x + w, y + h)).tobytes()
    channels = {}
    total = {'regular_m': 0, 'singular_m': 0, 'regular_neg': 0, 'singular_neg': 0, 'groups': 0}
    for channel, name in enumerate('RGB'):
        values = plane[channel::3]
        positive = _rs_counts_plane(values, _RS_MASK)
        negative = _rs_counts_plane(values, _RS_NEG_MASK)
        groups = positive['groups']
        channels[name] = {
            'groups': groups,
            'r_m': positive['regular'] / groups,
            's_m': positive['singular'] / groups,
            'r_neg': negative['regular'] / groups,
            's_neg': negative['singular'] / groups,
            'd_m': (positive['regular'] - positive['singular']) / groups,
            'd_neg': (negative['regular'] - negative['singular']) / groups,
        }
        total['regular_m'] += positive['regular']
        total['singular_m'] += positive['singular']
        total['regular_neg'] += negative['regular']
        total['singular_neg'] += negative['singular']
        total['groups'] += groups
    groups = total['groups']
    return {
        'method': METHOD_RS,
        'usage': 'auxiliary_only',
        'analysis_scope': scope,
        'region': _region_dict(x, y, w, h),
        'group_size': _RS_GROUP,
        'mask': list(_RS_MASK),
        'channels': channels,
        'pooled': {
            'groups': groups,
            'r_m': total['regular_m'] / groups if groups else None,
            's_m': total['singular_m'] / groups if groups else None,
            'r_neg': total['regular_neg'] / groups if groups else None,
            's_neg': total['singular_neg'] / groups if groups else None,
            'd_m': (total['regular_m'] - total['singular_m']) / groups if groups else None,
            'd_neg': (total['regular_neg'] - total['singular_neg']) / groups if groups else None,
        },
        'note': ('RS 仅作辅助特征，不参与判定；本项目载体的平坦色块与 0/255 饱和值'
                 '破坏 RS 模型假设，且未实现经独立验证的嵌入率估计。'),
    }


# --------------------------------------------------------------------------
# 校准文件
# --------------------------------------------------------------------------
def _canonical_json(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def calibration_id(calibration: dict) -> str:
    data = {key: value for key, value in calibration.items() if key != 'calibration_id'}
    return 'sha256:' + hashlib.sha256(_canonical_json(data).encode('utf-8')).hexdigest()


def load_calibration(path=None) -> dict:
    """读取并校验校准文件；calibration_id 不匹配时拒绝加载。"""
    target = Path(path) if path is not None else Path(__file__).with_name(DEFAULT_CALIBRATION_FILENAME)
    try:
        calibration = json.loads(target.read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise ValueError(f'找不到卡方检测校准文件：{target}') from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f'校准文件不是有效 JSON：{target}') from exc
    if calibration.get('schema') != _CALIBRATION_SCHEMA:
        raise ValueError('校准文件 schema 不受支持')
    expected = calibration_id(calibration)
    if calibration.get('calibration_id') != expected:
        raise ValueError('校准文件校验失败：calibration_id 不匹配，请重新生成')
    return calibration


def _threshold_from(calibration: dict) -> float:
    raw = calibration.get('threshold')
    if not isinstance(raw, (int, float)) or isinstance(raw, bool) or not 0.0 < float(raw) <= 1.0:
        raise ValueError('校准文件中的 threshold 必须是 (0, 1] 内的数值')
    return float(raw)


def environment_summary() -> dict:
    return {
        'python': sys.version.split()[0],
        'pillow': getattr(Image, '__version__', None) or 'unknown',
        'platform': platform.platform(),
    }


# --------------------------------------------------------------------------
# 对外入口
# --------------------------------------------------------------------------
def analyze(image, region=None, method: str = METHOD_CHI_SQUARE, *,
            threshold=None, calibration_path=None, include_rs: bool = False) -> dict:
    """分析图像（或指定区域）的 LSB 值对统计特征。

    参数
    ----
    image : PIL.Image
        任意模式，内部转换为 RGB。
    region : (x, y, width, height) | None
        左上原点、右下边界不包含；None 表示整幅图。
    method : str
        ``"chi_square"`` 给出检测判定；``"rs"`` 返回 RS 辅助特征，判定固定为
        inconclusive（RS 不参与本项目判定，原因见文档）。
    threshold : float | None
        覆盖校准阈值，用于实验对比；默认读取校准文件。
    calibration_path : str | Path | None
        自定义校准文件路径（默认与模块同目录）。
    include_rs : bool
        为 True 时在 ``details["rs"]`` 中附带 RS 辅助特征（不参与判定）。

    返回
    ----
    dict
        可直接 JSON 序列化；含 method/statistic/score/threshold/decision/
        calibration_id/limitations 等服务层约定字段。
    """
    if method == METHOD_RS:
        features = rs_features(image, region)
        return {
            'method': METHOD_RS,
            'usage': 'auxiliary_only',
            'analysis_scope': features['analysis_scope'],
            'region': features['region'],
            'statistic': None,
            'score': None,
            'threshold': None,
            'decision': 'inconclusive',
            'calibration_id': None,
            'detail': ('RS 仅作辅助特征，不用于判定：本项目载体的平坦色块与 0/255 '
                       '饱和值破坏 RS 模型假设，且未实现经独立验证的嵌入率估计。'),
            'details': {'rs': features},
            'limitations': list(LIMITATIONS),
        }
    if method != METHOD_CHI_SQUARE:
        raise ValueError('method 仅支持 chi_square 或 rs')

    image = _require_image(image)
    x, y, w, h, scope = _normalise_region(image, region)

    calibration = None
    calibration_error = None
    if threshold is None:
        calibration = load_calibration(calibration_path)
        used_threshold = _threshold_from(calibration)
        used_calibration_id = calibration['calibration_id']
        threshold_source = 'calibration'
    else:
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
            raise ValueError('threshold 必须是数值')
        if not 0.0 < float(threshold) <= 1.0:
            raise ValueError('threshold 必须在 (0, 1] 内')
        used_threshold = float(threshold)
        threshold_source = 'manual'
        try:
            calibration = load_calibration(calibration_path)
            used_calibration_id = calibration['calibration_id']
        except ValueError as exc:
            calibration_error = str(exc)
            used_calibration_id = 'manual'

    crop = image.crop((x, y, x + w, y + h))
    data = crop.tobytes()
    hist, samples, ones = _histogram(data)
    detail = _chi_square_detail(hist, samples, ones)

    result = {
        'method': METHOD_CHI_SQUARE,
        'method_detail': 'chi_square_bias_adjusted',
        'analysis_scope': scope,
        'region': _region_dict(x, y, w, h),
        'samples': samples,
        'threshold': used_threshold,
        'threshold_source': threshold_source,
        'calibration_id': used_calibration_id,
        'limitations': list(LIMITATIONS),
        'details': {'pair_count': detail.get('pair_count'), 'classic_statistic': detail.get('classic_statistic')},
    }
    if calibration is not None:
        result['calibration_created'] = calibration.get('created')
    if calibration_error is not None:
        result['calibration_note'] = calibration_error

    if include_rs:
        result['details']['rs'] = rs_features(image, (x, y, w, h) if scope == 'region' else None)

    if not detail['ok']:
        result.update({
            'statistic': None,
            'score': None,
            'decision': 'inconclusive',
            'detail': f"无法判定：{detail['reason']}",
        })
        result['details'].update(detail)
        return result

    score = detail['score']
    suspicious = score >= used_threshold
    result.update({
        'statistic': detail['statistic'],
        'score': score,
        'decision': 'suspicious' if suspicious else 'clean',
        'detail': None,
    })
    result['details'].update({
        'classic_statistic': detail['classic_statistic'],
        'bias_correction': detail['bias_correction'],
        'lsb_one_ratio': detail['lsb_one_ratio'],
        'pair_count': detail['pair_count'],
        'degrees_of_freedom': detail['degrees_of_freedom'],
        'pairs': detail['pairs'],
        'per_channel': _per_channel_details(data),
    })
    if suspicious:
        result['detail'] = (
            f"卡方分数 {score:.4f} ≥ 阈值 {used_threshold:.2f}：区域内 LSB 值对分布"
            '接近均衡，与 LSB 替换的统计特征一致。该结果只是检测证据，'
            '不能据此断言存在秘密，也不能给出“含密概率”。'
        )
    else:
        result['detail'] = (
            f"卡方分数 {score:.4f} < 阈值 {used_threshold:.2f}：未发现值对被均衡化的证据。"
            '不能据此证明图像未嵌入秘密：小载荷、位置置乱或自适应算法可能保持原分布。'
        )
    return result


def _per_channel_details(data: bytes) -> list[dict]:
    """三通道分别给出统计量，作为诊断信息（未做多重比较校正）。"""
    details = []
    for channel, name in enumerate('RGB'):
        hist, samples, ones = _histogram(data, stride=3, offset=channel)
        entry = {'channel': name, 'samples': samples}
        stats = _pair_statistics(hist)
        entry['pair_count'] = stats['pair_count']
        entry['classic_statistic'] = stats['r']
        if stats['pair_count'] >= 2 and samples >= MIN_SAMPLES and ones not in (0, samples):
            pair_count = stats['pair_count']
            one_ratio = ones / samples
            bias = 2.0 * samples * (one_ratio - 0.5) ** 2
            adjusted = max(0.0, stats['r'] - bias)
            entry['statistic'] = adjusted
            entry['score'] = chi_square_sf(adjusted, pair_count - 1)
        else:
            entry['statistic'] = None
            entry['score'] = None
        details.append(entry)
    return details
