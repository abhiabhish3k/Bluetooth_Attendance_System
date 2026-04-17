/**
 * BLE Attendance System – Dashboard
 *
 * A minimal React dashboard for viewing attendance reports.
 * Connects to the FastAPI backend at http://localhost:8000.
 */

import { useState, useEffect, useCallback } from "react";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------
const api = {
  getSessions:        ()         => axios.get(`${API_BASE}/api/sessions`),
  getActiveSession:   ()         => axios.get(`${API_BASE}/api/sessions/active`),
  getReport:          (id)       => axios.get(`${API_BASE}/api/attendance/report/${id}`),
  getStudents:        ()         => axios.get(`${API_BASE}/api/students`),
  activateSession:    (id)       => axios.post(`${API_BASE}/api/sessions/${id}/activate`),
  createSession:      (data)     => axios.post(`${API_BASE}/api/sessions`, data),
  createStudent:      (data)     => axios.post(`${API_BASE}/api/students`, data),
};

// ---------------------------------------------------------------------------
// Components
// ---------------------------------------------------------------------------

function StatusBadge({ status }) {
  const colour = status === "present" ? "#22c55e" : "#ef4444";
  return (
    <span style={{
      background: colour, color: "#fff",
      padding: "2px 10px", borderRadius: 12, fontSize: 13, fontWeight: 600,
    }}>
      {status}
    </span>
  );
}

function AttendanceTable({ report }) {
  if (!report) return <p>No report loaded.</p>;
  return (
    <div>
      <h3>{report.class_name}</h3>
      <p>
        Present: <strong>{report.present_count}</strong> /&nbsp;
        Total: <strong>{report.total_students}</strong> &nbsp;|&nbsp;
        Absent: <strong>{report.absent_count}</strong>
      </p>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "#f1f5f9" }}>
            {["Roll No.", "Name", "Status", "Detected At", "RSSI"].map(h => (
              <th key={h} style={{ padding: "8px 12px", textAlign: "left", border: "1px solid #e2e8f0" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {report.records.map(r => (
            <tr key={r.student_id}>
              <td style={{ padding: "8px 12px", border: "1px solid #e2e8f0" }}>{r.roll_number}</td>
              <td style={{ padding: "8px 12px", border: "1px solid #e2e8f0" }}>{r.name}</td>
              <td style={{ padding: "8px 12px", border: "1px solid #e2e8f0" }}><StatusBadge status={r.status} /></td>
              <td style={{ padding: "8px 12px", border: "1px solid #e2e8f0" }}>{r.detected_time ?? "–"}</td>
              <td style={{ padding: "8px 12px", border: "1px solid #e2e8f0" }}>{r.rssi != null ? `${r.rssi} dBm` : "–"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main App
// ---------------------------------------------------------------------------
export default function App() {
  const [sessions, setSessions] = useState([]);
  const [activeSession, setActiveSession] = useState(null);
  const [selectedSessionId, setSelectedSessionId] = useState(null);
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const loadSessions = useCallback(async () => {
    try {
      const [sessRes, activeRes] = await Promise.all([
        api.getSessions(),
        api.getActiveSession(),
      ]);
      setSessions(sessRes.data);
      setActiveSession(activeRes.data.active ? activeRes.data.session : null);
    } catch (e) {
      setError("Could not connect to backend. Is it running?");
    }
  }, []);

  const loadReport = useCallback(async (id) => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.getReport(id);
      setReport(res.data);
    } catch (e) {
      setError(`Failed to load report for session ${id}`);
      setReport(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadSessions(); }, [loadSessions]);

  useEffect(() => {
    if (selectedSessionId) loadReport(selectedSessionId);
  }, [selectedSessionId, loadReport]);

  return (
    <div style={{ fontFamily: "system-ui, sans-serif", maxWidth: 900, margin: "0 auto", padding: "24px 16px" }}>
      <h1 style={{ color: "#1e293b" }}>📡 BLE Attendance Dashboard</h1>

      {activeSession && (
        <div style={{ background: "#dcfce7", border: "1px solid #86efac", borderRadius: 8, padding: "12px 16px", marginBottom: 16 }}>
          🟢 <strong>Active session:</strong> {activeSession.class_name} (ID: {activeSession.session_id})
        </div>
      )}

      {error && (
        <div style={{ background: "#fee2e2", border: "1px solid #fca5a5", borderRadius: 8, padding: "12px 16px", marginBottom: 16 }}>
          ❌ {error}
        </div>
      )}

      <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        {/* Session list */}
        <div style={{ flex: "0 0 260px" }}>
          <h2 style={{ fontSize: 16, marginBottom: 8 }}>Sessions</h2>
          <button onClick={loadSessions} style={{ marginBottom: 8, padding: "4px 12px", cursor: "pointer" }}>
            🔄 Refresh
          </button>
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {sessions.map(s => (
              <li
                key={s.session_id}
                onClick={() => setSelectedSessionId(s.session_id)}
                style={{
                  padding: "8px 12px", marginBottom: 4, cursor: "pointer",
                  background: s.session_id === selectedSessionId ? "#dbeafe" : "#f8fafc",
                  border: "1px solid #e2e8f0", borderRadius: 6,
                }}
              >
                <strong>{s.class_name}</strong><br />
                <small>{new Date(s.start_time).toLocaleString()}</small>
              </li>
            ))}
            {sessions.length === 0 && <li style={{ color: "#94a3b8" }}>No sessions yet.</li>}
          </ul>
        </div>

        {/* Report */}
        <div style={{ flex: 1, minWidth: 300 }}>
          <h2 style={{ fontSize: 16, marginBottom: 8 }}>
            Attendance Report
            {selectedSessionId && <span style={{ color: "#64748b", fontWeight: 400 }}> – Session #{selectedSessionId}</span>}
          </h2>
          {loading ? <p>Loading…</p> : <AttendanceTable report={report} />}
        </div>
      </div>
    </div>
  );
}
