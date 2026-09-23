PYTHON ?= python3
JOBS ?= 2
ARGS ?=

.PHONY: fetch build patch probe fixture reproduce install test binary tarball pkg-arch pkg-deb pkg-sums
fetch:
	$(PYTHON) scripts/repro.py fetch $(ARGS)
build:
	$(PYTHON) scripts/repro.py build --jobs $(JOBS) $(ARGS)
patch:
	$(PYTHON) scripts/repro.py patch $(ARGS)
probe:
	$(PYTHON) scripts/repro.py probe $(ARGS)
fixture:
	$(PYTHON) scripts/repro.py fixture $(ARGS)
reproduce:
	$(PYTHON) scripts/repro.py reproduce $(ARGS)
install:
	$(PYTHON) scripts/repro.py install $(ARGS)
test:
	$(PYTHON) -m unittest discover -s tests -v
binary:
	scripts/build-binary.sh $(ARGS)
tarball:
	scripts/build-binary.sh --tarball-out $(ARGS)
pkg-arch:
	cd packaging/arch && makepkg -f $(ARGS)
pkg-sums:
	python3 packaging/arch/update-sums.py
pkg-deb:
	packaging/deb/build-deb.sh $(ARGS)
