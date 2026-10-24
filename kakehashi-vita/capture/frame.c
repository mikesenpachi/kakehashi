/*
 * Frame capture without hooks: ask the display driver for the frame on the screen now,
 * then copy its pixels from the memory of the process that owns it, a few rows at a time.
 *
 * Nothing runs in the game's display path, so a failure here cannot freeze the game.
 * An earlier version used a hook on _sceDisplaySetFrameBuf instead, and every app froze.
 * There is no full-frame buffer: a 2 MB kernel block failed with 0x80024303 (no free page unit)
 * after sleep and after flight mode. bmp.c copies and writes strips instead.
 * Both functions used here are documented in the VitaSDK headers and are in ForDriver libraries
 * (no NID changes in 3.63+).
 */

#include <psp2kern/kernel/sysclib.h>
#include <psp2kern/kernel/sysmem/data_transfers.h>

#include "kakehashi.h"

SceDisplayFrameBufInfo frame_info;
int frame_index;

/*
 * Find the frame on the main screen now. The header does not say which framebuffer index the
 * game uses, so try index 0, then 1. Fill frame_info and frame_index.
 * Return FRAME_OK, FRAME_NO_FRAME, FRAME_BAD_FORMAT, or the error code of the driver.
 */
int frame_find(void)
{
	int head = ksceDisplayGetPrimaryHead();
	int ret = FRAME_NO_FRAME;
	for (frame_index = 0; frame_index < 2; frame_index++) {
		memset(&frame_info, 0, sizeof(frame_info));
		frame_info.size = sizeof(frame_info);
		ret = ksceDisplayGetProcFrameBufInternal(-1, head, frame_index, &frame_info);
		if (ret >= 0 && frame_info.framebuf.base)
			break;
	}
	if (ret < 0)
		return ret;
	const SceDisplayFrameBuf *fb = &frame_info.framebuf;
	if (!fb->base)
		return FRAME_NO_FRAME;
	int known = fb->pixelformat == SCE_DISPLAY_PIXELFORMAT_A8B8G8R8 ||
		    fb->pixelformat == PIXELFORMAT_BGRA5551;
	if (!known || fb->width > MAX_WIDTH || fb->height > MAX_HEIGHT)
		return FRAME_BAD_FORMAT;
	return FRAME_OK;
}

/* Return the bytes per pixel of the frame from frame_find: 2 for BGRA5551, else 4. */
int frame_bytes_per_pixel(void)
{
	return frame_info.framebuf.pixelformat == PIXELFORMAT_BGRA5551 ? 2 : 4;
}

/*
 * Copy count rows of the frame from frame_find, starting at row first, into dest
 * (width pixels per row, no gaps). The pitch is in pixels for both formats.
 * Return FRAME_OK or FRAME_COPY_FAILED.
 */
int frame_copy(void *dest, int first, int count)
{
	const SceDisplayFrameBuf *fb = &frame_info.framebuf;
	const uint8_t *base = fb->base;
	int bpp = frame_bytes_per_pixel();
	uint8_t *out = dest;
	for (int y = first; y < first + count; y++) {
		if (ksceKernelCopyFromUserProc(frame_info.pid, out + (y - first) * fb->width * bpp,
					       base + y * fb->pitch * bpp, fb->width * bpp) < 0)
			return FRAME_COPY_FAILED;
	}
	return FRAME_OK;
}
