import { useEffect, useState } from "react";
import { api } from "../api/client";
type O = { id: number; label: string; capacity_note: string; cool_min: number };
export default function OvensPage() {
  const [rows, setRows] = useState<O[]>([]);
  // draft values keyed by oven id, so leaving and re-entering keeps the saved value
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [savedId, setSavedId] = useState<number | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    api<O[]>("/ovens").then(os => {
      setRows(os);
      setDrafts(Object.fromEntries(os.map(o => [o.id, String(o.cool_min)])));
    });
  }, []);
  async function save(id: number) {
    setErr(""); setSavedId(null);
    const cool_min = Math.max(0, Math.floor(Number(drafts[id] ?? 0) || 0));
    try {
      const o = await api<O>(`/ovens/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ cool_min }),
      });
      setRows(rs => rs.map(r => (r.id === id ? o : r)));
      setDrafts(d => ({ ...d, [id]: String(o.cool_min) }));
      setSavedId(id);
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
  }
  return (<>
    <h2>炉位</h2>
    {err && <div className="err">{err}</div>}
    <table className="table">
      <thead><tr><th>标签</th><th>备注</th><th>冷却分钟</th><th></th></tr></thead>
      <tbody>{rows.map(o => (
        <tr key={o.id}>
          <td>{o.label}</td>
          <td>{o.capacity_note}</td>
          <td className="mono">
            <input type="number" min={0} step={1} style={{ width: 90 }}
              value={drafts[o.id] ?? String(o.cool_min)}
              onChange={e => setDrafts(d => ({ ...d, [o.id]: e.target.value }))}
              onBlur={() => save(o.id)} />
          </td>
          <td>
            <button onClick={() => save(o.id)}>保存</button>
            {savedId === o.id && <span className="ok" style={{ marginLeft: 8 }}>已保存</span>}
          </td>
        </tr>
      ))}</tbody>
    </table>
  </>);
}
