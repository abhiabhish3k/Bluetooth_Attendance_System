/**
 * dedup.cpp — Deduplicator implementation.
 */

#include "dedup.h"
#include <Arduino.h>

bool Deduplicator::accept(const std::string& mac) {
    unsigned long now = millis();
    auto it = _lastSeen.find(mac);
    if (it != _lastSeen.end() &&
        (now - it->second) < (unsigned long)DEDUP_WINDOW_MS) {
        return false;  // too soon – duplicate
    }
    _lastSeen[mac] = now;
    return true;
}

void Deduplicator::prune() {
    // Only scan the map when it is large to avoid wasting CPU cycles.
    if (_lastSeen.size() <= 500) return;

    unsigned long now = millis();
    for (auto it = _lastSeen.begin(); it != _lastSeen.end(); ) {
        // Evict entries that have not been seen for 4× the dedup window.
        if (now - it->second > (unsigned long)DEDUP_WINDOW_MS * 4) {
            it = _lastSeen.erase(it);
        } else {
            ++it;
        }
    }
}
