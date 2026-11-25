.PHONY: new test lint
new:
	@test -n "$(name)" || (echo "usage: make new name=my-idea"; exit 1)
	cp -r projects/_template projects/$(name)
	@echo "Created projects/$(name). Fill in its README."
test:
	@for d in projects/*/; do case $$d in *_template*) continue;; esac; \
	  (cd $$d && [ -d tests ] && python -m pytest -q) || exit 1; done
lint:
	ruff check . && ruff format --check .
