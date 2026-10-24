/*
 * kakehashi 3DS plugin (3GX, CTRPluginFramework), loaded by the Luma3DS plugin loader into a game.
 *
 * When the game starts, read CONFIG, show a "kakehashi loaded" notice and log the title ID of the game to LOG.
 * Then read the buttons about 60 times a second. Each time the combo goes down, the next frame
 * callbacks copy both screens (in parts), and main() writes them as one 400x480 BMP into QUEUE:
 * the top screen above, the bottom screen centered below. A notice shows "SAVED" or "FAILED".
 * main() runs on the plugin's own thread, not the game's.
 * The game also sees the combo: CTRPF cannot hide a button from the game. ZL and ZR come only through
 * ir:rst, which DQ8 does not update, and starting it from the plugin broke the game's C-stick.
 *
 * A low priority sender thread sends each shot in QUEUE to the Shot API and deletes it after a 200.
 * It uses the system HTTP service (http:C), not sockets: a game that started the socket service
 * itself owns it, and soc:U allows one start per process. Its POST memory is in the SYSTEM region (http.cpp).
 */

#include <3ds.h>
#include <CTRPluginFramework.hpp>

#include "config.hpp"
#include "http.hpp"

#include <cstring>
#include <ctime>
#include <string>
#include <vector>

namespace CTRPluginFramework
{
    static const std::string FOLDER = "/kakehashi";
    static const std::string LOG = FOLDER + "/log.txt";
    static const std::string QUEUE = FOLDER + "/queue";
    static const std::string CONFIG = FOLDER + "/config.txt";

    /* Read once at start, before the sender thread starts. */
    static Config config;

    /* Screen sizes. The shot is both screens: top above, bottom centered below. */
    static const u32 WIDTH = 400;        /* top screen, and the shot */
    static const u32 BOTTOM_WIDTH = 320;
    static const u32 HEIGHT = 240;       /* each screen */
    static const u32 PAD = (WIDTH - BOTTOM_WIDTH) / 2;

    static const Time POLL = Milliseconds(16);

    /* Set when the game closes. The framework waits at most 1 s for main() to return. */
    static volatile bool exiting = false;

    /* Append one line of text to the log file. */
    static void LogLine(const std::string &text)
    {
        File file;
        if (File::Open(file, LOG, File::WRITE | File::CREATE | File::APPEND) == File::SUCCESS)
            file.WriteLine(text);
    }

    /*
     * Finding the game's hid shared memory (the buttons). With UseGameHidMemory, CTRPF first points
     * hidSharedMem to a fake block of zeros in the plugin heap. A hook on the game's svc 0x1F sets the
     * real block, but it finds the call by a code pattern, which misses in some games (Pokemon Omega Ruby,
     * Mario & Luigi RPG3 DX: no combo was seen). Then the plugin looks for the block itself.
     * The game maps its shared memory from SHARED_START; the hid block is read-only.
     */
    static const u32 SHARED_START = 0x10000000;
    static const u32 SHARED_END = 0x14000000;

    extern "C" void hidSetSharedMem(vu32 *sharedMem); /* in libctrpf, not in its headers */

    static bool HidFound(void)
    {
        return (u32)hidSharedMem >= SHARED_START && (u32)hidSharedMem < SHARED_END;
    }

    /* The same check as CTRPF's hook (pluginInit.cpp): recent time stamps and small indexes, for the pad and the touch screen. */
    static bool LooksLikeHid(u32 base)
    {
        u64 now = svcGetSystemTick();
        u64 padTick = ((vu64 *)base)[0];
        u32 padIndex = ((vu32 *)base)[4];
        u64 touchTick = ((vu64 *)(base + 0xA8))[0];
        u32 touchIndex = ((vu32 *)(base + 0xA8))[4];
        return llabs(now - padTick) < 1000000000LL && llabs(now - touchTick) < 1000000000LL && padIndex < 8 &&
               touchIndex < 8;
    }

    /* Look for the game's hid block among the shared blocks. If found, read the buttons from it. */
    static void FindHid(void)
    {
        u32 address = SHARED_START;
        while (address < SHARED_END)
        {
            MemInfo info;
            PageInfo page;
            if (R_FAILED(svcQueryMemory(&info, &page, address)))
                return;
            if (info.state == MEMSTATE_SHARED && info.perm == MEMPERM_READ && LooksLikeHid(info.base_addr))
            {
                hidSetSharedMem((vu32 *)info.base_addr);
                LogLine(Utils::Format("kakehashi: buttons from %08lX (found by scan)", info.base_addr));
                return;
            }
            address = info.base_addr + info.size;
        }
    }

