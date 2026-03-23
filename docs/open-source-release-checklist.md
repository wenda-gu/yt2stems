# Open Source Release Checklist

- Confirm the LICENSE file matches the intended project license
- Verify the README installation instructions on a clean machine
- Confirm the bootstrap installer works with the currently recommended Python version
- Run `python -m unittest`
- Run `ruff check .`
- Run `python -m build`
- Review issue templates and contributor docs
- Tag the initial release after CI is green
- Upload the release artifacts and note the SHA256 values
