#pragma once

#include <string>
#include <unordered_map>
#include <mutex>
#include <chrono>

namespace ble {

/**
 * Deduplicates BLE device events within a configurable time window.
 *
 * During a detection burst a single physical device may produce many
 * InterfacesAdded / PropertiesChanged signals per second.  The deduplicator
 * tracks when each MAC address was last forwarded and suppresses subsequent
 * events until the window expires.
 *
 * Thread-safe: all public methods may be called from different threads.
 */
class Deduplicator {
public:
    using Clock    = std::chrono::steady_clock;
    using TimePoint = Clock::time_point;

    /**
     * @param windowSeconds  How long (in seconds) to suppress duplicate
     *                       events for the same MAC address.  Default: 5.
     */
    explicit Deduplicator(int windowSeconds = 5);

    /**
     * Query whether an event for @p mac should be forwarded.
     *
     * If the MAC has not been seen, or its window has expired, the internal
     * timestamp is updated and this function returns true (pass through).
     * Otherwise the event is a duplicate and false is returned (suppress).
     *
     * @param mac  MAC address string (case-insensitive).
     * @return true  => forward the event.
     *         false => suppress the event.
     */
    bool shouldProcess(const std::string& mac);

    /**
     * Remove expired entries from the internal map to reclaim memory.
     * Calls this periodically if you expect a large number of unique devices.
     */
    void purgeExpired();

    /**
     * Remove all entries (useful for tests or after a reset).
     */
    void clear();

    /** Returns the configured deduplication window in seconds. */
    int windowSeconds() const;

private:
    std::unordered_map<std::string, TimePoint> m_lastSeen;
    mutable std::mutex m_mutex;
    std::chrono::seconds m_window;
};

} // namespace ble
