#pragma once

#include <3ds.h>

#include <string>

/*
 * Start and stop the system HTTP service (http:C) with its POST memory in the SYSTEM region.
 * After HttpStart, the libctru httpc request functions (httpcOpenContext and others) work as usual.
 */

/* Start the service with size bytes (a multiple of 0x1000) of POST memory. On failure, step names the failed step. */
Result HttpStart(u32 size, std::string &step);

/* Stop the service and free the POST memory. */
void HttpStop(void);

/* Free memory in the SYSTEM region, in KB. */
u32 SystemFreeKB(void);
