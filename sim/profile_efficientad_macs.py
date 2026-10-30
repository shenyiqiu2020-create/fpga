"""Count convolution MACs for the pinned EfficientAD small architecture.

This mirrors get_pdn_small and get_autoencoder in the pinned upstream
``common.py`` (commit fcab5146f84ae17597044ad5ddf1656ccf805401).
It does not load PyTorch, weights, or images. One MAC means one multiply and
accumulate; pooling, interpolation, activation, and data movement are omitted.
Only the final feature width changes in the candidate: teacher/AE output C,
student output 2C. This is a theoretical architecture comparison, not a
latency or accuracy prediction.
"""

from __future__ import annotations

import argparse
import json


IMAGE_SIZE = 256


def _output_size(size: int, kernel: int, stride: int, padding: int) -> int:
    result = (size + 2 * padding - kernel) // stride + 1
    if result <= 0:
        raise ValueError("kernel exceeds the current feature map")
    return result


def _conv(layers: list[dict], height: int, width: int, in_channels: int,
          out_channels: int, kernel: int, stride: int = 1,
          padding: int = 0) -> tuple[int, int]:
    out_height = _output_size(height, kernel, stride, padding)
    out_width = _output_size(width, kernel, stride, padding)
    macs = (out_height * out_width * out_channels * in_channels
            * kernel * kernel)
    layers.append({
        "index": len(layers) + 1,
        "input_chw": [in_channels, height, width],
        "output_chw": [out_channels, out_height, out_width],
        "kernel": kernel,
        "stride": stride,
        "padding": padding,
        "macs": macs,
    })
    return out_height, out_width


def _pool(height: int, width: int) -> tuple[int, int]:
    return _output_size(height, 2, 2, 0), _output_size(width, 2, 2, 0)


def _pdn(out_channels: int) -> list[dict]:
    layers: list[dict] = []
    height = width = IMAGE_SIZE
    height, width = _conv(layers, height, width, 3, 128, 4)
    height, width = _pool(height, width)
    height, width = _conv(layers, height, width, 128, 256, 4)
    height, width = _pool(height, width)
    height, width = _conv(layers, height, width, 256, 256, 3)
    _conv(layers, height, width, 256, out_channels, 4)
    return layers


def _autoencoder(out_channels: int) -> list[dict]:
    layers: list[dict] = []
    height = width = IMAGE_SIZE
    in_channels = 3
    for channels in (32, 32, 64, 64, 64):
        height, width = _conv(layers, height, width, in_channels, channels,
                              4, stride=2, padding=1)
        in_channels = channels
    height, width = _conv(layers, height, width, 64, 64, 8)
    for upsample_size in (3, 8, 15, 32, 63, 127):
        height = width = upsample_size
        height, width = _conv(layers, height, width, 64, 64, 4, padding=2)
    height = width = 56
    height, width = _conv(layers, height, width, 64, 64, 3, padding=1)
    _conv(layers, height, width, 64, out_channels, 3, padding=1)
    return layers


def profile(out_channels: int) -> dict:
    """Return per-layer and total MACs for full three-branch EfficientAD."""
    if out_channels <= 0:
        raise ValueError("out_channels must be positive")
    models = {
        "teacher": _pdn(out_channels),
        "student": _pdn(2 * out_channels),
        "autoencoder": _autoencoder(out_channels),
    }
    if {tuple(layers[-1]["output_chw"][1:]) for layers in models.values()} != {(56, 56)}:
        raise AssertionError("branch output sizes must match")
    return {
        "out_channels": out_channels,
        "student_out_channels": 2 * out_channels,
        "models": {name: {
            "conv_count": len(layers),
            "macs": sum(layer["macs"] for layer in layers),
            "layers": layers,
        } for name, layers in models.items()},
        "total_conv_count": sum(len(layers) for layers in models.values()),
        "total_macs": sum(layer["macs"] for layers in models.values()
                          for layer in layers),
    }


def compare(baseline_channels: int = 384, candidate_channels: int = 192) -> dict:
    baseline = profile(baseline_channels)
    candidate = profile(candidate_channels)
    saved = baseline["total_macs"] - candidate["total_macs"]
    return {
        "input_chw": [3, IMAGE_SIZE, IMAGE_SIZE],
        "baseline": baseline,
        "candidate": candidate,
        "saved_macs": saved,
        "saved_fraction": saved / baseline["total_macs"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-channels", type=int, default=384)
    parser.add_argument("--candidate-channels", type=int, default=192)
    parser.add_argument("--json", action="store_true",
                        help="include every layer in machine-readable JSON")
    args = parser.parse_args()
    result = compare(args.baseline_channels, args.candidate_channels)
    if args.json:
        print(json.dumps(result, indent=2))
        return
    for label in ("baseline", "candidate"):
        case = result[label]
        print(f"{label}: feature channels={case['out_channels']}, "
              f"convolutions={case['total_conv_count']}, "
              f"MACs={case['total_macs'] / 1e9:.3f} G")
        for name, model in case["models"].items():
            print(f"  {name}: {model['conv_count']} convolutions, "
                  f"{model['macs'] / 1e9:.3f} GMac")
            for layer in model["layers"]:
                print(f"    {layer['index']:2} "
                      f"{layer['input_chw']} -> {layer['output_chw']} "
                      f"k{layer['kernel']} s{layer['stride']} "
                      f"p{layer['padding']}: {layer['macs'] / 1e9:.3f} GMac")
    print(f"saved: {result['saved_macs'] / 1e9:.3f} GMac "
          f"({result['saved_fraction']:.1%}); theoretical count only")


if __name__ == "__main__":
    main()
