/*
 * kakehashi capture plugin (kernel).
 *
 * Increment 7: at boot, the plugin reads the combo from config.txt (default L + R + SELECT).
 * A thread reads the buttons about 60 times a second. When the combo goes down, it logs the
 * count since boot, copies the frame on the screen and saves it as a BMP in the queue folder, named <YYYYMMDD-HHMMSS>-<n>_<titleid>.bmp. Button hooks hide the combo from
 * the game. The BMP is written to TEMP first and then renamed into the queue, so the sender never
 * reads a half-written file. The frame is copied and written in strips of 16 rows, so the plugin
 * needs no large memory block. After each combo, a notice shows "SAVED" or "FAILED".
 */

#include <psp2kern/io/fcntl.h>
#include <psp2kern/io/stat.h>
#include <psp2kern/kernel/modulemgr.h>
#include <psp2kern/kernel/rtc.h>
#include <psp2kern/kernel/sysclib.h>
#include <psp2kern/kernel/sysroot.h>
#include <psp2kern/kernel/threadmgr.h>

#include "kakehashi.h"

#define LOG FOLDER "/log.txt"
#define OLD_LOG FOLDER "/log.old.txt"
#define MAX_LOG (64 * 1024)
#define TEMP FOLDER "/capture.tmp"
#define POLL_US 16000
#define NOTICE_GONE_US 50000 /* 3 frames: the game draws over an old notice before the copy */

/* Append one line of text to the log file. */
void log_line(const char *text)
{
	SceUID fd = ksceIoOpen(LOG, SCE_O_WRONLY | SCE_O_CREAT | SCE_O_APPEND, 0666);
	if (fd < 0)
		return;
	ksceIoWrite(fd, text, strlen(text));
	ksceIoWrite(fd, "\n", 1);
	ksceIoClose(fd);
}

/* At boot, a log over MAX_LOG becomes OLD_LOG, so the log never grows past about 64 KB. */
static void rotate_log(void)
{
	SceIoStat stat;
	if (ksceIoGetstat(LOG, &stat) >= 0 && stat.st_size > MAX_LOG) {
		ksceIoRemove(OLD_LOG);
		ksceIoRename(LOG, OLD_LOG);
	}
}

/*
 * Make the queue path for shot number count of the process pid:
 * QUEUE/<YYYYMMDD-HHMMSS>-<count>_<titleid>.bmp, with the local time of the Vita.
 */
static void queue_path(char *path, SceSize size, int count, SceUID pid)
{
	char title[32] = "unknown";
	SceDateTime now;
	ksceKernelSysrootGetProcessTitleId(pid, title, sizeof(title));
	ksceRtcGetCurrentClockLocalTime(&now);
	snprintf(path, size, QUEUE "/%04d%02d%02d-%02d%02d%02d-%d_%s.bmp", now.year, now.month,
		 now.day, now.hour, now.minute, now.second, count, title);
}

/*
 * Capture the frame on the screen and save it in the queue folder.
 * The answer of the display driver is logged before the copy, so it is on disk even if the
 * copy crashes the Vita. Return 1 if the shot is in the queue, else 0.
 */
static int save_shot(int count)
{
	char line[192];
	const SceDisplayFrameBuf *fb = &frame_info.framebuf;
	int ret = frame_find();
	snprintf(line, sizeof(line),
		 "kakehashi: frame %08X: index %d, pid %08X, base %08X, %dx%d, pitch %d, format %08X", ret,
		 frame_index, frame_info.pid, (unsigned int)fb->base, fb->width, fb->height, fb->pitch,
		 fb->pixelformat);
	log_line(line);
	if (ret != FRAME_OK)
		return 0;

	char path[128];
	queue_path(path, sizeof(path), count, frame_info.pid);
	SceInt64 start = ksceKernelGetSystemTimeWide();
	ret = write_bmp(TEMP);
	SceInt64 written = ksceKernelGetSystemTimeWide();
	if (ret >= 0)
		ret = ksceIoRename(TEMP, path);
	if (ret < 0)
		snprintf(line, sizeof(line), "kakehashi: cannot write %s: %08X", path, ret);
	else
		snprintf(line, sizeof(line), "kakehashi: saved %s (copy and write %d ms)", path,
			 (int)((written - start) / 1000));
	log_line(line);
	return ret >= 0;
}

/* Read the buttons in a loop. Each time the combo goes down, log it and save a shot. */
static int combo_thread(SceSize args, void *argp)
{
	SceCtrlData pad;
	int was_down = 0;
	int count = 0;
	char line[64];

	for (;;) {
		ksceCtrlPeekBufferPositive(0, &pad, 1);
		int down = (pad.buttons & combo) == combo;
		if (down && !was_down) {
			count++;
			snprintf(line, sizeof(line), "kakehashi: combo #%d", count);
			log_line(line);
			if (notice_hide())
				ksceKernelDelayThread(NOTICE_GONE_US);
			int ok = save_shot(count);
			notice_show(ok ? "SAVED" : "FAILED", ok);
		}
		was_down = down;
		ksceKernelDelayThread(POLL_US);
	}
	return 0;
}

int _start(SceSize args, void *argp) __attribute__((weak, alias("module_start")));

int module_start(SceSize args, void *argp)
{
	ksceIoMkdir(FOLDER, 0777);
	ksceIoMkdir(QUEUE, 0777);
	rotate_log();
	log_line("kakehashi: capture plugin loaded");
	read_config();
	install_button_hooks();
	install_notice_hook();

	/* Priority 0xA0, the default for normal threads: with 0x3C, the game sound stopped during a capture. Tested. */
	SceUID thread = ksceKernelCreateThread("kakehashi_combo", combo_thread, 0xA0, 0x4000, 0, 0, NULL);
	if (thread < 0) {
		log_line("kakehashi: cannot create combo thread");
		return SCE_KERNEL_START_SUCCESS;
	}
	ksceKernelStartThread(thread, 0, NULL);
	return SCE_KERNEL_START_SUCCESS;
}

int module_stop(SceSize args, void *argp)
{
	return SCE_KERNEL_STOP_SUCCESS;
}
