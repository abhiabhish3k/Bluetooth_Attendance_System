/**
 * Deduplicator – suppress repeated BLE events within a time window.
 */

#include "deduplicator.h"
#include <algorithm>
#include <cctype>

namespace ble {

// ---------------------------------------------------------------------------
// Constructor
// ---------------------------------------------------------------------------
Deduplicator::Deduplicator(int windowSeconds)
    : m_window(std::chrono::seconds(windowSeconds))
{}

// ---------------------------------------------------------------------------
// shouldProcess
// ---------------------------------------------------------------------------
bool Deduplicator::shouldProcess(const std::string& mac) {
    // Normalise MAC to uppercase for consistent keying
    std::string key = mac;
    std::transform(key.begin(), key.end(), key.begin(),
                   [](unsigned char c) { return static_cast<char>(std::toupper(c)); });

    std::lock_guard<std::mutex> lock(m_mutex);
    auto now = Clock::now();
    auto it  = m_lastSeen.find(key);

    if (it != m_lastSeen.end()) {
        if (now - it->second < m_window) {
            return false; // duplicate – suppress
        }
        it->second = now; // window expired – update timestamp
    } else {
        m_lastSeen.emplace(key, now);
    }
    return true;
}

// ---------------------------------------------------------------------------
// purgeExpired
// ---------------------------------------------------------------------------
void Deduplicator::purgeExpired() {
    std::lock_guard<std::mutex> lock(m_mutex);
    auto now = Clock::now();
    for (auto it = m_lastSeen.begin(); it != m_lastSeen.end();) {
        if (now - it->second >= m_window) {
            it = m_lastSeen.erase(it);
        } else {
            ++it;
        }
    }
}

// ---------------------------------------------------------------------------
// clear
// ---------------------------------------------------------------------------
void Deduplicator::clear() {
    std::lock_guard<std::mutex> lock(m_mutex);
    m_lastSeen.clear();
}

// ---------------------------------------------------------------------------
// windowSeconds
// ---------------------------------------------------------------------------
int Deduplicator::windowSeconds() const {
    return static_cast<int>(m_window.count());
}

} // namespace ble
