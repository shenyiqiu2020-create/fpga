"""Compare .npy or little-endian raw tensors with explicit numerical tolerances."""
import argparse
import json
import math
from pathlib import Path
import sys

from check_manifest import digest


def compare(expected_path, actual_path, dtype=None, atol=0., rtol=0.):
    import numpy as np
    if not all(math.isfinite(v) and v >= 0 for v in (atol, rtol)):
        raise ValueError('Tolerances must be finite and nonnegative')
    supported = {'int8', 'uint8', 'int16', 'uint16', 'int32', 'uint32', 'float32', 'float64'}
    def load(path):
        path = Path(path)
        if path.suffix.lower() == '.npy':
            array = np.load(path, mmap_mode='r', allow_pickle=False)
            if dtype is not None and array.dtype != np.dtype(dtype):
                raise ValueError('Requested dtype differs from .npy dtype')
        else:
            if dtype is None:
                raise ValueError('--dtype is required for raw binary files')
            dt = np.dtype(dtype).newbyteorder('<')
            if path.stat().st_size % dt.itemsize:
                raise ValueError('Raw file has a partial trailing element')
            array = np.memmap(path, dtype=dt, mode='r')
        if array.dtype.name not in supported:
            raise ValueError('Supported element types: '+', '.join(sorted(supported)))
        if not array.size:
            raise ValueError('Empty tensors are not accepted as a successful comparison')
        return array
    expected, actual = load(expected_path), load(actual_path)
    if expected.shape != actual.shape or expected.dtype != actual.dtype:
        raise ValueError('Tensor shape/dtype mismatch')
    if expected.dtype.kind in 'iu' and (atol or rtol):
        raise ValueError('Integer tensors require exact comparison; tolerances apply to floats')
    e, a = expected.reshape(-1), actual.reshape(-1)
    mismatches, nonfinite, maximum, first = 0, 0, 0., []
    for begin in range(0, e.size, 262144):
        x, y = np.asarray(e[begin:begin+262144]), np.asarray(a[begin:begin+262144])
        finite = np.isfinite(x) & np.isfinite(y)
        delta = np.abs(x.astype(np.float64)-y.astype(np.float64))
        valid_delta = delta[finite]
        if valid_delta.size:
            maximum = max(maximum, float(valid_delta.max()))
        bad = ~finite | (delta > atol+rtol*np.abs(x.astype(np.float64)))
        nonfinite += int((~finite).sum())
        mismatches += int(bad.sum())
        if len(first) < 8:
            first.extend((np.flatnonzero(bad)[:8-len(first)]+begin).tolist())
    return {'status':'PASS' if mismatches==0 else 'FAIL', 'elements':int(e.size),
            'shape':list(expected.shape), 'dtype':str(expected.dtype),
            'atol':atol,'rtol':rtol,'mismatches':mismatches,'nonfinite_elements':nonfinite,
            'max_abs_error_finite':maximum,'first_mismatch_flat_indices':first,
            'expected_sha256':digest(expected_path),'actual_sha256':digest(actual_path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('expected', type=Path)
    parser.add_argument('actual', type=Path)
    parser.add_argument('--dtype', choices=['int8','uint8','int16','uint16','int32','uint32','float32','float64'])
    parser.add_argument('--atol', type=float, default=0.)
    parser.add_argument('--rtol', type=float, default=0.)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        result = compare(args.expected,args.actual,args.dtype,args.atol,args.rtol)
        if args.output:
            args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    except (OSError,ValueError,ImportError) as exc:
        print(json.dumps({'status':'ERROR','error':str(exc)}))
        return 2
    print(json.dumps(result,indent=2))
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':
    sys.exit(main())
