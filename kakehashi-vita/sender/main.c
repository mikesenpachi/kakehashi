/*
 * kakehashi sender plugin (user, loaded in SceShell).
 *
 * Increment 5: 10 s after the shell starts, the thread reads the server, port and token from
 * CONFIG. Then it checks the queue folder every 2 s. It sends each file to the Shot API,
 * one at a time, and deletes it after a 200 reply. After a failure it waits 30 s.
 * When Wi-Fi is not connected (flight mode, out of range), it does not try and logs nothing.
 * Without a valid config, it logs the problem and sends nothing.
 * Queue names are <YYYYMMDD-HHMMSS>-<n>_<titleid>.bmp: taken is the first 15 characters, game is
 * the part between '_' and the extension.
 */

#include <psp2/io/dirent.h>
#include <psp2/io/fcntl.h>
#include <psp2/io/stat.h>
#include <psp2/kernel/clib.h>
#include <psp2/kernel/modulemgr.h>
#include <psp2/kernel/threadmgr.h>
#include <psp2/net/net.h>
#include <psp2/net/netctl.h>

#define FOLDER "ux0:data/kakehashi"
#define QUEUE FOLDER "/queue"
#define LOG FOLDER "/sender.txt"
#define OLD_LOG FOLDER "/sender.old.txt"
#define MAX_LOG (64 * 1024)
#define CONFIG FOLDER "/config.txt"
#define START_US (10 * 1000 * 1000) /* NetCtl is not ready at the start of the shell: an earlier call hung the boot */
#define POLL_US (2 * 1000 * 1000)
#define RETRY_US (30 * 1000 * 1000)
#define SEND_TIMEOUT_US (5 * 1000 * 1000)
#define REPLY_TIMEOUT_US (30 * 1000 * 1000) /* the webapp runs OCR before it replies */
#define TAKEN_LEN 15                         /* YYYYMMDD-HHMMSS */

static char chunk[32 * 1024];
static char server[64];
static char token[64];
static int port;
static SceNetInAddr server_addr;

/* Append one line of text to the log file. */
static void log_line(const char *text)
{
	SceUID fd = sceIoOpen(LOG, SCE_O_WRONLY | SCE_O_CREAT | SCE_O_APPEND, 0666);
	if (fd < 0)
		return;
	sceIoWrite(fd, text, sceClibStrnlen(text, 256));
	sceIoWrite(fd, "\n", 1);
	sceIoClose(fd);
}

/* At boot, a log over MAX_LOG becomes OLD_LOG, so the log never grows past about 64 KB. */
static void rotate_log(void)
{
	SceIoStat stat;
	if (sceIoGetstat(LOG, &stat) >= 0 && stat.st_size > MAX_LOG) {
		sceIoRemove(OLD_LOG);
		sceIoRename(LOG, OLD_LOG);
	}
}

/* Log a step name and its result as hex. */
static void log_result(const char *step, int ret)
{
	char line[320];
	sceClibSnprintf(line, sizeof(line), "kakehashi sender: %s %08X", step, ret);
	log_line(line);
}

/*
 * Copy the value of key from the config text into value, up to the end of the line or a space.
 * Return 1 if the key is there, else 0.
 */
static int config_value(const char *text, const char *key, char *value, SceSize size)
{
	SceSize key_len = sceClibStrnlen(key, 32);
	for (const char *line = text; line; line = sceClibStrchr(line, '\n')) {
		while (*line == '\n')
			line++;
		if (sceClibStrncmp(line, key, key_len) != 0 || line[key_len] != '=')
			continue;
		const char *start = line + key_len + 1;
		SceSize len = 0;
		while (len < size - 1 && start[len] && start[len] != '\r' && start[len] != '\n' &&
		       start[len] != ' ')
			len++;
		sceClibMemcpy(value, start, len);
		value[len] = '\0';
		return 1;
	}
	return 0;
}

/* Return the port number in text, or 0 if it is not a number from 1 to 65535. */
static int parse_port(const char *text)
{
	int value = 0;
	for (int i = 0; text[i]; i++) {
		if (text[i] < '0' || text[i] > '9' || i >= 5)
			return 0;
		value = value * 10 + text[i] - '0';
	}
	return value <= 65535 ? value : 0;
}