    /*
     * True if the hid shared memory that the buttons are read from is mapped.
     * The game unmaps it when it closes, before the framework's EXIT event, and the framework
     * hooks only the map call (svc 0x1F), not the unmap: a read after that crashed in
     * hidScanInput (Luma dump: pc in hidScanInput, fault address 0x10000010).
     */
    static bool HidMapped(void)
    {
        MemInfo info;
        PageInfo page;
        return R_SUCCEEDED(svcQueryMemory(&info, &page, (u32)hidSharedMem)) && info.state != MEMSTATE_FREE &&
               (info.perm & MEMPERM_READ);
    }

    /*
     * The shot: a BMP file (54-byte header, then rows of WIDTH pixels, bottom row first, 3 bytes per pixel)
     * of both screens. One buffer for main() and the sender. shotLock: main() holds it from the combo until
     * the file is written, the sender while it reads a file and gives it to the HTTP service.
     */
    static const u32 HEADER = 54;
    static const u32 ROW = WIDTH * 3;
    static const u32 SHOT_SIZE = HEADER + 2 * HEIGHT * ROW;
    static u32 shotWords[(SHOT_SIZE + 3) / 4]; /* u32 for httpcAddPostDataRaw */
    static u8 *const shot = (u8 *)shotWords;
    static LightLock shotLock;

    /*
     * The screen frames as the GPU stores them: rotated, one column per x (bottom pixel first), Stride
     * bytes from one column to the next (DQ8: 720, Mario & Luigi: 768, ACNL: 512, longer than 240 pixels).
     * The pixel format is Format & 7 (GSP); CTRPF's BytesPerPixel was wrong in ACNL (3 for RGB565).
     * Bytes per pixel for RGBA8, BGR8, RGB565, RGB5A1, RGBA4:
     */
    static const u32 FORMAT_BYTES[] = {4, 3, 2, 2, 2};

    /* Each frame is copied in PARTS parts, one per frame: a whole top copy takes 11 to 12 ms. */
    static const u32 PARTS = 4;

    /* Set by main() after a combo; OnFrame copies one part of each screen per frame and clears it after the last. */
    static volatile bool copyWanted = false;
    static volatile u32 topParts = 0;
    static volatile u32 bottomParts = 0;
    static volatile u32 copyTicks = 0; /* the longest part */

    /* Set by OnFrame when a screen has an unknown format or a too short stride: then nothing is copied. */
    static volatile bool badScreen = false;
    static volatile u32 badValues[4]; /* IsTop, BytesPerPixel, Stride, Format */

    /* Put one frame pixel (format 0 to 4) into the shot as B, G, R. */
    static void PutPixel(u8 *out, const u8 *in, u32 format)
    {
        u32 v = in[0] | in[1] << 8;
        switch (format)
        {
        case 0: /* RGBA8: bytes A, B, G, R */
            out[0] = in[1], out[1] = in[2], out[2] = in[3];
            break;
        case 1: /* BGR8 */
            out[0] = in[0], out[1] = in[1], out[2] = in[2];
            break;
        case 2: /* RGB565 */
            out[0] = (v & 31) << 3, out[1] = (v >> 5 & 63) << 2, out[2] = (v >> 11 & 31) << 3;
            break;
        case 3: /* RGB5A1 */
            out[0] = (v >> 1 & 31) << 3, out[1] = (v >> 6 & 31) << 3, out[2] = (v >> 11 & 31) << 3;
            break;
        default: /* RGBA4 */
            out[0] = (v >> 4 & 15) * 17, out[1] = (v >> 8 & 15) * 17, out[2] = (v >> 12 & 15) * 17;
            break;
        }
    }

