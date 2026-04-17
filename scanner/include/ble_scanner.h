#pragma once

#include <string>
#include <functional>
#include <atomic>
#include <memory>
#include <dbus/dbus.h>

namespace ble {

/**
 * Represents a detected BLE device event.
 */
struct DeviceEvent {
    std::string address;    ///< MAC address (e.g. "AA:BB:CC:DD:EE:FF")
    std::string name;       ///< Advertising name (may be empty)
    int         rssi;       ///< Signal strength in dBm
    int64_t     timestamp;  ///< Unix timestamp (seconds)
};

/**
 * Callback invoked when a BLE device event is received.
 */
using DeviceCallback = std::function<void(const DeviceEvent&)>;

/**
 * BLE scanner that interfaces with BlueZ via D-Bus.
 *
 * Listens for InterfacesAdded signals from the BlueZ ObjectManager and
 * PropertiesChanged signals from org.bluez.Device1 to report nearby
 * BLE devices with their RSSI values.
 */
class BleScanner {
public:
    explicit BleScanner(const std::string& adapter = "hci0");
    ~BleScanner();

    // Non-copyable, movable
    BleScanner(const BleScanner&) = delete;
    BleScanner& operator=(const BleScanner&) = delete;
    BleScanner(BleScanner&&) = default;
    BleScanner& operator=(BleScanner&&) = default;

    /**
     * Register a callback to receive device events.
     * Must be called before start().
     */
    void setCallback(DeviceCallback cb);

    /**
     * Connect to D-Bus system bus and start BLE discovery.
     * @return true on success, false on failure.
     */
    bool start();

    /**
     * Stop BLE discovery and clean up D-Bus resources.
     */
    void stop();

    /**
     * Run the D-Bus event loop until stop() is called.
     * This call blocks until scanning is stopped.
     */
    void run();

    /**
     * Returns true if the scanner is currently running.
     */
    bool isRunning() const;

private:
    bool initDbus();
    bool startDiscovery();
    void stopDiscovery();
    void addMatchRules();
    void removeMatchRules();
    void processMessage(DBusMessage* msg);
    void handleInterfacesAdded(DBusMessage* msg);
    void handlePropertiesChanged(DBusMessage* msg);
    void parseDevice1Properties(const std::string& objPath, DBusMessageIter* iter);

    static DBusHandlerResult messageFilter(DBusConnection* conn,
                                           DBusMessage* msg,
                                           void* userData);

    std::string      m_adapter;       ///< Bluetooth adapter name (e.g. "hci0")
    std::string      m_adapterPath;   ///< D-Bus path ("/org/bluez/hci0")
    DBusConnection*  m_conn;          ///< D-Bus connection handle
    DeviceCallback   m_callback;      ///< User-supplied event handler
    std::atomic<bool> m_running;      ///< Scan loop control flag
};

} // namespace ble
