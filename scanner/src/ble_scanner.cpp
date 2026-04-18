/**
 * BLE Scanner – BlueZ D-Bus Integration
 *
 * Monitors BlueZ ObjectManager and Device1 property signals to detect
 * nearby BLE devices and deliver DeviceEvents to the registered callback.
 *
 * Beacon parsing: when a device advertises ManufacturerData, the parser
 * attempts to extract a student unique_id.  Two formats are supported:
 *   - Apple iBeacon (company 0x004C): "major:minor" string
 *   - Custom BLE-Attendance (company 0xFFFF): embedded UTF-8 unique_id
 */

#include "ble_scanner.h"
#include "device_parser.h"

#include <iostream>
#include <cstring>
#include <ctime>
#include <stdexcept>
#include <vector>

namespace ble {

// ---------------------------------------------------------------------------
// D-Bus constants
// ---------------------------------------------------------------------------
static constexpr const char* BLUEZ_SERVICE       = "org.bluez";
static constexpr const char* BLUEZ_OBJMANAGER_IF = "org.freedesktop.DBus.ObjectManager";
static constexpr const char* BLUEZ_ADAPTER_IF    = "org.bluez.Adapter1";
static constexpr const char* BLUEZ_DEVICE_IF     = "org.bluez.Device1";
static constexpr const char* DBUS_PROPS_IF       = "org.freedesktop.DBus.Properties";
static constexpr const char* OBJMANAGER_PATH     = "/";

static constexpr int DBUS_TIMEOUT_MS = 5000;

// ---------------------------------------------------------------------------
// Constructor / Destructor
// ---------------------------------------------------------------------------
BleScanner::BleScanner(const std::string& adapter)
    : m_adapter(adapter)
    , m_adapterPath("/org/bluez/" + adapter)
    , m_conn(nullptr)
    , m_running(false)
{}

BleScanner::~BleScanner() {
    stop();
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------
void BleScanner::setCallback(DeviceCallback cb) {
    m_callback = std::move(cb);
}

bool BleScanner::start() {
    if (m_running.load()) return true;

    if (!initDbus()) return false;
    addMatchRules();

    if (!startDiscovery()) {
        removeMatchRules();
        if (m_conn) {
            dbus_connection_unref(m_conn);
            m_conn = nullptr;
        }
        return false;
    }

    m_running.store(true);
    return true;
}

void BleScanner::stop() {
    if (!m_running.exchange(false)) return;
    stopDiscovery();
    removeMatchRules();
    if (m_conn) {
        dbus_connection_unref(m_conn);
        m_conn = nullptr;
    }
}

void BleScanner::run() {
    while (m_running.load() && m_conn) {
        dbus_connection_read_write_dispatch(m_conn, 100 /* ms */);
    }
}

bool BleScanner::isRunning() const {
    return m_running.load();
}

// ---------------------------------------------------------------------------
// D-Bus initialisation
// ---------------------------------------------------------------------------
bool BleScanner::initDbus() {
    DBusError err;
    dbus_error_init(&err);

    m_conn = dbus_bus_get(DBUS_BUS_SYSTEM, &err);
    if (dbus_error_is_set(&err)) {
        std::cerr << "[BleScanner] D-Bus connection error: " << err.message << "\n";
        dbus_error_free(&err);
        return false;
    }
    if (!m_conn) {
        std::cerr << "[BleScanner] Failed to connect to D-Bus system bus\n";
        return false;
    }

    // Install our message filter
    if (!dbus_connection_add_filter(m_conn, &BleScanner::messageFilter, this, nullptr)) {
        std::cerr << "[BleScanner] Failed to add D-Bus message filter\n";
        dbus_connection_unref(m_conn);
        m_conn = nullptr;
        return false;
    }

    return true;
}

// ---------------------------------------------------------------------------
// Add / remove D-Bus match rules for BlueZ signals
// ---------------------------------------------------------------------------
void BleScanner::addMatchRules() {
    DBusError err;
    dbus_error_init(&err);

    // ObjectManager::InterfacesAdded – fires when a new device is discovered
    std::string rule1 = "type='signal',sender='" + std::string(BLUEZ_SERVICE) +
                        "',interface='" + std::string(BLUEZ_OBJMANAGER_IF) +
                        "',member='InterfacesAdded'";
    dbus_bus_add_match(m_conn, rule1.c_str(), &err);
    if (dbus_error_is_set(&err)) {
        std::cerr << "[BleScanner] Match rule error: " << err.message << "\n";
        dbus_error_free(&err);
    }

    // Properties::PropertiesChanged on Device1 – fires when RSSI updates
    std::string rule2 = "type='signal',sender='" + std::string(BLUEZ_SERVICE) +
                        "',interface='" + std::string(DBUS_PROPS_IF) +
                        "',member='PropertiesChanged',arg0='" +
                        std::string(BLUEZ_DEVICE_IF) + "'";
    dbus_bus_add_match(m_conn, rule2.c_str(), &err);
    if (dbus_error_is_set(&err)) {
        std::cerr << "[BleScanner] Match rule error: " << err.message << "\n";
        dbus_error_free(&err);
    }

    dbus_connection_flush(m_conn);
}

void BleScanner::removeMatchRules() {
    if (!m_conn) return;
    DBusError err;
    dbus_error_init(&err);

    std::string rule1 = "type='signal',sender='" + std::string(BLUEZ_SERVICE) +
                        "',interface='" + std::string(BLUEZ_OBJMANAGER_IF) +
                        "',member='InterfacesAdded'";
    dbus_bus_remove_match(m_conn, rule1.c_str(), &err);
    if (dbus_error_is_set(&err)) dbus_error_free(&err);

    std::string rule2 = "type='signal',sender='" + std::string(BLUEZ_SERVICE) +
                        "',interface='" + std::string(DBUS_PROPS_IF) +
                        "',member='PropertiesChanged',arg0='" +
                        std::string(BLUEZ_DEVICE_IF) + "'";
    dbus_bus_remove_match(m_conn, rule2.c_str(), &err);
    if (dbus_error_is_set(&err)) dbus_error_free(&err);

    dbus_connection_flush(m_conn);
}

// ---------------------------------------------------------------------------
// Start / Stop BlueZ discovery
// ---------------------------------------------------------------------------
bool BleScanner::startDiscovery() {
    DBusMessage* msg = dbus_message_new_method_call(
        BLUEZ_SERVICE,
        m_adapterPath.c_str(),
        BLUEZ_ADAPTER_IF,
        "StartDiscovery"
    );
    if (!msg) {
        std::cerr << "[BleScanner] Failed to create StartDiscovery message\n";
        return false;
    }

    DBusError err;
    dbus_error_init(&err);
    DBusMessage* reply = dbus_connection_send_with_reply_and_block(
        m_conn, msg, DBUS_TIMEOUT_MS, &err);
    dbus_message_unref(msg);

    if (dbus_error_is_set(&err)) {
        std::cerr << "[BleScanner] StartDiscovery error: " << err.message << "\n";
        dbus_error_free(&err);
        return false;
    }
    if (reply) dbus_message_unref(reply);

    std::cout << "[BleScanner] BLE discovery started on " << m_adapter << "\n";
    return true;
}

void BleScanner::stopDiscovery() {
    if (!m_conn) return;

    DBusMessage* msg = dbus_message_new_method_call(
        BLUEZ_SERVICE,
        m_adapterPath.c_str(),
        BLUEZ_ADAPTER_IF,
        "StopDiscovery"
    );
    if (!msg) return;

    DBusError err;
    dbus_error_init(&err);
    DBusMessage* reply = dbus_connection_send_with_reply_and_block(
        m_conn, msg, DBUS_TIMEOUT_MS, &err);
    dbus_message_unref(msg);
    if (dbus_error_is_set(&err)) dbus_error_free(&err);
    if (reply) dbus_message_unref(reply);

    std::cout << "[BleScanner] BLE discovery stopped\n";
}

// ---------------------------------------------------------------------------
// D-Bus message filter callback
// ---------------------------------------------------------------------------
DBusHandlerResult BleScanner::messageFilter(DBusConnection* /*conn*/,
                                              DBusMessage* msg,
                                              void* userData) {
    auto* self = static_cast<BleScanner*>(userData);
    self->processMessage(msg);
    return DBUS_HANDLER_RESULT_NOT_YET_HANDLED;
}

void BleScanner::processMessage(DBusMessage* msg) {
    if (!msg || !m_callback) return;

    const char* iface  = dbus_message_get_interface(msg);
    const char* member = dbus_message_get_member(msg);
    if (!iface || !member) return;

    if (std::string(iface) == BLUEZ_OBJMANAGER_IF &&
        std::string(member) == "InterfacesAdded") {
        handleInterfacesAdded(msg);
    } else if (std::string(iface) == DBUS_PROPS_IF &&
               std::string(member) == "PropertiesChanged") {
        handlePropertiesChanged(msg);
    }
}

// ---------------------------------------------------------------------------
// Parse InterfacesAdded signal
//
// Signature: oa{sa{sv}}
//   OBJECT_PATH  –  e.g. /org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF
//   dict<string, dict<string, variant>>  –  interface name → properties
// ---------------------------------------------------------------------------
void BleScanner::handleInterfacesAdded(DBusMessage* msg) {
    DBusMessageIter args;
    if (!dbus_message_iter_init(msg, &args)) return;
    if (dbus_message_iter_get_arg_type(&args) != DBUS_TYPE_OBJECT_PATH) return;

    const char* objPath = nullptr;
    dbus_message_iter_get_basic(&args, &objPath);
    if (!objPath) return;

    dbus_message_iter_next(&args);
    if (dbus_message_iter_get_arg_type(&args) != DBUS_TYPE_ARRAY) return;

    DBusMessageIter ifaceDict;
    dbus_message_iter_recurse(&args, &ifaceDict);

    while (dbus_message_iter_get_arg_type(&ifaceDict) == DBUS_TYPE_DICT_ENTRY) {
        DBusMessageIter entry;
        dbus_message_iter_recurse(&ifaceDict, &entry);

        const char* ifaceName = nullptr;
        dbus_message_iter_get_basic(&entry, &ifaceName);

        if (ifaceName && std::string(ifaceName) == BLUEZ_DEVICE_IF) {
            dbus_message_iter_next(&entry);
            parseDevice1Properties(std::string(objPath), &entry);
        }
        dbus_message_iter_next(&ifaceDict);
    }
}

// ---------------------------------------------------------------------------
// Parse PropertiesChanged signal
//
// Signature: sa{sv}as
//   interface name, changed properties dict, invalidated properties list
// ---------------------------------------------------------------------------
void BleScanner::handlePropertiesChanged(DBusMessage* msg) {
    const char* objPath = dbus_message_get_path(msg);
    if (!objPath) return;

    DBusMessageIter args;
    if (!dbus_message_iter_init(msg, &args)) return;

    // First argument is the interface name
    const char* ifaceName = nullptr;
    dbus_message_iter_get_basic(&args, &ifaceName);
    if (!ifaceName || std::string(ifaceName) != BLUEZ_DEVICE_IF) return;

    dbus_message_iter_next(&args);
    if (dbus_message_iter_get_arg_type(&args) != DBUS_TYPE_ARRAY) return;

    parseDevice1Properties(std::string(objPath), &args);
}

// ---------------------------------------------------------------------------
// Extract address, name, RSSI, and ManufacturerData from a Device1 property dict
// ---------------------------------------------------------------------------
void BleScanner::parseDevice1Properties(const std::string& objPath,
                                         DBusMessageIter* iter) {
    std::string address;
    std::string name;
    int rssi = 0;
    bool hasRssi = false;
    std::string beacon_id;

    // The iterator should point at an ARRAY of DICT_ENTRY {string, variant}
    DBusMessageIter propArray;
    dbus_message_iter_recurse(iter, &propArray);

    while (dbus_message_iter_get_arg_type(&propArray) == DBUS_TYPE_DICT_ENTRY) {
        DBusMessageIter propEntry;
        dbus_message_iter_recurse(&propArray, &propEntry);

        const char* propName = nullptr;
        dbus_message_iter_get_basic(&propEntry, &propName);
        dbus_message_iter_next(&propEntry);

        if (!propName) {
            dbus_message_iter_next(&propArray);
            continue;
        }

        // Value is wrapped in a variant
        DBusMessageIter variant;
        dbus_message_iter_recurse(&propEntry, &variant);
        int vType = dbus_message_iter_get_arg_type(&variant);

        if (std::string(propName) == "Address" && vType == DBUS_TYPE_STRING) {
            const char* addr = nullptr;
            dbus_message_iter_get_basic(&variant, &addr);
            if (addr) address = addr;

        } else if (std::string(propName) == "Name" && vType == DBUS_TYPE_STRING) {
            const char* n = nullptr;
            dbus_message_iter_get_basic(&variant, &n);
            if (n) name = n;

        } else if (std::string(propName) == "Alias" && name.empty() &&
                   vType == DBUS_TYPE_STRING) {
            const char* a = nullptr;
            dbus_message_iter_get_basic(&variant, &a);
            if (a) name = a;

        } else if (std::string(propName) == "RSSI" && vType == DBUS_TYPE_INT16) {
            dbus_int16_t r = 0;
            dbus_message_iter_get_basic(&variant, &r);
            rssi    = static_cast<int>(r);
            hasRssi = true;

        } else if (std::string(propName) == "ManufacturerData" &&
                   vType == DBUS_TYPE_ARRAY) {
            // ManufacturerData is a{qv} – dict<uint16, variant<array<byte>>>
            beacon_id = parseManufacturerData(&variant);
        }

        dbus_message_iter_next(&propArray);
    }

    // If address was not in the property dict, derive from path
    if (address.empty()) {
        address = DeviceParser::extractMacFromPath(objPath);
    }

    if (!hasRssi || address.empty()) return;

    auto evOpt = DeviceParser::buildEvent(address, name, rssi,
                                           static_cast<int64_t>(std::time(nullptr)),
                                           beacon_id);
    if (evOpt && m_callback) {
        m_callback(*evOpt);
    }
}

// ---------------------------------------------------------------------------
// parseManufacturerData
//
// Iterates over the ManufacturerData dictionary (a{qv}) and for each entry
// passes the company ID and payload bytes to DeviceParser::parseBeaconId.
// Returns the first recognised beacon identifier, or empty string.
// ---------------------------------------------------------------------------
std::string BleScanner::parseManufacturerData(DBusMessageIter* iter) {
    // iter currently points at the variant wrapping the a{qv} array
    // Recurse into the variant to get the array
    DBusMessageIter arrayIter;
    dbus_message_iter_recurse(iter, &arrayIter);

    while (dbus_message_iter_get_arg_type(&arrayIter) == DBUS_TYPE_DICT_ENTRY) {
        DBusMessageIter dictEntry;
        dbus_message_iter_recurse(&arrayIter, &dictEntry);

        // Key: uint16 company ID
        if (dbus_message_iter_get_arg_type(&dictEntry) != DBUS_TYPE_UINT16) {
            dbus_message_iter_next(&arrayIter);
            continue;
        }
        dbus_uint16_t companyId = 0;
        dbus_message_iter_get_basic(&dictEntry, &companyId);
        dbus_message_iter_next(&dictEntry);

        // Value: variant wrapping array of bytes
        if (dbus_message_iter_get_arg_type(&dictEntry) != DBUS_TYPE_VARIANT) {
            dbus_message_iter_next(&arrayIter);
            continue;
        }
        DBusMessageIter valueVariant;
        dbus_message_iter_recurse(&dictEntry, &valueVariant);

        if (dbus_message_iter_get_arg_type(&valueVariant) != DBUS_TYPE_ARRAY) {
            dbus_message_iter_next(&arrayIter);
            continue;
        }
        DBusMessageIter byteArray;
        dbus_message_iter_recurse(&valueVariant, &byteArray);

        std::vector<uint8_t> payload;
        while (dbus_message_iter_get_arg_type(&byteArray) == DBUS_TYPE_BYTE) {
            uint8_t byte = 0;
            dbus_message_iter_get_basic(&byteArray, &byte);
            payload.push_back(byte);
            dbus_message_iter_next(&byteArray);
        }

        std::string beaconId = DeviceParser::parseBeaconId(
            static_cast<uint16_t>(companyId), payload);
        if (!beaconId.empty()) {
            return beaconId;
        }

        dbus_message_iter_next(&arrayIter);
    }

    return {};
}

} // namespace ble