    /*
     * Copy the next part of screen (width columns in all) into the shot, unless all parts are done.
     * Frame column x, pixel p goes to BMP row firstRow + p, pixel firstX + x.
     * Each column is first copied in one block: the frame is read in large blocks, as one memcpy did.
     */
    static void CopyPart(const Screen &screen, u32 width, u32 firstRow, u32 firstX, volatile u32 &done)
    {
        static u8 column[HEIGHT * 4]; /* static: this runs on the game's thread and stack */
        if (done == PARTS)
            return;
        u64 start = svcGetSystemTick();
        u32 format = screen.Format & 7;
        u32 bytes = FORMAT_BYTES[format];
        const u8 *frame = screen.GetFramebuffer(0, HEIGHT - 1);
        u32 columns = width / PARTS;
        for (u32 x = done * columns; x < (done + 1) * columns; x++)
        {
            memcpy(column, frame + x * screen.Stride, HEIGHT * bytes);
            u8 *out = shot + HEADER + firstRow * ROW + (firstX + x) * 3;
            for (u32 p = 0; p < HEIGHT; p++, out += ROW)
                PutPixel(out, column + p * bytes, format);
        }
        u32 ticks = (u32)(svcGetSystemTick() - start);
        if (ticks > copyTicks)
            copyTicks = ticks;
        done++;
    }

    /*
     * Notice: "SAVED" or "FAILED" in the top-left corner of the top screen for NOTICE_TIME, as on the Vita.
     * CTRPF draws its own notices (OSD::Notify) into the frame before it calls OnFrame, for 5 s, so a
     * "shot #6" notice was in the next shot. This notice is drawn by OnFrame itself, never while a copy runs.
     */
    static const u64 NOTICE_TIME = 1500 * CPU_TICKS_PER_MSEC;
    static const char *volatile noticeText = "";
    static volatile u64 noticeEnd = 0;

    /* Show text from now on, for NOTICE_TIME. */
    static void ShowNotice(const char *text)
    {
        noticeText = text;
        noticeEnd = svcGetSystemTick() + NOTICE_TIME;
    }

    /* Draw the notice on the top screen while it is shown. Return true if it was drawn. */
    static bool DrawNotice(const Screen &screen)
    {
        if (!screen.IsTop || svcGetSystemTick() > noticeEnd)
            return false;
        screen.Draw(noticeText, 10, 10, Color::White, Color::Black);
        return true;
    }

    /*
     * Called by the game's display code each frame, once per screen. Only here (or with the game
     * paused) are the Screen values valid; OSD::GetTopScreen() in main() gave all zeros.
     * The game waits while this runs, so only one part per frame here (ReadPixel per pixel took
     * 97 ms). Only the left image: the user never plays with 3D on.
     * The top screen is the upper half of the shot (BMP rows HEIGHT and up), the bottom screen the lower half.
     * Only known formats with a stride of at least one column are copied: else the copy could read past the frame.
     * While no copy runs, it draws the notice instead (DrawNotice).
     */
    static bool OnFrame(const Screen &screen)
    {
        if (!copyWanted)
            return DrawNotice(screen);
        u32 format = screen.Format & 7;
        if (format > 4 || screen.Stride < HEIGHT * FORMAT_BYTES[format])
        {
            badValues[0] = screen.IsTop;
            badValues[1] = screen.BytesPerPixel;
            badValues[2] = screen.Stride;
            badValues[3] = screen.Format;
            badScreen = true;
            copyWanted = false;
            return false;
        }
        if (screen.IsTop)
            CopyPart(screen, WIDTH, HEIGHT, 0, topParts);
        else
            CopyPart(screen, BOTTOM_WIDTH, 0, PAD, bottomParts);
        if (topParts == PARTS && bottomParts == PARTS)
            copyWanted = false;
        return false;
    }

    /* Put a 32-bit value into a buffer, low byte first. */
    static void Put32(u8 *at, u32 value)
    {
        at[0] = value;
        at[1] = value >> 8;
        at[2] = value >> 16;
        at[3] = value >> 24;
    }

    /*
     * Put the BMP header into the shot and make the sides of the bottom screen black.
     * Needed before each copy: the sender uses the same buffer.
     */
    static void StartShot(void)
    {
        memset(shot, 0, HEADER);
        shot[0] = 'B';
        shot[1] = 'M';
        Put32(shot + 2, SHOT_SIZE);
        Put32(shot + 10, HEADER);
        Put32(shot + 14, 40);
        Put32(shot + 18, WIDTH);
        Put32(shot + 22, 2 * HEIGHT);
        shot[26] = 1;  /* planes */
        shot[28] = 24; /* bits per pixel */
        Put32(shot + 34, SHOT_SIZE - HEADER);

        for (u32 r = 0; r < HEIGHT; r++)
        {
            u8 *row = shot + HEADER + r * ROW;
            memset(row, 0, PAD * 3);
            memset(row + (PAD + BOTTOM_WIDTH) * 3, 0, PAD * 3);
        }
    }

