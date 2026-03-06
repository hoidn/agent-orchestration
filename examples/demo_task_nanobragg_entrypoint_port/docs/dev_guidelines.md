# Dev Guidelines

- Keep the port in pure Python + PyTorch.
- Prefer clear decomposition over transliterating one giant scalar function.
- Treat tensorization as a real requirement, not an optional optimization.
- Do not preserve the full detector/subpixel loop nest as a direct scalar port if the same work can be expressed as batched tensor operations.
- Preserve observable behavior before attempting optimization.
- Use the visible fixtures and smoke tests as a floor, not final proof of correctness.
