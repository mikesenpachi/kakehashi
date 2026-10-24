/*
 * BMP writer: save the frame from frame_find as a 24-bit BMP file.
 * It copies STRIP_ROWS rows at a time from the game, converts them and writes them in one call.
 * One write per strip, not per row: 545 row writes took about 3 s.
 */

#include <psp2kern/io/fcntl.h>

#include "kakehashi.h"

#define HEADER_SIZE 54
#define STRIP_ROWS 16

static uint32_t pixels[STRIP_ROWS * MAX_WIDTH];
static uint8_t out[STRIP_ROWS * (MAX_WIDTH * 3 + 3)];

/* Store a 32-bit value in little-endian order. */
static void put32(uint8_t *p, uint32_t value)
{
	p[0] = value;
	p[1] = value >> 8;
	p[2] = value >> 16;
	p[3] = value >> 24;
}

/* Fill header with the BMP header for a width x height 24-bit image. */
static void make_header(uint8_t *header, int width, int height, int row_size)
{
	put32(header + 2, HEADER_SIZE + row_size * height); /* file size */
	put32(header + 10, HEADER_SIZE);                     /* offset of the pixels */
	put32(header + 14, 40);                              /* info header size */
	put32(header + 18, width);
	put32(header + 22, height);
	header[26] = 1;                                      /* planes */
	header[28] = 24;                                     /* bits per pixel */
	put32(header + 34, row_size * height);               /* pixel data size */
}

/* Convert one row of A8B8G8R8 pixels into B, G, R bytes. */
static void convert_abgr(const uint32_t *src, uint8_t *row, int width)
{
	for (int x = 0; x < width; x++) {
		row[x * 3] = src[x] >> 16;    /* B */
		row[x * 3 + 1] = src[x] >> 8; /* G */
		row[x * 3 + 2] = src[x];      /* R */
	}
}

/* Convert one row of BGRA5551 pixels (red in the low 5 bits) into B, G, R bytes. */
static void convert_5551(const uint16_t *src, uint8_t *row, int width)
{
	for (int x = 0; x < width; x++) {
		row[x * 3] = ((src[x] >> 10) & 0x1F) << 3; /* B */
		row[x * 3 + 1] = ((src[x] >> 5) & 0x1F) << 3; /* G */
		row[x * 3 + 2] = (src[x] & 0x1F) << 3;     /* R */
	}
}

/*
 * Convert count rows of pixels into out, last row first, as B, G, R bytes.
 * Return the number of bytes in out.
 */
static int convert(int width, int count, int row_size)
{
	int bpp = frame_bytes_per_pixel();
	for (int i = 0; i < count; i++) {
		const uint8_t *src = (const uint8_t *)pixels + (count - 1 - i) * width * bpp;
		uint8_t *row = out + i * row_size;
		if (bpp == 2)
			convert_5551((const uint16_t *)src, row, width);
		else
			convert_abgr((const uint32_t *)src, row, width);
	}
	return count * row_size;
}

/*
 * Write the frame from frame_find as a 24-bit BMP. BMP rows go bottom to top, each row padded
 * to 4 bytes, so the strips go from the bottom of the screen to the top.
 * Return 0, a FRAME_ result, or a negative error code of the file system.
 */
int write_bmp(const char *path)
{
	int width = frame_info.framebuf.width;
	int height = frame_info.framebuf.height;
	int row_size = (width * 3 + 3) & ~3;
	uint8_t header[HEADER_SIZE] = {'B', 'M'};
	make_header(header, width, height, row_size);

	SceUID fd = ksceIoOpen(path, SCE_O_WRONLY | SCE_O_CREAT | SCE_O_TRUNC, 0666);
	if (fd < 0)
		return fd;
	int ret = ksceIoWrite(fd, header, HEADER_SIZE);
	for (int end = height; end > 0 && ret >= 0; end -= STRIP_ROWS) {
		int count = end < STRIP_ROWS ? end : STRIP_ROWS;
		ret = frame_copy(pixels, end - count, count);
		if (ret == FRAME_OK)
			ret = ksceIoWrite(fd, out, convert(width, count, row_size));
	}
	ksceIoClose(fd);
	return ret < 0 ? ret : 0;
}