    /*
     * Write the shot to a temp file with one write, then rename it into QUEUE. Return the file name or an error.
     * One write, not one per row: 240 small writes stopped the music of DQ8 (a digital copy that
     * streams its music from the SD card). CTRPF and Rosalina also write their screenshots in one block.
     */
    static std::string WriteShot(int count, const std::string &title)
    {
        time_t now = time(nullptr);
        char stamp[16];
        strftime(stamp, sizeof(stamp), "%Y%m%d-%H%M%S", gmtime(&now)); /* the 3DS clock is local time */
        std::string name = Utils::Format("%s-%d_%s.bmp", stamp, count, title.c_str());
        std::string temp = QUEUE + "/" + name + ".tmp";

        File file;
        if (File::Open(file, temp, File::WRITE | File::CREATE | File::TRUNCATE) != File::SUCCESS)
            return "open failed";
        int res = file.Write(shot, SHOT_SIZE);
        file.Close();
        if (res != File::SUCCESS)
            return Utils::Format("write failed %d", res);
        if (File::Rename(temp, QUEUE + "/" + name) != File::SUCCESS)
            return "rename failed";
        return name;
    }

    /*
     * Sender: a low priority thread sends each shot in QUEUE to the Shot API and deletes it after a 200.
     * After a failure it waits RETRY and tries again. With Wi-Fi off, a request fails with D8A0A049.
     */
    static const std::string SENDER_LOG = FOLDER + "/sender.txt";
    static const Time IDLE = Seconds(5);
    static const Time RETRY = Seconds(30);

    /* Append one line of text to the sender log (its own file: two threads must not open one file). */
    static void SenderLog(const std::string &text)
    {
        File file;
        if (File::Open(file, SENDER_LOG, File::WRITE | File::CREATE | File::APPEND) == File::SUCCESS)
            file.WriteLine(text);
    }

    /* Sleep for time, but stop early when the game closes. */
    static void Wait(Time time)
    {
        Clock clock;
        while (!exiting && clock.GetElapsedTime() < time)
            Sleep(Milliseconds(100));
    }

    /* Return the name of the oldest shot in QUEUE, or "" if there is none. Names sort by time. */
    static std::string OldestShot(void)
    {
        Directory dir;
        std::vector<std::string> names;
        if (Directory::Open(dir, QUEUE) == Directory::SUCCESS)
            dir.ListFiles(names, ".bmp");
        std::string oldest;
        for (const std::string &name : names)
            if (name.size() > 4 && name.compare(name.size() - 4, 4, ".bmp") == 0 && (oldest.empty() || name < oldest))
                oldest = name;
        return oldest;
    }

    /* Read the file into the shot buffer. Return its size, or 0 on failure. The caller holds shotLock. */
    static u32 ReadShot(const std::string &path)
    {
        File file;
        if (File::Open(file, path, File::READ) != File::SUCCESS)
            return 0;
        u32 size = (u32)file.GetSize();
        if (size == 0 || size > SHOT_SIZE || file.Read(shot, size) != File::SUCCESS)
            return 0;
        return size;
    }

