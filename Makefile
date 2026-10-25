# `make docs` is the publishing contract: HTML into docs/build/html/, warnings
# as errors, installing only what the docs need. The docs server runs exactly
# this — see pve's docs, vms/docs.
.PHONY: docs

docs:
	uv run --frozen --only-group docs sphinx-build -W --keep-going -b html docs docs/build/html
