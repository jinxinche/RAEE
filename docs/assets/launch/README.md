# RAEE-Lite demonstration media

Captured on 9 November 2026 from source commit [`4704dc8`](https://github.com/jinxinche/RAEE/commit/4704dc85581fcbe5c4079196478ee8e8747abd24), using Python 3.11.16 on macOS ARM64.

- [40-second MP4](raee-demo-40s.mp4): H.264, 1280×720, 25 fps; no audio.
- [Animated GIF](raee-demo.gif): the same six scenes and reading pauses.
- [Social preview PNG](raee-social-preview.png): 1280×640, intended for GitHub repository Settings → Social preview. Committing this file does not install it as the repository's social preview.
- [English SRT](raee-demo.en.srt) and [简体中文字幕](raee-demo.zh-CN.srt): optional sidecar subtitles. Upload them alongside the MP4 where supported; they are not burned into the video.
- [Actual standard output](demo-output.txt), [capture metadata](demo-provenance.json) and [SHA-256 manifest](SHA256SUMS).
- [Static walkthrough and reproduction](../../../examples/DEMO.md), for readers who prefer text or reduced motion.

The video and GIF are typography slides and terminal-output replays of a successful local synthetic demonstration. Reading pauses are editorial; these are **not screen recordings or execution-time measurements**. The final state `OBSERVED_PASS` records a labelled check result, not semantic coverage or correctness. The example's `@` check is not a production email validator.

The capture metadata records the source revision, script digest and stdout digest. These are reproducibility notes, not signed or independently authenticated attestations. The manifest covers this directory's media, subtitles and capture files; it deliberately does not hash itself or this explanatory document.

To reproduce the state sequence, review the source and follow the installation steps in the main README, then run `python examples/run_demo.py`. Do not infer hosted cross-platform demo validation from this one local capture.

All assets here are original project materials under the repository's [MIT license](../../../LICENSE). No private project code, agent transcripts or account analytics appear in the media.
