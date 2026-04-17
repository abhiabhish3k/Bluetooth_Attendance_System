#pragma once

#include <string>
#include <fstream>
#include <mutex>
#include "ble_scanner.h"

namespace ble {

/**
 * Log severity levels.
 */
enum class LogLevel {
    DEBUG = 0,
    INFO  = 1,
    WARN  = 2,
    ERROR = 3
};

/**
 * Thread-safe structured logger.
 *
 * Outputs:
 *   - Human-readable log lines to stdout (with level prefix and timestamp).
 *   - JSON-formatted device events to stdout AND optionally a log file.
 */
class Logger {
public:
    /**
     * @param logFile    Path to an optional log file.  Pass empty string to
     *                   disable file logging.
     * @param minLevel   Minimum severity level to emit.
     */
    explicit Logger(const std::string& logFile = "",
                    LogLevel minLevel = LogLevel::INFO);
    ~Logger();

    // Non-copyable
    Logger(const Logger&) = delete;
    Logger& operator=(const Logger&) = delete;

    /** Emit a structured log message at the given level. */
    void log(LogLevel level, const std::string& message);

    /** Convenience wrappers */
    void debug(const std::string& msg) { log(LogLevel::DEBUG, msg); }
    void info (const std::string& msg) { log(LogLevel::INFO,  msg); }
    void warn (const std::string& msg) { log(LogLevel::WARN,  msg); }
    void error(const std::string& msg) { log(LogLevel::ERROR, msg); }

    /**
     * Serialise a DeviceEvent as a single-line JSON object and emit it.
     *
     * Example:
     * {"address":"AA:BB:CC:DD:EE:FF","name":"MyPhone","rssi":-62,"timestamp":1712345678}
     */
    void logEvent(const DeviceEvent& event);

    /** Change the minimum log level at runtime. */
    void setLevel(LogLevel level);

private:
    std::string levelStr(LogLevel level) const;
    std::string currentTimestamp() const;
    void writeLine(const std::string& line);

    std::ofstream m_file;
    mutable std::mutex m_mutex;
    LogLevel m_minLevel;
};

} // namespace ble
