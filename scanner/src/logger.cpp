/**
 * Logger – structured JSON event output and human-readable log lines.
 */

#include "logger.h"

#include <iostream>
#include <iomanip>
#include <sstream>
#include <ctime>

namespace ble {

// ---------------------------------------------------------------------------
// Constructor / Destructor
// ---------------------------------------------------------------------------
Logger::Logger(const std::string& logFile, LogLevel minLevel)
    : m_minLevel(minLevel)
{
    if (!logFile.empty()) {
        m_file.open(logFile, std::ios::app);
        if (!m_file.is_open()) {
            std::cerr << "[Logger] Warning: could not open log file: " << logFile << "\n";
        }
    }
}

Logger::~Logger() {
    if (m_file.is_open()) {
        m_file.close();
    }
}

// ---------------------------------------------------------------------------
// setLevel
// ---------------------------------------------------------------------------
void Logger::setLevel(LogLevel level) {
    std::lock_guard<std::mutex> lock(m_mutex);
    m_minLevel = level;
}

// ---------------------------------------------------------------------------
// log
// ---------------------------------------------------------------------------
void Logger::log(LogLevel level, const std::string& message) {
    if (level < m_minLevel) return;

    std::string line = "[" + currentTimestamp() + "] [" + levelStr(level) + "] " + message;
    writeLine(line);
}

// ---------------------------------------------------------------------------
// logEvent – emit a single-line JSON object
// ---------------------------------------------------------------------------
void Logger::logEvent(const DeviceEvent& event) {
    // Escape any double-quotes in the device name
    std::string safeName;
    safeName.reserve(event.name.size());
    for (char c : event.name) {
        if (c == '"')  safeName += "\\\"";
        else if (c == '\\') safeName += "\\\\";
        else safeName += c;
    }

    // Escape beacon_id the same way
    std::string safeBeaconId;
    safeBeaconId.reserve(event.beacon_id.size());
    for (char c : event.beacon_id) {
        if (c == '"')  safeBeaconId += "\\\"";
        else if (c == '\\') safeBeaconId += "\\\\";
        else safeBeaconId += c;
    }

    std::ostringstream oss;
    oss << "{"
        << "\"address\":\"" << event.address  << "\","
        << "\"name\":\""    << safeName        << "\","
        << "\"rssi\":"      << event.rssi      << ","
        << "\"timestamp\":" << event.timestamp;

    if (!event.beacon_id.empty()) {
        oss << ",\"beacon_id\":\"" << safeBeaconId << "\"";
    }

    oss << "}";

    writeLine(oss.str());
}

// ---------------------------------------------------------------------------
// Private helpers
// ---------------------------------------------------------------------------
std::string Logger::levelStr(LogLevel level) const {
    switch (level) {
        case LogLevel::DEBUG: return "DEBUG";
        case LogLevel::INFO:  return "INFO ";
        case LogLevel::WARN:  return "WARN ";
        case LogLevel::ERROR: return "ERROR";
        default:              return "?????";
    }
}

std::string Logger::currentTimestamp() const {
    std::time_t now = std::time(nullptr);
    std::tm* tm_info = std::gmtime(&now);
    if (!tm_info) return "0000-00-00T00:00:00Z";

    std::ostringstream oss;
    oss << std::put_time(tm_info, "%Y-%m-%dT%H:%M:%SZ");
    return oss.str();
}

void Logger::writeLine(const std::string& line) {
    std::lock_guard<std::mutex> lock(m_mutex);
    std::cout << line << "\n";
    std::cout.flush();
    if (m_file.is_open()) {
        m_file << line << "\n";
        m_file.flush();
    }
}

} // namespace ble
