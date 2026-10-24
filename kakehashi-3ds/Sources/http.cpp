/*
 * The system HTTP service (http:C) with its POST memory in the SYSTEM region.
 *
 * libctru's httpcInit takes the POST memory from the plugin heap, and the service accepts only private
 * memory (svcCreateMemoryBlock). Private plugin memory (UsePrivateMemory) made 逆転裁判123 crash at
 * start, even with an empty plugin (Luma3DS issue #2225). So the POST memory comes from the SYSTEM
 * region with Luma's svcControlMemoryUnsafe, as Rosalina does for its own buffers: that memory is
 * private, and it is not taken from the game.
 *
 * HTTPC_Initialize and HTTPC_Finalize are copied from libctru (source/services/httpc.c), with only the
 * spacing changed, because they are static there. License: LICENSE-libctru.txt (zlib).
 * __httpc_servhandle is libctru's own service handle, used by its request functions.
 */

#include "http.hpp"

#include <cstring>

extern "C"
{
    extern Handle __httpc_servhandle;
    Result svcControlMemoryUnsafe(u32 *out, u32 addr0, u32 size, MemOp op, MemPerm perm); /* in libctrpf */
}

/* A free address range between the plugin heap (0x06000000, at most 5 MiB) and the plugin code (0x07000000). */
static const u32 ADDRESS = 0x06800000;

static u32 memorySize = 0;
static Handle memoryBlock = 0;

static Result HTTPC_Initialize(Handle handle, u32 sharedmem_size, Handle sharedmem_handle)
{
    u32 *cmdbuf = getThreadCommandBuffer();

    cmdbuf[0] = IPC_MakeHeader(0x1, 1, 4); // 0x10044
    cmdbuf[1] = sharedmem_size;            // POST buffer size (page aligned)
    cmdbuf[2] = IPC_Desc_CurProcessId();
    cmdbuf[4] = IPC_Desc_SharedHandles(1);
    cmdbuf[5] = sharedmem_handle; // POST buffer memory block handle

    Result ret = 0;
    if (R_FAILED(ret = svcSendSyncRequest(handle)))
        return ret;

    return cmdbuf[1];
}

static Result HTTPC_Finalize(Handle handle)
{
    u32 *cmdbuf = getThreadCommandBuffer();

    cmdbuf[0] = IPC_MakeHeader(0x39, 0, 0); // 0x390000

    Result ret = 0;
    if (R_FAILED(ret = svcSendSyncRequest(handle)))
        return ret;

    return cmdbuf[1];
}

/* True if the whole range from ADDRESS, size bytes long, is free in this process. */
static bool RangeFree(u32 size)
{
    MemInfo info;
    PageInfo page;
    return R_SUCCEEDED(svcQueryMemory(&info, &page, ADDRESS)) && info.state == MEMSTATE_FREE &&
           info.base_addr + info.size >= ADDRESS + size;
}

Result HttpStart(u32 size, std::string &step)
{
    step = "address not free";
    if (!RangeFree(size))
        return -1;

    step = "system memory";
    u32 out = 0;
    Result res = svcControlMemoryUnsafe(&out, ADDRESS, size, (MemOp)(MEMOP_REGION_SYSTEM | MEMOP_ALLOC),
                                        (MemPerm)(MEMPERM_READ | MEMPERM_WRITE));
    if (R_FAILED(res))
        return res;
    memorySize = size;
    memset((void *)ADDRESS, 0, size);

    step = "service";
    res = srvGetServiceHandle(&__httpc_servhandle, "http:C");
    if (R_SUCCEEDED(res))
    {
        step = "memory block";
        res = svcCreateMemoryBlock(&memoryBlock, ADDRESS, size, (MemPerm)0, (MemPerm)(MEMPERM_READ | MEMPERM_WRITE)); /* as libctru */
    }
    if (R_SUCCEEDED(res))
    {
        step = "initialize";
        res = HTTPC_Initialize(__httpc_servhandle, size, memoryBlock);
    }
    if (R_FAILED(res))
        HttpStop();
    return res;
}

void HttpStop(void)
{
    if (__httpc_servhandle)
    {
        HTTPC_Finalize(__httpc_servhandle);
        svcCloseHandle(__httpc_servhandle);
        __httpc_servhandle = 0;
    }
    if (memoryBlock)
    {
        svcCloseHandle(memoryBlock);
        memoryBlock = 0;
    }
    if (memorySize)
    {
        svcControlMemoryUnsafe(nullptr, ADDRESS, memorySize, MEMOP_FREE, (MemPerm)0);
        memorySize = 0;
    }
}

u32 SystemFreeKB(void)
{
    return osGetMemRegionFree(MEMREGION_SYSTEM) / 1024;
}
