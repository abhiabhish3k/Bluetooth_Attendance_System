/**
 * dedup.h — Time-window-based BLE advertisement deduplicator.
 *
 * Each BLE address is accepted at most once per DEDUP_WINDOW_MS milliseconds
 * (configured in config.h).  The map is pruned automatically to prevent
 * unbounded memory growth in long-running deployments.
 */

#pragma once

#include <map>
#include <string>
#include "config.h"

class Deduplicator {
public:
    /**
     * Return true if the event for this MAC address should be accepted.
     * Updates the last-seen timestamp when accepted.
     */
    bool accept(const std::string& mac);

    /**
     * Remove stale entries from the internal map.
     * No-op when the map is small; cheap to call on every loop() iteration.
     */
    void prune();

private:
    std::map<std::string, unsigned long> _lastSeen;
};
