VENV_PATH = ./.venv
PYTHON_VERSION = 3.14

.PHONY: configure
configure:
	rm -rf $(VENV_PATH)
	uv venv --python $(PYTHON_VERSION)
	uv sync

clean:
	rm -rf venv

.PHONY: typecheck
typecheck:
	uv run basedpyright custom_components/
