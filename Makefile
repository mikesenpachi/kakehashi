# kakehashi tasks. Run from the repo root: make <target>

VITASDK ?= $(HOME)/vitasdk
export VITASDK
export PATH := $(VITASDK)/bin:$(PATH)
SERVER ?= http://localhost:8766
BACKUP_DIR ?= $(HOME)/kakehashi-backups

.PHONY: help server plugins capture sender plugin-3ds image-3ds zip-3ds zip-vita demo samples test prune backup restore

help:
	@echo "make server    start the webapp on port 8766 (reloads on .py changes)"
	@echo "make plugins   build the Vita capture and sender plugins"
	@echo "make zip-vita  build the Vita plugins and zip them (release/kakehashi-vita.zip)"
	@echo "make plugin-3ds build the 3DS plugin in Docker (kakehashi-3ds/kakehashi.3gx)"
	@echo "make zip-3ds   build the 3DS plugin and zip it for the SD card (release/kakehashi-3ds.zip)"
	@echo "make demo      start a demo server on port 8767 with empty data (then: uv run tools/demo.py)"
	@echo "make samples   upload your shots in samples/ to SERVER (default $(SERVER)); adds them to its database"
	@echo "make test      run the webapp unit tests (temporary data, fake OCR)"
	@echo "make prune     list image files that no shot uses (deletes nothing; see the tool for --delete)"
	@echo "make backup    back up the database and new images to BACKUP_DIR (default $(BACKUP_DIR))"
	@echo "make restore   stop the server first; restore the newest copy in BACKUP_DIR (or DB=<file>); moves the current data aside"

server:
	cd kakehashi-web && uv run uvicorn main:app --host 0.0.0.0 --port 8766 --reload

plugins: capture sender

capture sender:
	cmake -S kakehashi-vita/$@ -B kakehashi-vita/$@/build
	cmake --build kakehashi-vita/$@/build

# One folder per Vita storage area: copy ur0/tai/* to ur0:tai/ and ux0/data/kakehashi/* to ux0:data/kakehashi/.
zip-vita: plugins
	rm -rf release/sd-vita release/kakehashi-vita.zip
	mkdir -p release/sd-vita/ur0/tai release/sd-vita/ux0/data/kakehashi
	cp kakehashi-vita/capture/build/kakehashi.skprx kakehashi-vita/sender/build/kakehashi_sender.suprx release/sd-vita/ur0/tai/
	cp kakehashi-vita/config.example.txt release/sd-vita/ux0/data/kakehashi/config.example.txt
	cd release/sd-vita && zip -r -X ../kakehashi-vita.zip ur0 ux0

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

# A demo server for recordings: its own empty data folder, so real shots never show.
demo:
	rm -rf $(CURDIR)/kakehashi-web/demo-data
	cd kakehashi-web && KAKEHASHI_DATA=$(CURDIR)/kakehashi-web/demo-data uv run uvicorn main:app --port 8767

samples:
	uv run tools/upload_samples.py $(SERVER)

test:
	cd kakehashi-web && uv run pytest

prune:
	uv run tools/prune_images.py

# Adds only: a dated database copy and the new image files. Never deletes in BACKUP_DIR.
backup:
	uv run tools/backup.py "$(BACKUP_DIR)"

# Refuses while the server runs. Renames the current data folder, never deletes it.
restore:
	uv run tools/restore.py "$(BACKUP_DIR)" $(if $(DB),"$(DB)")
