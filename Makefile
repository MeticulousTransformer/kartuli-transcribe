.PHONY: install-local test

install-local:
	uv tool install --force .

test:
	python -m unittest discover -s tests -v
