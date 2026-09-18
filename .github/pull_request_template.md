## Summary
<!-- Briefly describe the change and why it is needed. -->

## How to test
<!-- List commands or manual steps a reviewer can run to verify the change. -->

## Checklist
- [ ] `ruff check src tests scripts` passes
- [ ] `pytest tests -q` passes (or new tests are included)
- [ ] `npm --prefix frontend test` and `npm --prefix frontend run build` pass
- [ ] No personal recordings, model weights, secrets, or environment files are added
- [ ] Documentation is updated if user-facing behavior changed
