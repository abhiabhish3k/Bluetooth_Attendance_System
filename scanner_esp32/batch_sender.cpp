/**
 * batch_sender.cpp — BatchSender implementation.
 *
 * Design decisions:
 *  - Offline buffer stores fully serialised JSON strings so we don't need to
 *    re-serialise on retry.
 *  - Exponential backoff uses blocking delay() because the BLE scan callback
 *    runs on the same FreeRTOS task; a short delay is acceptable here.
 *  - The offline buffer is a simple ring-end-array (FIFO semantics, no wrap):
 *    entries are appended at _offlineCount and the whole slice is shifted after
 *    a partial drain.  For OFFLINE_BUFFER_MAX = 100 this is cheap.
 */

#include "batch_sender.h"

BatchSender batchSender;

// ── Constructor ──────────────────────────────────────────────────────────────

BatchSender::BatchSender()
    : _batchDoc(BATCH_DOC_SIZE), _batchCount(0),
      _lastBatchMs(0), _offlineCount(0)
{
    _resetBatch();
}

// ── Public interface ─────────────────────────────────────────────────────────

void BatchSender::enqueue(const String& mac, int rssi, const String& beaconId,
                          int64_t timestampSec, const String& name)
{
    JsonObject ev = _batchArray.createNestedObject();
    ev["address"]    = mac.c_str();
    ev["rssi"]       = rssi;
    ev["timestamp"]  = (long long)timestampSec;
    ev["beacon_id"]  = beaconId.c_str();
    ev["scanner_id"] = SCANNER_ID;
    if (name.length() > 0) ev["name"] = name.c_str();
    _batchCount++;

    if (_batchCount >= MAX_BATCH_SIZE) {
        flush();
    }
}

void BatchSender::tick() {
    if (millis() - _lastBatchMs >= (unsigned long)BATCH_INTERVAL_MS) {
        flush();
    }
}

void BatchSender::flush() {
    if (_batchCount == 0) {
        _lastBatchMs = millis();
        return;
    }

    // Serialise the batch as {"events": [...]}
    DynamicJsonDocument envelope(BATCH_DOC_SIZE + 64);
    envelope["events"] = _batchArray;
    String payload;
    serializeJson(envelope, payload);

    if (WiFi.status() != WL_CONNECTED) {
        // Buffer for when Wi-Fi comes back
        if (_offlineCount < OFFLINE_BUFFER_MAX) {
            _offlineBuffer[_offlineCount++] = payload;
            LOG_WARN("Wi-Fi down – buffered batch of %d event(s) (offline=%d)",
                     _batchCount, _offlineCount);
        } else {
            LOG_WARN("Wi-Fi down & offline buffer full – dropping %d event(s)",
                     _batchCount);
        }
        _resetBatch();
        return;
    }

    // Wi-Fi is up: drain any offline backlog first, then send current payload
    _drainOfflineBuffer();
    _doSend(payload, _batchCount);
    _resetBatch();
}

// ── Private helpers ──────────────────────────────────────────────────────────

void BatchSender::_resetBatch() {
    _batchDoc.clear();
    _batchArray  = _batchDoc.to<JsonArray>();
    _batchCount  = 0;
    _lastBatchMs = millis();
}

void BatchSender::_drainOfflineBuffer() {
    if (_offlineCount == 0) return;
    LOG_INFO("Draining offline buffer (%d payload(s)) ...", _offlineCount);

    int sent = 0;
    while (sent < _offlineCount && WiFi.status() == WL_CONNECTED) {
        if (_postWithRetry(_offlineBuffer[sent])) {
            sent++;
        } else {
            break;  // stop draining; will retry on next tick
        }
    }

    if (sent > 0) {
        // Shift remaining entries to the front of the array
        for (int i = 0; i < _offlineCount - sent; i++) {
            _offlineBuffer[i] = _offlineBuffer[i + sent];
        }
        _offlineCount -= sent;
        LOG_INFO("Offline buffer: sent %d, remaining %d", sent, _offlineCount);
    }
}

void BatchSender::_doSend(const String& payload, int eventCount) {
    if (_postWithRetry(payload)) {
        LOG_INFO("Sent %d event(s) to backend (offline=%d)",
                 eventCount, _offlineCount);
    } else {
        // All retries exhausted – buffer for later
        if (_offlineCount < OFFLINE_BUFFER_MAX) {
            _offlineBuffer[_offlineCount++] = payload;
            LOG_WARN("POST failed – buffered for retry (offline=%d)", _offlineCount);
        } else {
            LOG_WARN("POST failed & offline buffer full – %d event(s) dropped",
                     eventCount);
        }
    }
}

bool BatchSender::_postWithRetry(const String& payload) {
    for (int attempt = 1; attempt <= HTTP_RETRY_COUNT; attempt++) {
        HTTPClient http;
        http.begin(BACKEND_URL);
        http.addHeader("Content-Type", "application/json");
        if (strlen(AUTH_TOKEN) > 0) {
            http.addHeader("Authorization", String("Bearer ") + AUTH_TOKEN);
        }
        http.setTimeout(HTTP_TIMEOUT_MS);

        int code = http.POST(payload);
        http.end();

        if (code >= 200 && code < 300) {
            return true;
        }

        if (code > 0) {
            LOG_WARN("HTTP %d on attempt %d/%d", code, attempt, HTTP_RETRY_COUNT);
        } else {
            LOG_WARN("HTTP error '%s' on attempt %d/%d",
                     HTTPClient::errorToString(code).c_str(),
                     attempt, HTTP_RETRY_COUNT);
        }

        if (attempt < HTTP_RETRY_COUNT) {
            // Exponential backoff: 500 ms, 1000 ms, 2000 ms, …
            // Cap the shift to prevent overflow if HTTP_RETRY_COUNT is raised.
            int shift = (attempt - 1 < 6) ? (attempt - 1) : 6;
            unsigned long backoff = (unsigned long)HTTP_RETRY_BASE_MS * (1UL << shift);
            LOG_DEBUG("Retry backoff: %lu ms", backoff);
            delay(backoff);
        }
    }
    return false;
}
