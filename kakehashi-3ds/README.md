# kakehashi-3ds

3DS plugin (3GX, CTRPluginFramework), loaded by the Luma3DS plugin loader into a game.

When you press the combo, it saves both screens as one 400x480 BMP (top screen above, bottom screen centered below) to `sdmc:/kakehashi/queue/<YYYYMMDD-HHMMSS>-<n>_<titleid>.bmp`. "SAVED" or "FAILED" shows for 1.5 s; it is never in a shot. A low-priority thread sends each shot to the webapp's Shot API and deletes it after a 200. Without Wi-Fi, the shots wait in the queue. Logs: `sdmc:/kakehashi/log.txt` and `sdmc:/kakehashi/sender.txt`.

Tested on a New 3DS XL with Luma3DS v13.3.3, in Dragon Quest VIII, Ace Attorney Trilogy (逆転裁判123), Pokémon Omega Ruby, Mario & Luigi RPG3 DX and Animal Crossing: New Leaf. 3D mode is not supported.

## Install

Use `kakehashi-3ds.zip` from the GitHub release, or build it (below).

1. In the Rosalina menu (L + Down + Select), turn on **Plugin Loader**.
2. Unzip `kakehashi-3ds.zip` at the root of the SD card. It has `luma/plugins/default.3gx` (loaded into every game without its own plugin) and `kakehashi/config.example.txt`. A `default.3gx` that is already there is replaced. For one game only, move the file to `/luma/plugins/<title ID>/kakehashi.3gx` instead.
3. Copy `kakehashi/config.example.txt` to `kakehashi/config.txt` and edit it (see Config). The zip has no `config.txt`, so an update never replaces your settings.
4. Start the game. A "kakehashi loaded" notice shows.

A game loads only one plugin: if a game has its own plugin folder, `default.3gx` is not loaded into it. The framework also makes `/luma/plugins/ActionReplay/` (its cheat feature).

## Config

`sdmc:/kakehashi/config.txt`, read when the game starts. The same format as the Vita's:

```
server=192.168.1.10
port=8766
token=
combo=L+SELECT
combo.0004000000108800=L+DOWN
```

- `server` is the computer's IPv4 address, `port` the webapp port. Without them, nothing is sent.
- `token` must match `KAKEHASHI_TOKEN` on the computer. Leave it empty when no token is set.
- `combo`: button names joined with `+`, at least 2: A, B, X, Y, L, R, START, SELECT, UP, DOWN, LEFT, RIGHT. Default `L+SELECT`. ZL and ZR cannot be used: the plugin cannot read them.
- `combo.<title ID>` sets the combo for one game. The log line `loaded in <title ID>` gives the ID.
- The game also sees the combo, so choose buttons that the game ignores.
- Problems go to `log.txt`.

## Build

Needs Docker. From the repo root:

```
make plugin-3ds
```

The output is `kakehashi-3ds/kakehashi.3gx`. `make zip-3ds` builds it and makes `release/kakehashi-3ds.zip` with the SD card folders. The Docker image (`Dockerfile`) has devkitARM, libctru, CTRPluginFramework (`libctrpf`) and `3gxtool` from devkitPro and ThePixellizerOSS. It is amd64, because `3gxtool` is built only for x86_64 Linux; Docker emulates it on Apple Silicon.

## How it works

- **Buttons:** the plugin sets `UseGameHidMemory = true` and reads the buttons from the game's own hid memory. Without it, the framework opens a second hid session, and the New 3DS C-stick stops working in the game. When the framework does not find the game's hid memory, the plugin scans the game's shared memory for it.
- **Capture:** the copy is split over 8 frame callbacks (4 parts per screen, about 3.7 ms each), and the file is written with one write. A whole copy in one frame made games stutter. The copy uses each screen's own format and stride.
- **Network:** the plugin uses the system HTTP service (`http:C`), not sockets: a game that started the socket service itself owns it.
- **Memory:** `kakehashi.plgInfo` sets `MemorySize: 5MiB` and `UsePrivateMemory: false`. With private plugin memory, Ace Attorney Trilogy crashed at start, even with an empty plugin (Luma3DS issue #2225). The HTTP service needs private memory for its POST buffer, so `Sources/http.cpp` takes that buffer (564 KB) from the SYSTEM region with Luma's `svcControlMemoryUnsafe`, as Rosalina does. The sender starts the HTTP service only while the queue has shots, and stops it before the game closes: a game closed with the service running did not start again until a reboot.

## Licenses

- `Includes/types.h` is copied from CTRPluginFramework (the `libctrpf` package leaves it out, but its headers include it). License: `Includes/LICENSE-ctrpf.txt`.
- Two functions in `Sources/http.cpp` come from libctru. License: `Sources/LICENSE-libctru.txt`.

## Remove

Delete the `.3gx` file, or turn off the plugin loader in Rosalina.