/* Read server, port and token from CONFIG and log the result. Return 1 if they are valid. */
static int read_config(void)
{
	char text[1024];
	char port_text[16] = "";
	SceUID fd = sceIoOpen(CONFIG, SCE_O_RDONLY, 0);
	if (fd < 0) {
		log_result("no config file " CONFIG, fd);
		return 0;
	}
	int len = sceIoRead(fd, text, sizeof(text) - 1);
	sceIoClose(fd);
	text[len > 0 ? len : 0] = '\0';

	config_value(text, "server", server, sizeof(server));
	config_value(text, "port", port_text, sizeof(port_text));
	config_value(text, "token", token, sizeof(token));
	port = parse_port(port_text);
	char line[256];
	sceClibSnprintf(line, sizeof(line), "kakehashi sender: config server '%s', port '%s', token %s",
			server, port_text, token[0] ? "set" : "not set");
	log_line(line);
	if (sceNetInetPton(SCE_NET_AF_INET, server, &server_addr) != 1) {
		log_line("kakehashi sender: config error: server must be an IPv4 address, like 192.168.1.10");
		return 0;
	}
	if (!port) {
		log_line("kakehashi sender: config error: port must be a number from 1 to 65535");
		return 0;
	}
	return 1;
}

/*
 * Find the first queue file with a name we can read. Copy its name to name and its size to size.
 * Return 1 if found, else 0.
 */
static int next_file(char *name, SceSize name_size, unsigned int *size)
{
	SceUID dir = sceIoDopen(QUEUE);
	if (dir < 0)
		return 0;
	SceIoDirent entry;
	int found = 0;
	while (!found && sceIoDread(dir, &entry) > 0) {
		const char *underscore = sceClibStrchr(entry.d_name, '_');
		if (SCE_S_ISDIR(entry.d_stat.st_mode) || !underscore || underscore - entry.d_name <= TAKEN_LEN)
			continue;
		sceClibStrncpy(name, entry.d_name, name_size);
		name[name_size - 1] = '\0';
		*size = (unsigned int)entry.d_stat.st_size;
		found = 1;
	}
	sceIoDclose(dir);
	return found;
}

/* Send all len bytes. Return 0, or the error of sceNetSend. */
static int send_all(int s, const char *data, int len)
{
	while (len > 0) {
		int sent = sceNetSend(s, data, len, 0);
		if (sent < 0)
			return sent;
		data += sent;
		len -= sent;
	}
	return 0;
}

/* Open a TCP connection to the webapp. Return the socket, or an error. */
static int connect_server(void)
{
	SceNetSockaddrIn addr;
	sceClibMemset(&addr, 0, sizeof(addr));
	addr.sin_len = sizeof(addr);
	addr.sin_family = SCE_NET_AF_INET;
	addr.sin_port = sceNetHtons(port);
	addr.sin_addr = server_addr;

	int s = sceNetSocket("kakehashi", SCE_NET_AF_INET, SCE_NET_SOCK_STREAM, 0);
	if (s < 0)
		return s;
	int send_timeout = SEND_TIMEOUT_US;
	int reply_timeout = REPLY_TIMEOUT_US;
	sceNetSetsockopt(s, SCE_NET_SOL_SOCKET, SCE_NET_SO_SNDTIMEO, &send_timeout, sizeof(send_timeout));
	sceNetSetsockopt(s, SCE_NET_SOL_SOCKET, SCE_NET_SO_RCVTIMEO, &reply_timeout, sizeof(reply_timeout));
	int ret = sceNetConnect(s, (SceNetSockaddr *)&addr, sizeof(addr));
	if (ret < 0) {
		sceNetSocketClose(s);
		return ret;
	}
	return s;
}

