import React, { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const api = {
  getHealth: () => axios.get(`${API_BASE}/health`),
  getSessions: () => axios.get(`${API_BASE}/api/sessions`),
  getActiveSession: () => axios.get(`${API_BASE}/api/sessions/active`),
  getSessionReport: (id) => axios.get(`${API_BASE}/api/attendance/report/${id}`),
  createSession: (data) => axios.post(`${API_BASE}/api/sessions`, data),
  updateSession: (id, data) => axios.patch(`${API_BASE}/api/sessions/${id}`, data),
  activateSession: (id) => axios.post(`${API_BASE}/api/sessions/${id}/activate`),
  deleteSession: (id) => axios.delete(`${API_BASE}/api/sessions/${id}`),

  listStudents: (search) =>
    axios.get(`${API_BASE}/api/students`, { params: search ? { search } : {} }),
  createStudent: (data) => axios.post(`${API_BASE}/api/students`, data),
  updateStudent: (id, data) => axios.patch(`${API_BASE}/api/students/${id}`, data),
  deleteStudent: (id) => axios.delete(`${API_BASE}/api/students/${id}`),
  registerBeacon: (id, beacon_id) =>
    axios.post(`${API_BASE}/api/students/${id}/beacon/register`, { beacon_id }),
  getBeacon: (id) => axios.get(`${API_BASE}/api/students/${id}/beacon`),

  listAttendance: (params) => axios.get(`${API_BASE}/api/attendance`, { params }),
  deleteAttendance: (id) => axios.delete(`${API_BASE}/api/attendance/${id}`),

  sendScanEvent: (data) => axios.post(`${API_BASE}/api/events`, data),
  sendBatchScanEvents: (data) => axios.post(`${API_BASE}/api/events/batch`, data),
};

const section = {
  background: "#fff",
  border: "1px solid #e2e8f0",
  borderRadius: 10,
  padding: 14,
};

const input = {
  padding: "8px 10px",
  border: "1px solid #cbd5e1",
  borderRadius: 8,
};

const btn = {
  padding: "8px 12px",
  border: "1px solid #94a3b8",
  borderRadius: 8,
  background: "#f8fafc",
  cursor: "pointer",
};

function StatusPill({ status }) {
  const map = {
    present: "#16a34a",
    absent: "#dc2626",
    marked: "#16a34a",
    ignored: "#b45309",
    logged: "#0f766e",
    already_marked: "#0369a1",
  };
  return (
    <span
      style={{
        background: map[status] || "#475569",
        color: "#fff",
        padding: "2px 8px",
        borderRadius: 999,
        fontSize: 12,
        fontWeight: 600,
      }}
    >
      {status}
    </span>
  );
}

export default function App() {
  const [students, setStudents] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [activeSession, setActiveSession] = useState(null);
  const [attendance, setAttendance] = useState([]);
  const [report, setReport] = useState(null);
  const [backendHealth, setBackendHealth] = useState(null);

  const [selectedStudent, setSelectedStudent] = useState(null);
  const [selectedSessionId, setSelectedSessionId] = useState(null);

  const [studentSearch, setStudentSearch] = useState("");
  const [attendanceSessionFilter, setAttendanceSessionFilter] = useState("");
  const [attendanceStudentFilter, setAttendanceStudentFilter] = useState("");

  const [beaconLookup, setBeaconLookup] = useState(null);
  const [scanResult, setScanResult] = useState(null);
  const [flash, setFlash] = useState({ type: "info", text: "" });
  const [loading, setLoading] = useState(false);

  const [newStudent, setNewStudent] = useState({
    name: "",
    roll_number: "",
    email: "",
    mac_address: "",
    unique_id: "",
  });

  const [editStudent, setEditStudent] = useState({
    name: "",
    email: "",
    mac_address: "",
    unique_id: "",
  });

  const [newSession, setNewSession] = useState({
    class_name: "",
    start_time: "",
    end_time: "",
    threshold_rssi: -75,
  });

  const [sessionPatch, setSessionPatch] = useState({
    end_time: "",
    threshold_rssi: "",
  });

  const [beaconValue, setBeaconValue] = useState("");
  const [scanEventForm, setScanEventForm] = useState({
    address: "",
    name: "",
    rssi: -65,
    beacon_id: "",
  });
  const [batchEventsInput, setBatchEventsInput] = useState("[]");

  const flashStyle = useMemo(() => {
    if (flash.type === "error") return { background: "#fee2e2", border: "1px solid #fca5a5" };
    if (flash.type === "success") return { background: "#dcfce7", border: "1px solid #86efac" };
    return { background: "#dbeafe", border: "1px solid #93c5fd" };
  }, [flash]);

  const setMessage = (type, text) => setFlash({ type, text });
  const unixTimestampNow = () => Math.floor(Date.now() / 1000);
  const toIsoDateTime = (value, label) => {
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      throw new Error(`Invalid ${label}.`);
    }
    return parsed.toISOString();
  };

  const loadStudents = useCallback(async (search = "") => {
    const res = await api.listStudents(search.trim());
    setStudents(res.data);
  }, []);

  const loadSessions = useCallback(async () => {
    const [sessRes, activeRes] = await Promise.all([
      api.getSessions(),
      api.getActiveSession(),
    ]);
    setSessions(sessRes.data);
    setActiveSession(activeRes.data?.active ? activeRes.data.session : null);
  }, []);

  const loadHealth = useCallback(async () => {
    const res = await api.getHealth();
    setBackendHealth(res.data);
  }, []);

  const loadAttendanceList = useCallback(async () => {
    const params = {};
    if (attendanceSessionFilter) params.session_id = Number(attendanceSessionFilter);
    if (attendanceStudentFilter) params.student_id = Number(attendanceStudentFilter);
    const res = await api.listAttendance(params);
    setAttendance(res.data);
  }, [attendanceSessionFilter, attendanceStudentFilter]);

  const loadReport = useCallback(async (id) => {
    if (!id) {
      setReport(null);
      return;
    }
    const res = await api.getSessionReport(id);
    setReport(res.data);
  }, []);

  const refreshAll = useCallback(async () => {
    setLoading(true);
      try {
        await Promise.all([loadStudents(studentSearch), loadSessions(), loadAttendanceList(), loadHealth()]);
        if (selectedSessionId) await loadReport(selectedSessionId);
        setMessage("success", "Data refreshed (filters preserved).");
    } catch (e) {
      setMessage("error", e?.response?.data?.detail || "Failed to refresh data.");
    } finally {
      setLoading(false);
    }
  }, [loadAttendanceList, loadHealth, loadReport, loadSessions, loadStudents, selectedSessionId, studentSearch]);

  useEffect(() => {
    const run = async () => {
      setLoading(true);
      try {
         const [studentsRes, sessionsRes, activeRes, attendanceRes, healthRes] = await Promise.all([
           api.listStudents(),
           api.getSessions(),
           api.getActiveSession(),
           api.listAttendance({}),
           api.getHealth(),
         ]);
        setStudents(studentsRes.data);
         setSessions(sessionsRes.data);
         setActiveSession(activeRes.data?.active ? activeRes.data.session : null);
         setAttendance(attendanceRes.data);
         setBackendHealth(healthRes.data);
         setMessage("success", "Data loaded.");
      } catch (e) {
        setMessage("error", e?.response?.data?.detail || "Failed to refresh data.");
      } finally {
        setLoading(false);
      }
    };
    run();
  }, []);

  useEffect(() => {
    if (selectedStudent) {
      setEditStudent({
        name: selectedStudent.name || "",
        email: selectedStudent.email || "",
        mac_address: selectedStudent.mac_address || "",
        unique_id: selectedStudent.unique_id || "",
      });
    }
  }, [selectedStudent]);

  const handleCreateStudent = async (e) => {
    e.preventDefault();
    try {
      await api.createStudent({
        ...newStudent,
        unique_id: newStudent.unique_id.trim() || null,
      });
      setNewStudent({ name: "", roll_number: "", email: "", mac_address: "", unique_id: "" });
      await loadStudents(studentSearch);
      setMessage("success", "Student created.");
    } catch (err) {
      setMessage("error", err?.response?.data?.detail || "Could not create student.");
    }
  };

  const handleUpdateStudent = async (e) => {
    e.preventDefault();
    if (!selectedStudent) return;
    try {
      await api.updateStudent(selectedStudent.id, {
        name: editStudent.name,
        email: editStudent.email,
        mac_address: editStudent.mac_address,
        unique_id: editStudent.unique_id.trim() || null,
      });
      await loadStudents(studentSearch);
      setMessage("success", `Student #${selectedStudent.id} updated.`);
    } catch (err) {
      setMessage("error", err?.response?.data?.detail || "Could not update student.");
    }
  };

  const handleDeleteStudent = async () => {
    if (!selectedStudent) return;
    if (!window.confirm(`Delete student ${selectedStudent.name}?`)) return;
    try {
      await api.deleteStudent(selectedStudent.id);
      setSelectedStudent(null);
      setBeaconLookup(null);
      await Promise.all([loadStudents(studentSearch), loadAttendanceList()]);
      setMessage("success", "Student deleted.");
    } catch (err) {
      setMessage("error", err?.response?.data?.detail || "Could not delete student.");
    }
  };

  const handleRegisterBeacon = async () => {
    if (!selectedStudent) return;
    try {
      await api.registerBeacon(selectedStudent.id, beaconValue.trim());
      await loadStudents(studentSearch);
      setMessage("success", "Beacon registered.");
    } catch (err) {
      setMessage("error", err?.response?.data?.detail || "Could not register beacon.");
    }
  };

  const handleLookupBeacon = async () => {
    if (!selectedStudent) return;
    try {
      const res = await api.getBeacon(selectedStudent.id);
      setBeaconLookup(res.data);
      setMessage("success", "Beacon details loaded.");
    } catch (err) {
      setBeaconLookup(null);
      setMessage("error", err?.response?.data?.detail || "No beacon registered.");
    }
  };

  const handleCreateSession = async (e) => {
    e.preventDefault();
    try {
      const threshold = Number(newSession.threshold_rssi);
      if (Number.isNaN(threshold)) throw new Error("Invalid RSSI threshold.");
      const payload = {
        class_name: newSession.class_name,
        start_time: toIsoDateTime(newSession.start_time, "session start time"),
        threshold_rssi: threshold,
      };
      if (newSession.end_time) payload.end_time = toIsoDateTime(newSession.end_time, "session end time");
      await api.createSession(payload);
      setNewSession({ class_name: "", start_time: "", end_time: "", threshold_rssi: -75 });
      await loadSessions();
      setMessage("success", "Session created.");
    } catch (err) {
      setMessage("error", err?.response?.data?.detail || err?.message || "Could not create session.");
    }
  };

  const handleActivateSession = async () => {
    if (!selectedSessionId) return;
    try {
      await api.activateSession(selectedSessionId);
      await loadSessions();
      setMessage("success", `Session #${selectedSessionId} activated.`);
    } catch (err) {
      setMessage("error", err?.response?.data?.detail || "Could not activate session.");
    }
  };

  const handlePatchSession = async () => {
    if (!selectedSessionId) return;
    const payload = {};
    if (sessionPatch.end_time) payload.end_time = toIsoDateTime(sessionPatch.end_time, "session end time");
    if (sessionPatch.threshold_rssi !== "") {
      const threshold = Number(sessionPatch.threshold_rssi);
      if (Number.isNaN(threshold)) {
        setMessage("error", "Invalid RSSI threshold.");
        return;
      }
      payload.threshold_rssi = threshold;
    }
    if (!Object.keys(payload).length) {
      setMessage("error", "Provide end time or threshold to update.");
      return;
    }
    try {
      await api.updateSession(selectedSessionId, payload);
      setSessionPatch({ end_time: "", threshold_rssi: "" });
      await Promise.all([loadSessions(), loadReport(selectedSessionId)]);
      setMessage("success", `Session #${selectedSessionId} updated.`);
    } catch (err) {
      setMessage("error", err?.response?.data?.detail || "Could not update session.");
    }
  };

  const handleDeleteSession = async () => {
    if (!selectedSessionId) return;
    if (!window.confirm(`Delete session #${selectedSessionId}? This is irreversible.`)) return;
    try {
      await api.deleteSession(selectedSessionId);
      setSelectedSessionId(null);
      setReport(null);
      await Promise.all([loadSessions(), loadAttendanceList()]);
      setMessage("success", "Session deleted.");
    } catch (err) {
      setMessage("error", err?.response?.data?.detail || "Could not delete session.");
    }
  };

  const handleDeleteAttendance = async (attendanceId) => {
    if (!window.confirm(`Delete attendance record #${attendanceId}?`)) return;
    try {
      await api.deleteAttendance(attendanceId);
      await loadAttendanceList();
      if (selectedSessionId) await loadReport(selectedSessionId);
      setMessage("success", "Attendance record deleted.");
    } catch (err) {
      setMessage("error", err?.response?.data?.detail || "Could not delete attendance record.");
    }
  };

  const handleSendScanEvent = async (e) => {
    e.preventDefault();
    try {
      const rssi = Number(scanEventForm.rssi);
      if (Number.isNaN(rssi)) throw new Error("Invalid RSSI value.");
      const payload = {
        address: scanEventForm.address.trim(),
        name: scanEventForm.name.trim(),
        rssi,
        timestamp: unixTimestampNow(),
      };
      const beaconId = scanEventForm.beacon_id.trim();
      if (beaconId) payload.beacon_id = beaconId;
      const res = await api.sendScanEvent(payload);
      setScanResult(res.data);
      await loadAttendanceList();
      if (selectedSessionId) await loadReport(selectedSessionId);
      setMessage("success", "Scan event sent.");
    } catch (err) {
      setMessage("error", err?.response?.data?.detail || err?.message || "Could not send scan event.");
    }
  };

  const handleSendBatchEvents = async () => {
    try {
      const parsed = JSON.parse(batchEventsInput);
      if (!Array.isArray(parsed)) throw new Error("Batch input must be a JSON array.");
      const payload = parsed.map((event) => ({
        ...event,
        timestamp: event?.timestamp ?? unixTimestampNow(),
      }));
      const res = await api.sendBatchScanEvents(payload);
      setScanResult(res.data);
      await loadAttendanceList();
      if (selectedSessionId) await loadReport(selectedSessionId);
      setMessage("success", "Batch scan events sent.");
    } catch (err) {
      setMessage("error", err?.response?.data?.detail || err?.message || "Could not send batch scan events.");
    }
  };

  const selectedSession = sessions.find((s) => s.session_id === Number(selectedSessionId));

  return (
    <div style={{ background: "#f8fafc", minHeight: "100vh", padding: 16, fontFamily: "system-ui,sans-serif" }}>
      <div style={{ maxWidth: 1400, margin: "0 auto", display: "grid", gap: 14 }}>
        <header style={{ ...section, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <h1 style={{ margin: 0 }}>BLE Attendance Admin</h1>
            <p style={{ margin: "6px 0 0", color: "#475569" }}>
              Manage students, beacon mapping, sessions, attendance, and reports.
            </p>
          </div>
          <button aria-label="Refresh All" style={btn} onClick={refreshAll} disabled={loading}>{loading ? "Refreshing..." : "Refresh All"}</button>
        </header>

        {flash.text && (
          <div style={{ ...flashStyle, borderRadius: 8, padding: "10px 12px" }}>{flash.text}</div>
        )}

        <div style={{ ...section }}>
          <strong>Current Active Session:</strong>{" "}
          {activeSession ? `${activeSession.class_name} (#${activeSession.session_id})` : "None"}
        </div>

        <section style={section}>
          <h2 style={{ marginTop: 0 }}>Backend & Scanner Events</h2>
          <p style={{ marginTop: 0, color: "#475569" }}>
            Backend:{" "}
            {backendHealth?.status ? (
              <>
                <strong>{backendHealth.status}</strong> · {backendHealth.app} v{backendHealth.version}
              </>
            ) : (
              "Unavailable"
            )}
          </p>
          <form onSubmit={handleSendScanEvent} style={{ display: "grid", gridTemplateColumns: "repeat(5,minmax(0,1fr))", gap: 8 }}>
            <input aria-label="Scan event MAC address" style={input} placeholder="MAC XX:XX:..." value={scanEventForm.address} onChange={(e) => setScanEventForm({ ...scanEventForm, address: e.target.value })} required />
            <input aria-label="Scan event device name" style={input} placeholder="Device name" value={scanEventForm.name} onChange={(e) => setScanEventForm({ ...scanEventForm, name: e.target.value })} />
            <input aria-label="Scan event RSSI" style={input} type="number" placeholder="RSSI" value={scanEventForm.rssi} onChange={(e) => setScanEventForm({ ...scanEventForm, rssi: e.target.value })} required />
            <input aria-label="Scan event beacon ID" style={input} placeholder="beacon_id (optional)" value={scanEventForm.beacon_id} onChange={(e) => setScanEventForm({ ...scanEventForm, beacon_id: e.target.value })} />
            <button style={btn} type="submit">Send Scan Event</button>
          </form>
          <div style={{ marginTop: 8, display: "grid", gap: 8 }}>
            <textarea
              aria-label="Batch scan events JSON"
              style={{ ...input, minHeight: 96, fontFamily: "monospace" }}
              value={batchEventsInput}
              onChange={(e) => setBatchEventsInput(e.target.value)}
              placeholder='[{"address":"AA:BB:CC:DD:EE:FF","rssi":-62,"name":"phone","beacon_id":"1:1001"}]'
            />
            <div>
              <button style={btn} type="button" onClick={handleSendBatchEvents}>Send Batch Events</button>
            </div>
            {scanResult && (
              <pre style={{ margin: 0, background: "#0f172a", color: "#e2e8f0", borderRadius: 8, padding: 10, overflow: "auto" }}>
                {JSON.stringify(scanResult, null, 2)}
              </pre>
            )}
          </div>
        </section>

        <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 14 }}>
          <section style={section}>
            <h2 style={{ marginTop: 0 }}>Students</h2>
            <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
              <input aria-label="Search students by name or roll number" style={{ ...input, flex: 1 }} value={studentSearch} onChange={(e) => setStudentSearch(e.target.value)} placeholder="Search by name/roll" />
              <button aria-label="Search students" style={btn} onClick={() => loadStudents(studentSearch)}>Search</button>
            </div>

            <div style={{ maxHeight: 220, overflow: "auto", border: "1px solid #e2e8f0", borderRadius: 8, marginBottom: 10 }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ background: "#f1f5f9" }}>
                    <th style={{ padding: 8, textAlign: "left" }}>ID</th>
                    <th style={{ padding: 8, textAlign: "left" }}>Roll</th>
                    <th style={{ padding: 8, textAlign: "left" }}>Name</th>
                    <th style={{ padding: 8, textAlign: "left" }}>Unique ID</th>
                  </tr>
                </thead>
                <tbody>
                  {students.map((s) => (
                    <tr key={s.id} onClick={() => setSelectedStudent(s)} style={{ cursor: "pointer", background: selectedStudent?.id === s.id ? "#dbeafe" : "transparent" }}>
                      <td style={{ padding: 8, borderTop: "1px solid #e2e8f0" }}>{s.id}</td>
                      <td style={{ padding: 8, borderTop: "1px solid #e2e8f0" }}>{s.roll_number}</td>
                      <td style={{ padding: 8, borderTop: "1px solid #e2e8f0" }}>{s.name}</td>
                      <td style={{ padding: 8, borderTop: "1px solid #e2e8f0" }}>{s.unique_id || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <form onSubmit={handleCreateStudent} style={{ display: "grid", gridTemplateColumns: "repeat(5,minmax(0,1fr))", gap: 8 }}>
              <input aria-label="Student name" style={input} placeholder="Name" value={newStudent.name} onChange={(e) => setNewStudent({ ...newStudent, name: e.target.value })} required />
              <input aria-label="Student roll number" style={input} placeholder="Roll Number" value={newStudent.roll_number} onChange={(e) => setNewStudent({ ...newStudent, roll_number: e.target.value })} required />
              <input aria-label="Student email" style={input} placeholder="Email" type="email" value={newStudent.email} onChange={(e) => setNewStudent({ ...newStudent, email: e.target.value })} required />
              <input aria-label="Student MAC address" style={input} placeholder="MAC XX:XX:..." value={newStudent.mac_address} onChange={(e) => setNewStudent({ ...newStudent, mac_address: e.target.value })} required />
              <input aria-label="Student unique ID optional" style={input} placeholder="Beacon unique_id (optional)" value={newStudent.unique_id} onChange={(e) => setNewStudent({ ...newStudent, unique_id: e.target.value })} />
              <button style={{ ...btn, gridColumn: "1/-1" }} type="submit">Create Student</button>
            </form>

            {selectedStudent && (
              <div style={{ marginTop: 12, borderTop: "1px solid #e2e8f0", paddingTop: 10 }}>
                <h3 style={{ margin: "0 0 8px" }}>Edit Student #{selectedStudent.id}</h3>
                <form onSubmit={handleUpdateStudent} style={{ display: "grid", gridTemplateColumns: "repeat(4,minmax(0,1fr))", gap: 8 }}>
                  <input aria-label="Edit student name" style={input} value={editStudent.name} onChange={(e) => setEditStudent({ ...editStudent, name: e.target.value })} required />
                  <input aria-label="Edit student email" style={input} type="email" value={editStudent.email} onChange={(e) => setEditStudent({ ...editStudent, email: e.target.value })} required />
                  <input aria-label="Edit student MAC address" style={input} value={editStudent.mac_address} onChange={(e) => setEditStudent({ ...editStudent, mac_address: e.target.value })} required />
                  <input aria-label="Edit student unique ID" style={input} value={editStudent.unique_id} onChange={(e) => setEditStudent({ ...editStudent, unique_id: e.target.value })} placeholder="unique_id" />
                  <button style={btn} type="submit">Update</button>
                  <button style={{ ...btn, borderColor: "#fca5a5", background: "#fff1f2" }} type="button" onClick={handleDeleteStudent}>Delete Student</button>
                </form>

                <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
                  <input aria-label="Beacon ID" style={{ ...input, minWidth: 220 }} placeholder="beacon_id (e.g. 1:1001)" value={beaconValue} onChange={(e) => setBeaconValue(e.target.value)} />
                  <button style={btn} type="button" onClick={handleRegisterBeacon}>Register Beacon</button>
                  <button style={btn} type="button" onClick={handleLookupBeacon}>Get Beacon</button>
                  {beaconLookup && (
                    <span style={{ alignSelf: "center", color: "#334155" }}>
                      Beacon: <strong>{beaconLookup.beacon_id}</strong> · Advertised: {String(beaconLookup.advertised)}
                    </span>
                  )}
                </div>
              </div>
            )}
          </section>

          <section style={section}>
            <h2 style={{ marginTop: 0 }}>Sessions</h2>

            <div style={{ maxHeight: 220, overflow: "auto", border: "1px solid #e2e8f0", borderRadius: 8, marginBottom: 10 }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ background: "#f1f5f9" }}>
                    <th style={{ padding: 8, textAlign: "left" }}>ID</th>
                    <th style={{ padding: 8, textAlign: "left" }}>Class</th>
                    <th style={{ padding: 8, textAlign: "left" }}>Threshold</th>
                  </tr>
                </thead>
                <tbody>
                  {sessions.map((s) => (
                    <tr key={s.session_id} onClick={() => setSelectedSessionId(s.session_id)} style={{ cursor: "pointer", background: Number(selectedSessionId) === s.session_id ? "#dbeafe" : "transparent" }}>
                      <td style={{ padding: 8, borderTop: "1px solid #e2e8f0" }}>{s.session_id}</td>
                      <td style={{ padding: 8, borderTop: "1px solid #e2e8f0" }}>{s.class_name}</td>
                      <td style={{ padding: 8, borderTop: "1px solid #e2e8f0" }}>{s.threshold_rssi}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <form onSubmit={handleCreateSession} style={{ display: "grid", gap: 8 }}>
              <input aria-label="Session class name" style={input} placeholder="Class Name" value={newSession.class_name} onChange={(e) => setNewSession({ ...newSession, class_name: e.target.value })} required />
              <input aria-label="Session start time" style={input} type="datetime-local" value={newSession.start_time} onChange={(e) => setNewSession({ ...newSession, start_time: e.target.value })} required />
              <input aria-label="Session end time optional" style={input} type="datetime-local" value={newSession.end_time} onChange={(e) => setNewSession({ ...newSession, end_time: e.target.value })} />
              <input aria-label="RSSI threshold" style={input} type="number" value={newSession.threshold_rssi} onChange={(e) => setNewSession({ ...newSession, threshold_rssi: e.target.value })} />
              <button style={btn} type="submit">Create Session</button>
            </form>

            {selectedSessionId && (
              <div style={{ marginTop: 12, borderTop: "1px solid #e2e8f0", paddingTop: 10, display: "grid", gap: 8 }}>
                <h3 style={{ margin: 0 }}>Selected Session #{selectedSessionId}</h3>
                {selectedSession && (
                  <div style={{ color: "#475569", fontSize: 14 }}>
                    {selectedSession.class_name} · Start: {new Date(selectedSession.start_time).toLocaleString()}
                  </div>
                )}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                  <input aria-label="Update session end time" style={input} type="datetime-local" value={sessionPatch.end_time} onChange={(e) => setSessionPatch({ ...sessionPatch, end_time: e.target.value })} placeholder="Set end time" />
                  <input aria-label="Update RSSI threshold" style={input} type="number" value={sessionPatch.threshold_rssi} onChange={(e) => setSessionPatch({ ...sessionPatch, threshold_rssi: e.target.value })} placeholder="Set threshold" />
                </div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <button style={btn} type="button" onClick={() => loadReport(selectedSessionId)}>Load Report</button>
                  <button style={btn} type="button" onClick={handleActivateSession}>Activate</button>
                  <button style={btn} type="button" onClick={handlePatchSession}>Update</button>
                  <button style={{ ...btn, borderColor: "#fca5a5", background: "#fff1f2" }} type="button" onClick={handleDeleteSession}>Delete</button>
                </div>
              </div>
            )}
          </section>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 14 }}>
          <section style={section}>
            <h2 style={{ marginTop: 0 }}>Attendance Report</h2>
            {!report ? (
              <p style={{ color: "#64748b" }}>Select a session and click “Load Report”.</p>
            ) : (
              <div>
                <p style={{ marginTop: 0 }}>
                  <strong>{report.class_name}</strong> · Present {report.present_count}/{report.total_students} · Absent {report.absent_count}
                </p>
                <div style={{ maxHeight: 280, overflow: "auto", border: "1px solid #e2e8f0", borderRadius: 8 }}>
                  <table style={{ width: "100%", borderCollapse: "collapse" }}>
                    <thead>
                      <tr style={{ background: "#f1f5f9" }}>
                        <th style={{ padding: 8, textAlign: "left" }}>Roll</th>
                        <th style={{ padding: 8, textAlign: "left" }}>Name</th>
                        <th style={{ padding: 8, textAlign: "left" }}>Status</th>
                        <th style={{ padding: 8, textAlign: "left" }}>Detected Time</th>
                        <th style={{ padding: 8, textAlign: "left" }}>RSSI</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.records.map((r) => (
                        <tr key={r.student_id}>
                          <td style={{ padding: 8, borderTop: "1px solid #e2e8f0" }}>{r.roll_number}</td>
                          <td style={{ padding: 8, borderTop: "1px solid #e2e8f0" }}>{r.name}</td>
                          <td style={{ padding: 8, borderTop: "1px solid #e2e8f0" }}><StatusPill status={r.status} /></td>
                          <td style={{ padding: 8, borderTop: "1px solid #e2e8f0" }}>{r.detected_time || "-"}</td>
                          <td style={{ padding: 8, borderTop: "1px solid #e2e8f0" }}>{r.rssi ?? "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </section>

          <section style={section}>
            <h2 style={{ marginTop: 0 }}>Attendance Records</h2>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto", gap: 8, marginBottom: 8 }}>
              <input aria-label="Filter by session ID" style={input} placeholder="Filter by session_id" value={attendanceSessionFilter} onChange={(e) => setAttendanceSessionFilter(e.target.value)} />
              <input aria-label="Filter by student ID" style={input} placeholder="Filter by student_id" value={attendanceStudentFilter} onChange={(e) => setAttendanceStudentFilter(e.target.value)} />
              <button style={btn} onClick={loadAttendanceList}>Apply</button>
            </div>

            <div style={{ maxHeight: 320, overflow: "auto", border: "1px solid #e2e8f0", borderRadius: 8 }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ background: "#f1f5f9" }}>
                    <th style={{ padding: 8, textAlign: "left" }}>ID</th>
                    <th style={{ padding: 8, textAlign: "left" }}>Student</th>
                    <th style={{ padding: 8, textAlign: "left" }}>Session</th>
                    <th style={{ padding: 8, textAlign: "left" }}>RSSI</th>
                    <th style={{ padding: 8, textAlign: "left" }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {attendance.map((a) => (
                    <tr key={a.attendance_id}>
                      <td style={{ padding: 8, borderTop: "1px solid #e2e8f0" }}>{a.attendance_id}</td>
                      <td style={{ padding: 8, borderTop: "1px solid #e2e8f0" }}>{a.student_id}</td>
                      <td style={{ padding: 8, borderTop: "1px solid #e2e8f0" }}>{a.session_id}</td>
                      <td style={{ padding: 8, borderTop: "1px solid #e2e8f0" }}>{a.rssi ?? "-"}</td>
                      <td style={{ padding: 8, borderTop: "1px solid #e2e8f0" }}>
                        <button style={{ ...btn, fontSize: 12 }} onClick={() => handleDeleteAttendance(a.attendance_id)}>
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
