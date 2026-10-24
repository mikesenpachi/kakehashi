/*
 * Notice on the screen: "SAVED" or "FAILED" in the top-left corner for 1.5 s.
 *
 * A hook on ksceDisplaySetFrameBufInternal (SceDisplayForDriver, NID 0x16466675, the same in
 * 3.60 and 3.65) copies the notice into each frame before it goes to the screen. PSVshell hooks
 * the same function (no PSVshell code is used here). This is not _sceDisplaySetFrameBuf: a hook
 * on that one froze every app.
 * The text uses a 5x7 font with only the characters the notice needs, drawn 3 times larger.
 */

#include <psp2kern/kernel/sysclib.h>
#include <psp2kern/kernel/sysmem/data_transfers.h>
#include <psp2kern/kernel/threadmgr.h>
#include <taihen.h>

#include "kakehashi.h"

#define SCALE 3
#define CELL (6 * SCALE) /* 5 pixels and a gap */
#define PAD 6
#define MAX_CHARS 12
#define NOTICE_W (PAD * 2 + MAX_CHARS * CELL)
#define NOTICE_H (PAD * 2 + 7 * SCALE)
#define NOTICE_X 16
#define NOTICE_Y 16
#define SHOW_US (1500 * 1000)

/* Colors as A8B8G8R8 (0xAABBGGRR). */
#define BACK 0xFF202020
#define WHITE 0xFFFFFFFF
#define RED 0xFF4040FF

static const char CHARS[] = " ADEFILSV";
static const uint8_t FONT[][7] = {
	{0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00}, /* space */
	{0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11}, /* A */
	{0x1E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x1E}, /* D */
	{0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F}, /* E */
	{0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10}, /* F */
	{0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E}, /* I */
	{0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F}, /* L */
	{0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E}, /* S */
	{0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04}, /* V */
};

static uint32_t notice[NOTICE_H * NOTICE_W];
static int notice_w;
static volatile SceInt64 notice_until;
static tai_hook_ref_t hook_ref;

/* Draw one character of the font into the notice at x. Unknown characters are spaces. */
static void draw_char(char c, int x, uint32_t color)
{
	const char *found = strchr(CHARS, c);
	const uint8_t *glyph = FONT[found ? found - CHARS : 0];
	for (int row = 0; row < 7 * SCALE; row++)
		for (int col = 0; col < 5 * SCALE; col++)
			if (glyph[row / SCALE] & (0x10 >> (col / SCALE)))
				notice[(PAD + row) * NOTICE_W + x + col] = color;
}

/* Show text on the screen for SHOW_US: white if ok, else red. */
void notice_show(const char *text, int ok)
{
	notice_until = 0;
	int len = strnlen(text, MAX_CHARS);
	notice_w = PAD * 2 + len * CELL - SCALE;
	for (int i = 0; i < NOTICE_H * NOTICE_W; i++)
		notice[i] = BACK;
	for (int i = 0; i < len; i++)
		draw_char(text[i], PAD + i * CELL, ok ? WHITE : RED);
	notice_until = ksceKernelGetSystemTimeWide() + SHOW_US;
}

/* Stop showing the notice. Return 1 if it was on the screen, else 0. */
int notice_hide(void)
{
	int shown = ksceKernelGetSystemTimeWide() < notice_until;
	notice_until = 0;
	return shown;
}

/* Copy the notice into the frame, row by row. The frame is in the memory of the calling process. */
static void draw_notice(const SceDisplayFrameBuf *fb)
{
	uint32_t *base = fb->base;
	for (int y = 0; y < NOTICE_H; y++)
		ksceKernelCopyToUser(base + (NOTICE_Y + y) * fb->pitch + NOTICE_X, notice + y * NOTICE_W,
				     notice_w * 4);
}

static int hook_set_frame(int head, int index, const SceDisplayFrameBuf *fb, int sync)
{
	if (head && fb && fb->base && fb->pixelformat == SCE_DISPLAY_PIXELFORMAT_A8B8G8R8 &&
	    fb->width >= NOTICE_X + NOTICE_W && fb->height >= NOTICE_Y + NOTICE_H &&
	    ksceKernelGetSystemTimeWide() < notice_until)
		draw_notice(fb);
	return TAI_CONTINUE(int, hook_ref, head, index, fb, sync);
}

/* Install the display hook and log the result. */
void install_notice_hook(void)
{
	char line[64];
	SceUID uid = taiHookFunctionExportForKernel(KERNEL_PID, &hook_ref, "SceDisplay", 0x9FED47AC,
						    0x16466675, hook_set_frame);
	snprintf(line, sizeof(line), "kakehashi: notice hook %08X", uid);
	log_line(line);
}
