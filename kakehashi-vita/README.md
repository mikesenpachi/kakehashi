# kakehashi-vita

Vita plugins, written in C with [VitaSDK](https://vitasdk.org/):

- `capture/`: a kernel plugin. When you press the combo, it saves the screen as a BMP in a queue folder. "SAVED" or "FAILED" shows on the screen for 1.5 s.
- `sender/`: a SceShell plugin. It sends each shot in the queue to the webapp, and deletes it after the webapp answers 200. Without Wi-Fi, the shots wait in the queue.

The sender talks to the webapp only through the Shot API (see [kakehashi-web/README.md](../kakehashi-web/README.md#api)): the image, the title ID and the capture time.

Needs a Vita with HENkaku / taiHEN, tested on firmware 3.65. PSP and PS1 games in Adrenaline work too, but the notice does not show there (Adrenaline does not use the display function that the notice hooks).

## Install on the Vita

Use the files from the GitHub release, or build them (below).

1. Copy `kakehashi.skprx` and `kakehashi_sender.suprx` to `ur0:tai/` (VitaShell, over FTP or USB). Over FTP from a computer:
   ```
   curl -T kakehashi.skprx "ftp://<vita ip>:1337/ur0:/tai/kakehashi.skprx"
   curl -T kakehashi_sender.suprx "ftp://<vita ip>:1337/ur0:/tai/kakehashi_sender.suprx"
   ```
2. In the taiHEN config, add `ur0:tai/kakehashi.skprx` under `*KERNEL`, and `ur0:tai/kakehashi_sender.suprx` under `*main`:
   ```
   *KERNEL
   ur0:tai/kakehashi.skprx
   *main
   ur0:tai/kakehashi_sender.suprx
   ```
   taiHEN reads `ux0:tai/config.txt` if it exists, else `ur0:tai/config.txt`. Edit the file that is used, and keep the lines that are already there.
3. Make `ux0:data/kakehashi/config.txt` (see Config).
4. Reboot the Vita.

The capture plugin logs to `ux0:data/kakehashi/log.txt` and puts the shots in `ux0:data/kakehashi/queue/` as `<YYYYMMDD-HHMMSS>-<n>_<titleid>.bmp`. The sender logs to `ux0:data/kakehashi/sender.txt`. At boot, a log over 64 KB becomes `log.old.txt` or `sender.old.txt` (the older copy is deleted).

## Config

`ux0:data/kakehashi/config.txt`. Edit it with the VitaShell text editor, then reboot. The webapp's `/server` page shows a ready block with your computer's address.

```
server=192.168.1.10
port=8766
token=
combo=L+R+SELECT
```

- `server` is the computer's IPv4 address (not a name). `port` is the webapp port.
- `token` must match `KAKEHASHI_TOKEN` on the computer. Leave it empty when no token is set.
- `combo`: button names joined with `+`, any order, any case, at least 2: `L`, `R`, `SELECT`, `START`, `UP`, `DOWN`, `LEFT`, `RIGHT`, `TRIANGLE`, `CIRCLE`, `CROSS`, `SQUARE`. Default `L+R+SELECT`. `log.txt` shows the combo in use, or the error. Pick buttons the game ignores: a game sees each button until the full combo is down.
- The sender reads the file 10 s after boot. Without a valid `server` and `port`, it logs the problem and sends nothing.

## Build

Install VitaSDK (macOS):

```
brew install cmake wget
git clone https://github.com/vitasdk/vdpm
cd vdpm
VITASDK=$HOME/vitasdk ./bootstrap-vitasdk.sh
VITASDK=$HOME/vitasdk $HOME/vitasdk/bin/vdpm install taihen
```

Add to your shell profile:

```
export VITASDK=$HOME/vitasdk
export PATH=$VITASDK/bin:$PATH
```

Then, from the repo root, `make plugins` builds both: `kakehashi-vita/capture/build/kakehashi.skprx` and `kakehashi-vita/sender/build/kakehashi_sender.suprx`.

## Remove, or recover from a bad plugin

- If apps freeze or the Vita does not boot normally: turn it off, then hold L while it boots. Plugins are not loaded.
- Delete the two config lines, then `ur0:tai/kakehashi.skprx`, `ur0:tai/kakehashi_sender.suprx` and `ux0:data/kakehashi/`. Reboot.