    /*
     * POST the shot file name to the Shot API. Name: <YYYYMMDD-HHMMSS>-<n>_<titleid>.bmp.
     * Return "HTTP <status>", or the step that failed and its result code.
     * The shot buffer is needed only until httpcAddPostDataRaw returns: the service copies the data
     * then (test: the buffer cleared right after it, the webapp still got the right shot).
     */
    static std::string SendShot(const std::string &name)
    {
        std::string taken = name.substr(0, 15);
        std::string game = name.substr(name.find('_') + 1);
        game = game.substr(0, game.size() - 4);
        std::string url = "http://" + config.server + ":" + std::to_string(config.port) + "/shot?game=" + game +
                          "&taken=" + taken;

        httpcContext context;
        Result res = httpcOpenContext(&context, HTTPC_METHOD_POST, url.c_str(), 0);
        if (R_FAILED(res))
            return Utils::Format("open failed %08lX", res);
        std::string step = "header";
        res = httpcAddRequestHeaderField(&context, "User-Agent", "kakehashi-3ds");
        if (R_SUCCEEDED(res) && !config.token.empty())
            res = httpcAddRequestHeaderField(&context, "X-Token", config.token.c_str());
        if (R_SUCCEEDED(res))
        {
            LightLock_Lock(&shotLock);
            u32 size = ReadShot(QUEUE + "/" + name);
            step = size ? "post data" : "read";
            res = size ? httpcAddPostDataRaw(&context, shotWords, size) : -1;
            LightLock_Unlock(&shotLock);
        }
        if (R_SUCCEEDED(res))
        {
            step = "request";
            res = httpcBeginRequest(&context);
        }
        u32 status = 0;
        if (R_SUCCEEDED(res))
        {
            step = "status";
            res = httpcGetResponseStatusCode(&context, &status);
        }
        httpcCloseContext(&context);
        if (R_FAILED(res))
            return Utils::Format("%s failed %08lX", step.c_str(), res);
        return Utils::Format("HTTP %lu", status);
    }

    /* Set by the sender when it has stopped the HTTP service and ends. main() waits for it on close. */
    static volatile bool senderDone = false;

    /* Start the HTTP service. The POST memory holds the POST data: with none, httpcAddPostDataRaw failed with D8A0A003. */
    static bool StartHttp(void)
    {
        u32 before = SystemFreeKB();
        std::string step;
        Result res = HttpStart((SHOT_SIZE + 0xFFF) & ~0xFFF, step);
        if (R_FAILED(res))
        {
            SenderLog(Utils::Format("sender: HTTP start failed at %s, %08lX, SYSTEM free %lu KB", step.c_str(), res, before));
            return false;
        }
        SenderLog(Utils::Format("sender: HTTP started, SYSTEM free %lu KB, then %lu KB", before, SystemFreeKB()));
        return true;
    }

    static void StopHttp(void)
    {
        HttpStop();
        SenderLog(Utils::Format("sender: HTTP stopped, SYSTEM free %lu KB", SystemFreeKB()));
    }

    /*
     * The sender thread. The HTTP service runs only while there are shots to send: when the game closed
     * with the service running, the next start of the game stayed at the "Nintendo 3DS" screen.
     * Logs a failure only when it differs from the last one, so Wi-Fi off does not fill the log.
     */
    static void Sender(void *)
    {
        bool started = false;
        std::string lastError;
        while (!exiting)
        {
            std::string name = OldestShot();
            if (name.empty())
            {
                if (started)
                    StopHttp();
                started = false;
                Wait(IDLE);
                continue;
            }
            if (!started && !(started = StartHttp()))
            {
                Wait(RETRY);
                continue;
            }
            u64 start = svcGetSystemTick();
            std::string error = SendShot(name);
            u32 ms = (u32)((svcGetSystemTick() - start) / CPU_TICKS_PER_MSEC);
            if (error == "HTTP 200")
            {
                File::Remove(QUEUE + "/" + name);
                SenderLog(Utils::Format("sender: sent %s, %lu ms", name.c_str(), ms));
                lastError.clear();
                continue;
            }
            if (error != lastError)
                SenderLog("sender: " + name + ": " + error + ", wait and try again");
            lastError = error;
            Wait(RETRY);
        }
        if (started)
            StopHttp();
        senderDone = true;
    }

    /*
     * Write one shot-sized file into QUEUE and delete it, while the game loads. Return the time in ms.
     * The first shot write after a start often took about 3 s, and the game stuttered meanwhile (it waits
     * for the SD card). With this warm-up, 3 combos wrote in about 180 ms, but the warm-up itself took
     * only 146 ms, so the cause of the slow writes is not known. The .tmp name keeps the sender away.
     */
    static u32 WarmUp(void)
    {
        u64 start = svcGetSystemTick();
        std::string path = QUEUE + "/warmup.tmp";
        File file;
        if (File::Open(file, path, File::WRITE | File::CREATE | File::TRUNCATE) == File::SUCCESS)
        {
            file.Write(shot, SHOT_SIZE);
            file.Close();
        }
        File::Remove(path);
        return (u32)((svcGetSystemTick() - start) / CPU_TICKS_PER_MSEC);
    }

