/*
 * Button hooks: hide the capture combo from the game.
 *
 * Hooks the button functions of the SceCtrl library that games call (NIDs from vita-headers
 * db/360, not changed in 3.63+): Peek and Read, BufferPositive, Positive2, PositiveExt,
 * PositiveExt2. The combo thread reads the buttons through the kernel function, which is not
 * hooked, so it still sees the combo.
 */

#include <psp2kern/kernel/sysclib.h>
#include <psp2kern/kernel/sysmem/data_transfers.h>
#include <taihen.h>

#include "kakehashi.h"

#define HOOK_COUNT 8
static const uint32_t HOOK_NIDS[HOOK_COUNT] = {
	0xA9C3CED6, 0x67E7AB83, 0x15F81E8C, 0xC4226A3E,
	0xA59454D3, 0xE2D99296, 0x860BF292, 0xA7178860,
};
static tai_hook_ref_t hook_refs[HOOK_COUNT];

/* Remove the combo buttons from each sample the game gets where the full combo is down. */
static void hide_combo(SceCtrlData *pad_user, int count)
{
	SceCtrlData pad;
	for (int i = 0; i < count; i++) {
		ksceKernelCopyFromUser(&pad, &pad_user[i], sizeof(pad));
		if ((pad.buttons & combo) == combo) {
			pad.buttons &= ~combo;
			ksceKernelCopyToUser(&pad_user[i], &pad, sizeof(pad));
		}
	}
}

/* One hook per function: call the real function, then hide the combo. */
#define HOOK(n)                                                              \
	static int hook_##n(int port, SceCtrlData *pad, int count)           \
	{                                                                    \
		int ret = TAI_CONTINUE(int, hook_refs[n], port, pad, count); \
		if (ret > 0)                                                 \
			hide_combo(pad, ret);                                \
		return ret;                                                  \
	}
HOOK(0) HOOK(1) HOOK(2) HOOK(3) HOOK(4) HOOK(5) HOOK(6) HOOK(7)

static const void *const HOOK_FUNCS[HOOK_COUNT] = {
	hook_0, hook_1, hook_2, hook_3, hook_4, hook_5, hook_6, hook_7,
};

/* Install the button hooks. Log the number that worked, and the error of each that failed. */
void install_button_hooks(void)
{
	char line[64];
	int ok = 0;
	for (int i = 0; i < HOOK_COUNT; i++) {
		SceUID uid = taiHookFunctionExportForKernel(KERNEL_PID, &hook_refs[i], "SceCtrl",
							    TAI_ANY_LIBRARY, HOOK_NIDS[i], HOOK_FUNCS[i]);
		if (uid >= 0) {
			ok++;
		} else {
			snprintf(line, sizeof(line), "kakehashi: hook %08X failed: %08X", HOOK_NIDS[i], uid);
			log_line(line);
		}
	}
	snprintf(line, sizeof(line), "kakehashi: %d of %d button hooks installed", ok, HOOK_COUNT);
	log_line(line);
}
