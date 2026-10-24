/*
 * Config: the combo= line of CONFIG, read once at boot.
 *
 * Format: combo=L+R+SELECT. Button names joined with '+', any order, any case, at least 2 buttons.
 * The PS and volume buttons are not allowed: the system acts on them. Without the line, or with
 * a wrong value, the combo is L+R+SELECT and the log tells why.
 */

#include <psp2kern/io/fcntl.h>
#include <psp2kern/kernel/sysclib.h>

#include "kakehashi.h"

#define CONFIG FOLDER "/config.txt"
#define KEY "combo="
#define MAX_VALUE 64

uint32_t combo = DEFAULT_COMBO;

static const struct {
	const char *name;
	uint32_t bit;
} BUTTONS[] = {
	{"L", SCE_CTRL_LTRIGGER},     {"R", SCE_CTRL_RTRIGGER},   {"SELECT", SCE_CTRL_SELECT},
	{"START", SCE_CTRL_START},    {"UP", SCE_CTRL_UP},        {"DOWN", SCE_CTRL_DOWN},
	{"LEFT", SCE_CTRL_LEFT},      {"RIGHT", SCE_CTRL_RIGHT},  {"TRIANGLE", SCE_CTRL_TRIANGLE},
	{"CIRCLE", SCE_CTRL_CIRCLE},  {"CROSS", SCE_CTRL_CROSS},  {"SQUARE", SCE_CTRL_SQUARE},
};

/* Return the bit of the button name, or 0 if the name is not known. */
static uint32_t button_bit(const char *name)
{
	for (unsigned int i = 0; i < sizeof(BUTTONS) / sizeof(BUTTONS[0]); i++)
		if (strcmp(name, BUTTONS[i].name) == 0)
			return BUTTONS[i].bit;
	return 0;
}

/*
 * Copy the value of the combo= line in text into value, in capitals, up to the end of the line
 * or a space. Return 1 if the line is there, else 0.
 */
static int combo_value(const char *text, char *value)
{
	for (const char *line = text; line; line = strchr(line, '\n')) {
		while (*line == '\n')
			line++;
		if (strncmp(line, KEY, sizeof(KEY) - 1) != 0)
			continue;
		const char *start = line + sizeof(KEY) - 1;
		int len = 0;
		while (len < MAX_VALUE - 1 && start[len] && start[len] != '\r' && start[len] != '\n' &&
		       start[len] != ' ') {
			value[len] = toupper(start[len]);
			len++;
		}
		value[len] = '\0';
		return 1;
	}
	return 0;
}

/* Return the buttons of value, like "L+R+SELECT". Copy an unknown name into bad and return 0. */
static uint32_t parse_combo(char *value, char *bad)
{
	uint32_t bits = 0;
	for (char *name = value; name;) {
		char *plus = strchr(name, '+');
		if (plus)
			*plus = '\0';
		uint32_t bit = button_bit(name);
		if (!bit) {
			strncpy(bad, name, MAX_VALUE);
			return 0;
		}
		bits |= bit;
		name = plus ? plus + 1 : NULL;
	}
	return bits;
}

/* Read the combo from CONFIG into combo and log the result. */
void read_config(void)
{
	char text[1024];
	char value[MAX_VALUE];
	char bad[MAX_VALUE] = "";
	char line[192];

	SceUID fd = ksceIoOpen(CONFIG, SCE_O_RDONLY, 0);
	int len = fd >= 0 ? ksceIoRead(fd, text, sizeof(text) - 1) : 0;
	if (fd >= 0)
		ksceIoClose(fd);
	text[len > 0 ? len : 0] = '\0';

	if (!combo_value(text, value)) {
		log_line("kakehashi: combo L+R+SELECT (default, no combo= line in " CONFIG ")");
		return;
	}
	char shown[MAX_VALUE];
	strncpy(shown, value, sizeof(shown));
	uint32_t bits = parse_combo(value, bad);
	if (!bits)
		snprintf(line, sizeof(line),
			 "kakehashi: combo error: unknown button '%s' in '%s', combo L+R+SELECT (default)",
			 bad, shown);
	else if (__builtin_popcount(bits) < 2)
		snprintf(line, sizeof(line),
			 "kakehashi: combo error: '%s' needs 2 or more buttons, combo L+R+SELECT (default)",
			 shown);
	else {
		combo = bits;
		snprintf(line, sizeof(line), "kakehashi: combo %s", shown);
	}
	log_line(line);
}
