# std.rnnn — speech denoise model for ffmpeg `arnndn`

- Source: https://raw.githubusercontent.com/richardpl/arnndn-models/master/std.rnnn
  (downloaded 2026-11-05, SHA-256 `6b8943dc4a9b6b24425873992a44f29c0577503276456af46a8854774faeb294`)
- The repo README says std.rnnn is the model originally bundled with Xiph RNNoise
  (https://github.com/xiph/rnnoise, BSD-3-Clause). The arnndn-models repo itself
  has no LICENSE file, so only this Xiph model is bundled, not the others.
- Used by `.claude/skills/baoben-edit/scripts/voice.py`.

# face_detection_yunet_2023mar.onnx — face detector for `retouch.py`

- Source: OpenCV Zoo `models/face_detection_yunet/face_detection_yunet_2023mar.onnx`
  (git LFS, fetched via media.githubusercontent.com 2026-11-06),
  SHA-256 `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`, 232,589 bytes.
- License: MIT (OpenCV Zoo YuNet). Loaded with `cv2.FaceDetectorYN` (opencv-python-headless ≥ 4.8;
  tested with 5.0.0.93).
