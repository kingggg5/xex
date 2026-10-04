# Third-party notices

Code or logic adapted from third-party sources. Libraries installed through npm or Cargo carry their own licence files and are not listed here.

## ClearWater6.1

- **Source:** https://github.com/SamG-Coder/ClearWater6.1 (`app.js`, the mobile adaptive render scale in `frame()`).
- **Licence:** MIT.
- **Adapted in:** `apps/client/src/render-scale-controller.mjs` (2026-10-02).
- **What was adapted:** the idea of the controller. A frame-time EMA (`avg * 0.94 + frameMs * 0.06`) is evaluated in windows (upstream: every 60 frames); the scale drops fast (−0.1) and climbs slowly (+0.05) between 0.5 and 1.
- **What was changed:**
  - thresholds are relative to the caller's target frame interval instead of fixed 25 ms and 12 ms;
  - GPU time is used when the host has it;
  - a missed-frame ratio is the down signal for vsync-capped frames;
  - climbing uses predicted-cost hysteresis, or a slow probe with back-off when headroom is unobservable;
  - the output drives an FSR 1 scale factor instead of a canvas size.
- **No source text was copied.**

```
MIT License

Copyright (c) 2026 SamG-Coder and CUDA WebShader contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
