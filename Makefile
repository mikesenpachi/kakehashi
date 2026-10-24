# kakehashi tasks. Run from the repo root: make <target>

VITASDK ?= $(HOME)/vitasdk
export VITASDK
export PATH := $(VITASDK)/bin:$(PATH)
SERVER ?= http://localhost:8766

.PHONY: help server plugins capture sender plugin-3ds image-3ds zip-3ds samples test prune

help:
	@echo "make server    start the webapp on port 8766 (reloads on .py changes)"
	@echo "make plugins   build the Vita capture and sender plugins"
	@echo "make plugin-3ds build the 3DS plugin in Docker (kakehashi-3ds/kakehashi.3gx)"
	@echo "make zip-3ds   build the 3DS plugin and zip it for the SD card (release/kakehashi-3ds.zip)"
	@echo "make samples   upload your shots in samples/ to SERVER (default $(SERVER)); adds them to its database"
	@echo "make test      run the webapp unit tests (temporary data, fake OCR)"
	@echo "make prune     list image files that no shot uses (deletes nothing; see the tool for --delete)"

server:
	cd kakehashi-web && uv run uvicorn main:app --host 0.0.0.0 --port 8766 --reload

plugins: capture sender

capture sender:
	cmake -S kakehashi-vita/$@ -B kakehashi-vita/$@/build
	cmake --build kakehashi-vita/$@/build

# The image has devkitARM, libctru, CTRPluginFramework and 3gxtool (kakehashi-3ds/Dockerfile).
image-3ds:
	docker build -t kakehashi-3ds kakehashi-3ds

plugin-3ds: image-3ds
	docker run --rm -v $(CURDIR)/kakehashi-3ds:/plugin kakehashi-3ds make

# The zip has the SD card folders: unzip it at the root of the SD card.
zip-3ds: plugin-3ds
	rm -rf release/sd-3ds release/kakehashi-3ds.zip
	mkdir -p release/sd-3ds/luma/plugins release/sd-3ds/kakehashi
	cp kakehashi-3ds/kakehashi.3gx release/sd-3ds/luma/plugins/default.3gx
	cp kakehashi-3ds/config.example.txt release/sd-3ds/kakehashi/config.example.txt
	cd release/sd-3ds && zip -r -X ../kakehashi-3ds.zip luma kakehashi

samples:
	uv run tools/upload_samples.py $(SERVER)

test:
	cd kakehashi-web && uv run pytest

prune:
	uv run tools/prune_images.py
