# English poster content draft

This is text only. Apply it to the official AMD one-page PPT template when supplied. The final printed poster must omit team and school information as required by Section Six of the guide.

## Title

Complete EfficientAD Inference on a Zynq 7020 FPGA

## Problem

Visual anomaly inspection of small white nylon tie mounts under controlled imaging conditions.

## System

A reusable INT8 HLS engine executes all 22 convolution stages with activation and pooling, plus seven bilinear resize stages. The Cortex A9 dispatches layers and computes the final anomaly score. A local interface accepts images and displays board-generated anomaly responses.

## Measured results

- PL clock 125 MHz; setup slack +0.175 ns and hold slack +0.038 ns.
- Kernel calls total 1.484 seconds per image; overlapping post-processing reduces kernel time by 17.0 percent against the PE40 serial schedule.
- 203 DSPs and 57 BRAM36 tiles; two uploaded-image maps match the exact INT8 reference pixel by pixel.
- 31 C RTL cases and 58 full-model stage CRC checks passed.

## Evaluation scope

The two embedded examples are calibration fixtures, not an independent accuracy benchmark. The historical FP32 holdout table contains 32 correct classifications among 33 successfully localized images and two additional localization failures. A fresh retrospective evaluation covers 284 crop records across four sets (224 distinct image hashes). INT8 accuracy is 96.97% on the early 33-image crop set but 66.67% on the expanded 48-image set, with all 16 normal images falsely flagged. Seventy-five held-out crop inputs, excluding calibration objects D19 and N17, are checked on the board against complete reference maps. These previously reviewed datasets are not a new blind test.

## Reproducibility

Source code, frozen weights, simulation evidence, routed reports, board artifacts, reusable validation tools and build instructions are included in the project package.
