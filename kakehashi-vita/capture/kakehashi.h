/* kakehashi capture plugin: shared constants and functions. */

#pragma once

#include <psp2kern/ctrl.h>
#include <psp2kern/display.h>
#include <stdint.h>

#define FOLDER "ux0:data/kakehashi"
#define QUEUE FOLDER "/queue"
/* The combo when config.txt has no valid combo= line. */
#define DEFAULT_COMBO (SCE_CTRL_LTRIGGER | SCE_CTRL_RTRIGGER | SCE_CTRL_SELECT)

/* Largest frame the plugin copies: the full Vita screen. */
#define MAX_WIDTH 960
#define MAX_HEIGHT 544

/* PS1 games in Adrenaline: BGRA5551, 16 bits per pixel, red in the low 5 bits. Not in VitaSDK. */
#define PIXELFORMAT_BGRA5551 0x50000000U

/* Results of frame_find and frame_copy. frame_find can also return an error code of the driver. */
enum {
	FRAME_OK = 0,
	FRAME_NO_FRAME = -1,   /* the driver gave no frame address for index 0 or 1 */
	FRAME_BAD_FORMAT = -2, /* pixel format is not A8B8G8R8 or BGRA5551, or the frame is too large */
	FRAME_COPY_FAILED = -3,
};

/* main.c */
void log_line(const char *text);

/* config.c */
extern uint32_t combo;
void read_config(void);

/* buttons.c */
void install_button_hooks(void);

/* frame.c */
extern SceDisplayFrameBufInfo frame_info;
extern int frame_index;
int frame_find(void);
int frame_bytes_per_pixel(void);
int frame_copy(void *dest, int first, int count);

/* bmp.c */
int write_bmp(const char *path);

/* notice.c */
void install_notice_hook(void);
void notice_show(const char *text, int ok);
int notice_hide(void);
