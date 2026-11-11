"""受限子进程：仅对数值 JSON 执行固定规模的 K-Means 最近中心计算。"""
import json
import math
import resource
import sys


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def predict(model, values):
    names = model.get('feature_names')
    means, scales = model.get('scale_mean'), model.get('scale_scale')
    lower, upper = model.get('feature_min'), model.get('feature_max')
    centers, radii = model.get('centers'), model.get('distance_p99')
    if model.get('format') != 'trusted-numeric-kmeans-v1' or not isinstance(names, list) or not 1 <= len(names) <= 16 or len(set(names)) != len(names):
        raise ValueError('schema')
    n = len(names)
    if any(not isinstance(name, str) or name not in values or not finite(values[name]) for name in names):
        raise ValueError('input')
    if any(not isinstance(row, list) or len(row) != n or not all(finite(item) for item in row) for row in (means, scales, lower, upper)):
        raise ValueError('parameters')
    if any(scale <= 0 or low > high for scale, low, high in zip(scales, lower, upper)):
        raise ValueError('bounds')
    if not isinstance(centers, list) or not 2 <= len(centers) <= 6 or not isinstance(radii, list) or len(radii) != len(centers):
        raise ValueError('centers')
    if any(not isinstance(row, list) or len(row) != n or not all(finite(item) for item in row) for row in centers) or any(not finite(radius) or radius < 0 for radius in radii):
        raise ValueError('centers')
    x = [values[name] for name in names]
    if any(value < low or value > high for value, low, high in zip(x, lower, upper)):
        return {'status': 'out_of_distribution'}
    normalized = [(value - mean) / scale for value, mean, scale in zip(x, means, scales)]
    distances = [math.sqrt(sum((value - center) ** 2 for value, center in zip(normalized, row))) for row in centers]
    index = min(range(len(distances)), key=distances.__getitem__)
    if distances[index] > radii[index]:
        return {'status': 'out_of_distribution'}
    return {'status': 'available', 'cluster': index}


def main():
    # 超时由父进程强制执行；输入规模和维度均有上限。
    resource.setrlimit(resource.RLIMIT_CPU, (1, 1))
    if sys.platform != 'darwin':
        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    raw = sys.stdin.buffer.read(1_100_001)
    if len(raw) > 1_100_000:
        raise ValueError('input_too_large')
    payload = json.loads(raw)
    result = predict(payload['model'], payload['features'])
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_bytes = peak if sys.platform == 'darwin' else peak * 1024
    if peak_bytes > 128 * 1024 * 1024:
        raise MemoryError('memory_budget_exceeded')
    result['peak_rss_bytes'] = peak_bytes
    print(json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print(json.dumps({'status': 'invalid_input'}))
        raise SystemExit(2)
