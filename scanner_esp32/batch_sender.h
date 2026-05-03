/**
 * batch_sender.h — HTTP batch sender with retry, exponential backoff, and
 *                  offline buffering.
 *
 * Collects scan events into a JSON batch and POSTs them to the backend's
 * /api/events/batch endpoint.  When Wi-Fi is unavailable, payloads are
 * kept in a ring buffer and re-sent once the connection is restored.
 *
 * The global singleton `batchSender` is declared at the bottom of this
 * header so it can be shared between scanner_esp32.ino and any other
 * translation unit.
 *
 * Call batchSender.tick() on every loop() iteration.
 */

#pragma once

#include <Arduino.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include "config.h"
#include "logger.h"

// Size of the per-batch JSON document (bytes).
// 8 192 B fits roughly 80 events at ~100 B each.
#define BATCH_DOC_SIZE 8192

class BatchSender {
public:
    BatchSender();

    /**
     * Append one scan event to the current batch.
     * If the batch reaches MAX_BATCH_SIZE, it is flushed immediately.
     *
     * @param mac          BLE MAC address string (e.g. "aa:bb:cc:dd:ee:ff")
     * @param rssi         Signal strength in dBm
     * @param beaconId     Parsed beacon_id string (e.g. "1:1001")
     * @param timestampSec Unix seconds from NTP (0 if NTP not yet synced)
     * @param name         Optional BLE advertising name (may be empty)
     */
    void enqueue(const String& mac, int rssi, const String& beaconId,
                 int64_t timestampSec, const String& name = "");

    /**
     * Called from loop().  Flushes the batch if BATCH_INTERVAL_MS has elapsed
     * or the batch is full.
     */
    void tick();

    /**
     * Force-flush the current batch regardless of the interval timer.
     * Safe to call even when the batch is empty.
     */
    void flush();

    /** Number of events currently waiting in the active batch. */
    int queuedCount() const { return _batchCount; }

    /** Number of payloads currently in the offline buffer. */
    int bufferedCount() const { return _offlineCount; }

private:
    // Active batch
    DynamicJsonDocument _batchDoc;
    JsonArray           _batchArray;
    int                 _batchCount;
    unsigned long       _lastBatchMs;

    // Offline buffer – stores serialised JSON strings while Wi-Fi is down.
    // Each entry is one complete {"events":[...]} payload string.
    String _offlineBuffer[OFFLINE_BUFFER_MAX];
    int    _offlineCount;

    // Helpers
    void _resetBatch();
    void _doSend(const String& payload, int eventCount);
    bool _postWithRetry(const String& payload);
    void _drainOfflineBuffer();
};

// Module-level singleton – include this header to access it.
extern BatchSender batchSender;
