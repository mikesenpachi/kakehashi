/*
 * Read the config file. Rules as on the Vita: a combo is button names joined with '+', any case,
 * at least 2 buttons; without a valid combo line the combo is DEFAULT_COMBO and the log tells why.
 * ZL and ZR are not allowed: the plugin cannot read them (they come only through ir:rst; see main.cpp).
 */

#include "config.hpp"

#include <CTRPluginFramework.hpp>

#include <cctype>
#include <cstdlib>

using namespace CTRPluginFramework;

static const char DEFAULT_COMBO[] = "L+SELECT";

static const struct
{
    const char *name;
    u32 bit;
} BUTTONS[] = {
    {"A", Key::A},           {"B", Key::B},         {"X", Key::X},
    {"Y", Key::Y},           {"L", Key::L},         {"R", Key::R},
    {"START", Key::Start},   {"SELECT", Key::Select}, {"UP", Key::DPadUp},
    {"DOWN", Key::DPadDown}, {"LEFT", Key::DPadLeft}, {"RIGHT", Key::DPadRight},
};

/* Copy the value of the key= line in text into value, up to the end of the line or a space. Return true if the line is there. */
static bool Value(const std::string &text, const std::string &key, std::string &value)
{
    std::string start = key + "=";
    size_t line = 0;
    while (line < text.size())
    {
        if (text.compare(line, start.size(), start) == 0)
        {
            size_t from = line + start.size();
            size_t to = text.find_first_of("\r\n ", from);
            value = text.substr(from, to == std::string::npos ? std::string::npos : to - from);
            return true;
        }
        size_t end = text.find('\n', line);
        line = end == std::string::npos ? text.size() : end + 1;
    }
    return false;
}

/* Return the button bits of text, like "L+SELECT", in capitals. Return 0 and the unknown name in bad on a wrong name. */
static u32 ParseCombo(const std::string &text, std::string &bad, u32 &count)
{
    u32 bits = 0;
    count = 0;
    size_t from = 0;
    while (true)
    {
        size_t plus = text.find('+', from);
        std::string name = text.substr(from, plus == std::string::npos ? std::string::npos : plus - from);
        u32 bit = 0;
        for (const auto &button : BUTTONS)
            if (name == button.name)
                bit = button.bit;
        if (!bit)
        {
            bad = name;
            return 0;
        }
        bits |= bit;
        count++;
        if (plus == std::string::npos)
            return bits;
        from = plus + 1;
    }
}

/* Set the combo from text (from the line called key), or the default with a log line on a problem. */
static void SetCombo(Config &config, std::string text, const std::string &key, std::vector<std::string> &log)
{
    for (char &c : text)
        c = toupper(c);
    std::string bad;
    u32 count = 0;
    u32 bits = ParseCombo(text, bad, count);
    if (!bits)
        log.push_back("config error: unknown button '" + bad + "' in " + key + "=" + text + ", combo " + DEFAULT_COMBO);
    else if (count < 2)
        log.push_back("config error: " + key + "=" + text + " needs 2 or more buttons, combo " + DEFAULT_COMBO);
    else
    {
        config.combo = bits;
        config.comboText = text;
        return;
    }
    std::string none;
    config.combo = ParseCombo(DEFAULT_COMBO, none, count);
    config.comboText = DEFAULT_COMBO;
}

Config ReadConfig(const std::string &path, const std::string &title, std::vector<std::string> &log)
{
    Config config;
    std::string text;
    File file;
    if (File::Open(file, path, File::READ) == File::SUCCESS)
    {
        text.resize((size_t)file.GetSize());
        if (file.Read(&text[0], text.size()) != File::SUCCESS)
            text.clear();
    }
    else
        log.push_back("config error: no file " + path + ", no sending");

    std::string port;
    Value(text, "server", config.server);
    Value(text, "port", port);
    Value(text, "token", config.token);
    config.port = (u32)strtoul(port.c_str(), nullptr, 10);
    if (config.port > 65535)
        config.port = 0;

    std::string combo;
    std::string key = "combo." + title;
    if (!Value(text, key, combo))
    {
        key = "combo";
        if (!Value(text, key, combo))
        {
            key = "default";
            combo = DEFAULT_COMBO;
        }
    }
    SetCombo(config, combo, key, log);

    log.push_back("config: server '" + config.server + "', port " + std::to_string(config.port) + ", token " +
                  (config.token.empty() ? "not set" : "set") + ", combo " + config.comboText + " (" + key + ")");
    if (config.server.empty() || !config.port)
        log.push_back("config error: server and port are needed, no sending");
    return config;
}