    static void OnProcessEvent(Process::Event event)
    {
        if (event == Process::Event::EXIT)
            exiting = true;
    }

    /*
     * Called before main, when the plugin starts.
     * UseGameHidMemory: read the buttons from the game's own hid memory instead of opening a second
     * hid session. Test: with the second session, the C-stick did not work in DQ8 (New 3DS XL).
     */
    void PatchProcess(FwkSettings &settings)
    {
        settings.UseGameHidMemory = true;
    }

    int main(void)
    {
        Directory::Create(FOLDER);
        Directory::Create(QUEUE);
        std::string title;
        Process::GetTitleID(title);
        LogLine("kakehashi: loaded in " + title);
        std::vector<std::string> configLog;
        config = ReadConfig(CONFIG, title, configLog);
        for (const std::string &line : configLog)
            LogLine("kakehashi: " + line);
        LogLine(Utils::Format("kakehashi: warm-up write %lu ms", WarmUp()));
        ShowNotice("kakehashi loaded");
        Process::SetProcessEventCallback(OnProcessEvent);
        LightLock_Init(&shotLock);
        OSD::Run(OnFrame);
        /* Priority 0x3F, the lowest: the sender runs only when the game's threads wait. Without server and port, no sender. */
        senderDone = config.server.empty() || !config.port;
        if (!senderDone && !threadCreate(Sender, nullptr, 0x8000, 0x3F, -2, true))
        {
            LogLine("kakehashi: sender thread not started");
            senderDone = true;
        }

        int count = 0;
        bool wasDown = false;
        bool unmappedLogged = false;
        bool hidLogged = false;
        Clock scanClock;
        while (!exiting)
        {
            Sleep(POLL);
            if (!HidFound())
            {
                if (scanClock.GetElapsedTime() > Seconds(1))
                {
                    FindHid();
                    scanClock.Restart();
                }
                continue;
            }
            if (!hidLogged)
                LogLine(Utils::Format("kakehashi: buttons from %08lX", (u32)hidSharedMem));
            hidLogged = true;
            if (!HidMapped())
            {
                if (!unmappedLogged)
                    LogLine("kakehashi: hid memory unmapped, no button reads");
                unmappedLogged = true;
                continue;
            }
            Controller::Update();
            bool down = Controller::IsKeysDown(config.combo);
            if (down && !wasDown)
            {
                count++;
                u64 start = svcGetSystemTick();
                LightLock_Lock(&shotLock);
                u64 locked = svcGetSystemTick();
                StartShot();
                topParts = 0;
                bottomParts = 0;
                copyTicks = 0;
                badScreen = false;
                copyWanted = true;
                while (copyWanted && !exiting)
                    Sleep(POLL);
                if (badScreen)
                {
                    LogLine(Utils::Format("kakehashi: combo #%d, screen not handled: top %lu, bytes per pixel %lu, stride %lu, format %lu",
                                          count, badValues[0], badValues[1], badValues[2], badValues[3]));
                    ShowNotice("FAILED");
                }
                else if (!copyWanted)
                {
                    u64 copied = svcGetSystemTick();
                    std::string result = WriteShot(count, title);
                    u64 written = svcGetSystemTick();
                    LogLine(Utils::Format("kakehashi: combo #%d, lock wait %lu ms, copy part max %lu us, write %lu ms, ", count,
                                          (u32)((locked - start) / CPU_TICKS_PER_MSEC), (u32)(copyTicks / CPU_TICKS_PER_USEC),
                                          (u32)((written - copied) / CPU_TICKS_PER_MSEC)) +
                            result);
                    bool saved = result.size() > 4 && result.compare(result.size() - 4, 4, ".bmp") == 0;
                    ShowNotice(saved ? "SAVED" : "FAILED");
                }
                LightLock_Unlock(&shotLock);
            }
            wasDown = down;
        }
        /* The framework waits at most 1 s for main(): give the sender up to 800 ms to stop the HTTP service. */
        Clock clock;
        while (!senderDone && clock.GetElapsedTime() < Milliseconds(800))
            Sleep(Milliseconds(10));
        LogLine(senderDone ? "kakehashi: game closing, sender done" : "kakehashi: game closing, sender still running");
        return 0;
    }
}
