#pragma once

#include <3ds.h>

#include <string>
#include <vector>

/*
 * The settings in sdmc:/kakehashi/config.txt, the same format as the Vita's: key=value lines.
 *   server=192.168.1.10
 *   port=8766
 *   token=
 *   combo=L+SELECT
 *   combo.0004000000108800=L+R      (optional: the combo for one game, by title ID)
 */
struct Config
{
    std::string server;    /* empty: no sending */
    u32 port = 0;          /* 0: no sending */
    std::string token;     /* sent as X-Token when set */
    u32 combo = 0;         /* button bits */
    std::string comboText; /* like "L+SELECT" */
};

/* Read the config file at path; title selects a combo.<title> line. One log line per result or problem goes into log. */
Config ReadConfig(const std::string &path, const std::string &title, std::vector<std::string> &log);