/* Send the file body from the queue in chunks. Return 0, or an error. */
static int send_body(int s, const char *path)
{
	SceUID fd = sceIoOpen(path, SCE_O_RDONLY, 0);
	if (fd < 0)
		return fd;
	int ret = 0;
	int got;
	while (ret == 0 && (got = sceIoRead(fd, chunk, sizeof(chunk))) > 0)
		ret = send_all(s, chunk, got);
	sceIoClose(fd);
	return ret < 0 ? ret : (got < 0 ? got : 0);
}

/*
 * POST one queue file to the Shot API and log the status line of the reply.
 * Return 1 if the webapp replied 200, else 0.
 */
static int send_file(const char *name, unsigned int size)
{
	char path[320];
	char head[640];
	const char *underscore = sceClibStrchr(name, '_');
	const char *dot = sceClibStrrchr(name, '.');
	int game_len = dot && dot > underscore ? dot - underscore - 1 : sceClibStrnlen(underscore + 1, 64);
	sceClibSnprintf(path, sizeof(path), QUEUE "/%s", name);
	int head_len = sceClibSnprintf(head, sizeof(head),
				       "POST /shot?game=%.*s&taken=%.*s HTTP/1.0\r\n"
				       "Host: %s:%d\r\n"
				       "%s%s%s"
				       "Content-Type: application/octet-stream\r\n"
				       "Content-Length: %u\r\n\r\n",
				       game_len, underscore + 1, TAKEN_LEN, name, server, port,
				       token[0] ? "X-Token: " : "", token, token[0] ? "\r\n" : "", size);

	int s = connect_server();
	if (s < 0) {
		log_result("connect", s);
		return 0;
	}
	int ret = send_all(s, head, head_len);
	if (ret == 0)
		ret = send_body(s, path);
	if (ret < 0) {
		log_result("send", ret);
		sceNetSocketClose(s);
		return 0;
	}
	char reply[64];
	ret = sceNetRecv(s, reply, sizeof(reply) - 1, 0);
	sceNetSocketClose(s);
	if (ret <= 0) {
		log_result("recv", ret);
		return 0;
	}
	reply[ret] = '\0';
	for (int i = 0; i < ret; i++)
		if (reply[i] == '\r' || reply[i] == '\n')
			reply[i] = '\0';
	log_line(reply);
	return sceClibStrncmp(reply + 8, " 200", 4) == 0;
}

/* Send the queue, one file at a time. Return 1 if all files went out, 0 at the first failure. */
static int send_queue(void)
{
	char name[256];
	char line[320];
	unsigned int size;

	while (next_file(name, sizeof(name), &size)) {
		sceClibSnprintf(line, sizeof(line), "kakehashi sender: send %s (%u bytes)", name, size);
		log_line(line);
		if (!send_file(name, size))
			return 0;
		sceClibSnprintf(line, sizeof(line), QUEUE "/%s", name);
		log_result("remove", sceIoRemove(line));
	}
	return 1;
}

/* Return 1 if Wi-Fi is connected, else 0. */
static int wifi_on(void)
{
	int state = SCE_NETCTL_STATE_DISCONNECTED;
	return sceNetCtlInetGetState(&state) == 0 && state == SCE_NETCTL_STATE_CONNECTED;
}

static int sender_thread(SceSize args, void *argp)
{
	sceKernelDelayThread(START_US);
	if (!read_config())
		return 0;
	for (;;) {
		sceKernelDelayThread(POLL_US);
		if (wifi_on() && !send_queue()) {
			log_line("kakehashi sender: retry in 30 s");
			sceKernelDelayThread(RETRY_US);
		}
	}
	return 0;
}

int _start(SceSize args, void *argp) __attribute__((weak, alias("module_start")));

int module_start(SceSize args, void *argp)
{
	sceIoMkdir(FOLDER, 0777);
	rotate_log();
	log_line("kakehashi sender: loaded");
	SceUID thread = sceKernelCreateThread("kakehashi_sender", sender_thread, 0x10000100, 0x4000, 0,
					      0, NULL);
	log_result("thread", thread);
	if (thread >= 0)
		sceKernelStartThread(thread, 0, NULL);
	return SCE_KERNEL_START_SUCCESS;
}

int module_stop(SceSize args, void *argp)
{
	return SCE_KERNEL_STOP_SUCCESS;
}
