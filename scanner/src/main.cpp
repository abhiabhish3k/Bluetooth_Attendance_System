/**
 * BLE Attendance Scanner – Entry Point
 *
 * Connects to BlueZ via D-Bus, continuously scans for nearby BLE devices,
 * applies a deduplication window, and emits JSON events to stdout.
 *
 * Usage:  sudo ./ble_scanner [config.json]
 */

#include <iostream>
#include <fstream>
#include <csignal>
#include <atomic>
#include <thread>
#include <chrono>
#include <string>

#include "ble_scanner.h"
#include "device_parser.h"
#include "deduplicator.h"
#include "logger.h"

// ---------------------------------------------------------------------------
// Global state for signal handling
// ---------------------------------------------------------------------------
static std::atomic<bool> g_shutdown{false};
static ble::BleScanner*  g_scanner = nullptr;

static void signalHandler(int signum) {
    std::cerr << "\n[signal] Caught signal " << signum << " – shutting down...\n";
    g_shutdown.store(true);
    if (g_scanner) {
        g_scanner->stop();
    }
}

// ---------------------------------------------------------------------------
// Simple JSON config loader (no external JSON library required)
// ---------------------------------------------------------------------------
struct Config {
    std::string adapter        = "hci0";
    int         rssiThreshold  = -80;      // dBm – ignore devices weaker than this
    int         dedupWindow    = 5;        // seconds
    std::string logFile        = "scanner.log";
    std::string logLevel       = "INFO";
};

static Config loadConfig(const std::string& path) {
    Config cfg;
    std::ifstream f(path);
    if (!f.is_open()) {
        std::cerr << "[config] Could not open " << path << " – using defaults\n";
        return cfg;
    }

    // Minimal hand-rolled JSON field extractor (avoids external dependency)
    auto extract = [](const std::string& src, const std::string& key,
                      std::string& out) -> bool {
        std::string search = "\"" + key + "\"";
        auto pos = src.find(search);
        if (pos == std::string::npos) return false;
        pos = src.find(':', pos);
        if (pos == std::string::npos) return false;
        ++pos;
        while (pos < src.size() && (src[pos] == ' ' || src[pos] == '\t')) ++pos;
        if (pos >= src.size()) return false;
        if (src[pos] == '"') {
            ++pos;
            auto end = src.find('"', pos);
            if (end == std::string::npos) return false;
            out = src.substr(pos, end - pos);
        } else {
            auto end = pos;
            while (end < src.size() && src[end] != ',' &&
                   src[end] != '}' && src[end] != '\n') ++end;
            out = src.substr(pos, end - pos);
        }
        return true;
    };

    std::string content((std::istreambuf_iterator<char>(f)),
                         std::istreambuf_iterator<char>());

    std::string val;
    if (extract(content, "adapter",       val)) cfg.adapter       = val;
    if (extract(content, "rssi_threshold",val)) cfg.rssiThreshold = std::stoi(val);
    if (extract(content, "dedup_window",  val)) cfg.dedupWindow   = std::stoi(val);
    if (extract(content, "log_file",      val)) cfg.logFile       = val;
    if (extract(content, "log_level",     val)) cfg.logLevel      = val;

    return cfg;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
int main(int argc, char* argv[]) {
    const std::string configPath = (argc > 1) ? argv[1] : "config.json";
    Config cfg = loadConfig(configPath);

    // Translate log level string
    ble::LogLevel logLevel = ble::LogLevel::INFO;
    if (cfg.logLevel == "DEBUG") logLevel = ble::LogLevel::DEBUG;
    else if (cfg.logLevel == "WARN")  logLevel = ble::LogLevel::WARN;
    else if (cfg.logLevel == "ERROR") logLevel = ble::LogLevel::ERROR;

    // Set up logger
    ble::Logger logger(cfg.logFile, logLevel);
    logger.info("BLE Attendance Scanner starting");
    logger.info("Adapter: " + cfg.adapter);
    logger.info("RSSI threshold: " + std::to_string(cfg.rssiThreshold) + " dBm");
    logger.info("Dedup window: " + std::to_string(cfg.dedupWindow) + "s");

    // Set up signal handlers
    std::signal(SIGINT,  signalHandler);
    std::signal(SIGTERM, signalHandler);

    // Set up deduplicator
    ble::Deduplicator dedup(cfg.dedupWindow);

    // Set up scanner
    ble::BleScanner scanner(cfg.adapter);
    g_scanner = &scanner;

    // Register device event callback
    scanner.setCallback([&](const ble::DeviceEvent& ev) {
        // Apply RSSI threshold filter
        if (ev.rssi < cfg.rssiThreshold) {
            logger.debug("Filtered (RSSI " + std::to_string(ev.rssi) +
                         " < " + std::to_string(cfg.rssiThreshold) + "): " +
                         ev.address);
            return;
        }
        // Deduplicate
        if (!dedup.shouldProcess(ev.address)) {
            logger.debug("Deduplicated: " + ev.address);
            return;
        }
        // Emit JSON event
        logger.logEvent(ev);
    });

    // Start scanning
    if (!scanner.start()) {
        logger.error("Failed to start BLE scanner – check Bluetooth adapter and D-Bus permissions");
        return 1;
    }

    logger.info("Scanner running – press Ctrl+C to stop");

    // Periodic purge of deduplicator to prevent memory growth
    std::thread purgeThread([&]() {
        while (!g_shutdown.load()) {
            std::this_thread::sleep_for(std::chrono::seconds(60));
            dedup.purgeExpired();
            logger.debug("Deduplicator purged");
        }
    });

    // Run the D-Bus event loop (blocks until stop() is called)
    scanner.run();

    g_shutdown.store(true);
    if (purgeThread.joinable()) {
        purgeThread.join();
    }

    logger.info("BLE Attendance Scanner stopped");
    return 0;
}
