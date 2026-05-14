/** Mnemosyne — Dashboard Review Plugin (plain IIFE, no build step). */
(function () {
  "use strict";
  const SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK) return;
  const { React } = SDK;
  const h = React.createElement;
  const { Card, CardContent, Badge, Button, Input, Label } = SDK.components;
  const { useCallback, useEffect, useMemo, useState } = SDK.hooks;
  const { cn, timeAgo, isoTimeAgo } = SDK.utils;
  const API = "/api/plugins/mnemosyne";
  const FILTERS = ["project", "repo", "branch", "discord_channel_id", "discord_thread_id", "type", "sensitivity"];

  function compactId(id) { return String(id || "").slice(0, 8); }
  function memoryTimeAgo(value) {
    if (value === undefined || value === null || value === "") return "";
    if (typeof value === "number") return timeAgo(value);
    const parsed = Date.parse(String(value));
    if (Number.isNaN(parsed)) return "unknown";
    return isoTimeAgo ? isoTimeAgo(String(value)) : timeAgo(Math.floor(parsed / 1000));
  }
  function qs(params) {
    const out = new URLSearchParams();
    Object.entries(params || {}).forEach(([k, v]) => { if (v !== undefined && v !== null && String(v).trim() !== "") out.set(k, String(v)); });
    return out.toString();
  }
  function Field(props) {
    return h("div", { className: "mnemo-field" },
      h(Label, null, props.label),
      h(Input, { value: props.value || "", placeholder: props.placeholder || "", onChange: e => props.onChange(e.target.value) }),
    );
  }
  function Tag(props) { return h(Badge, { variant: "outline" }, props.children); }
  function MemoryCard(props) {
    const m = props.memory;
    const meta = m.metadata || {};
    return h("button", {
      type: "button",
      className: "mnemo-memory-card",
      "data-active": props.active ? "true" : "false",
      onClick: () => props.onSelect(m),
    },
      h("div", { className: "flex items-center justify-between gap-2" },
        h("div", { className: "mnemo-tags" },
          Tag({ children: compactId(m.id) }),
          m.type && Tag({ children: m.type }),
          m.sensitivity && Tag({ children: m.sensitivity }),
          meta.review_status && Tag({ children: meta.review_status }),
        ),
        h("span", { className: "text-xs text-muted-foreground" }, memoryTimeAgo(m.updated_at)),
      ),
      h("p", { className: "mnemo-text mt-2 text-sm" }, m.text || "(empty)"),
      h("div", { className: "mnemo-tags mt-2 text-xs" },
        m.project && Tag({ children: "project:" + m.project }),
        m.repo && Tag({ children: "repo:" + m.repo }),
        m.branch && Tag({ children: "branch:" + m.branch }),
        m.discord_channel_id && Tag({ children: "channel:" + m.discord_channel_id }),
      ),
    );
  }

  function MnemosynePage() {
    const [query, setQuery] = useState("");
    const [filters, setFilters] = useState({});
    const [data, setData] = useState(null);
    const [selected, setSelected] = useState(null);
    const [draft, setDraft] = useState({ text: "", type: "", sensitivity: "", confidence: 1 });
    const [previewQuery, setPreviewQuery] = useState("");
    const [preview, setPreview] = useState(null);
    const [mergeIds, setMergeIds] = useState("");
    const [mergeText, setMergeText] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");

    const load = useCallback(function () {
      setBusy(true); setError("");
      const url = API + "/memories?" + qs(Object.assign({ query, limit: 50 }, filters));
      SDK.fetchJSON(url)
        .then(d => { setData(d); if (!selected && d.items && d.items[0]) setSelected(d.items[0]); })
        .catch(e => setError(String(e.message || e)))
        .finally(() => setBusy(false));
    }, [query, filters, selected]);

    useEffect(() => { load(); }, []);
    useEffect(() => {
      if (!selected) return;
      setDraft({
        text: selected.text || "",
        type: selected.type || "fact",
        sensitivity: selected.sensitivity || "normal",
        confidence: selected.confidence == null ? 1 : selected.confidence,
      });
      setMergeText(selected.text || "");
    }, [selected && selected.id]);

    function setFilter(k, v) { setFilters(Object.assign({}, filters, { [k]: v })); }
    function reloadSelected(id) {
      SDK.fetchJSON(API + "/memories/" + encodeURIComponent(id)).then(d => { setSelected(d.memory); load(); });
    }
    function saveEdit() {
      if (!selected) return;
      setBusy(true); setError("");
      SDK.fetchJSON(API + "/memories/" + encodeURIComponent(selected.id), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draft),
      }).then(d => { setSelected(d.memory); load(); })
        .catch(e => setError(String(e.message || e))).finally(() => setBusy(false));
    }
    function approve() {
      if (!selected) return;
      setBusy(true); setError("");
      SDK.fetchJSON(API + "/memories/" + encodeURIComponent(selected.id) + "/approve", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confidence: Math.max(Number(draft.confidence || 1), 0.9) }),
      }).then(d => { setSelected(d.memory); load(); })
        .catch(e => setError(String(e.message || e))).finally(() => setBusy(false));
    }
    function remove() {
      if (!selected) return;
      if (!window.confirm("Delete Mnemosyne memory " + selected.id + "?")) return;
      setBusy(true); setError("");
      SDK.fetchJSON(API + "/memories/" + encodeURIComponent(selected.id), { method: "DELETE" })
        .then(() => { setSelected(null); load(); })
        .catch(e => setError(String(e.message || e))).finally(() => setBusy(false));
    }
    function merge() {
      const ids = mergeIds.split(/[\s,]+/).map(s => s.trim()).filter(Boolean);
      if (selected && !ids.includes(selected.id)) ids.unshift(selected.id);
      if (ids.length < 2) { setError("Merge needs at least two memory ids."); return; }
      if (!window.confirm("Merge " + ids.length + " memories and delete source rows?")) return;
      setBusy(true); setError("");
      SDK.fetchJSON(API + "/memories/merge", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_ids: ids, text: mergeText, type: draft.type || "fact", sensitivity: draft.sensitivity || "normal", delete_sources: true }),
      }).then(d => { setSelected(d.memory); load(); })
        .catch(e => setError(String(e.message || e))).finally(() => setBusy(false));
    }
    function loadPreview() {
      SDK.fetchJSON(API + "/injections/latest?" + qs(Object.assign({ query: previewQuery || query, limit: 5 }, filters)))
        .then(setPreview).catch(e => setError(String(e.message || e)));
    }

    const config = data && data.config ? data.config : {};
    const items = data && data.items ? data.items : [];
    const activeId = selected && selected.id;

    return h("div", { className: "mnemo-page" },
      h("div", { className: "mnemo-hero" },
        h(Card, null, h(CardContent, { className: "py-5" },
          h("div", { className: "flex flex-wrap items-center gap-3" },
            h("h1", { className: "text-2xl font-semibold" }, "Mnemosyne Review"),
            Tag({ children: "local SQLite" }), Tag({ children: "provider opt-in" }), busy && Tag({ children: "loading" }),
          ),
          h("p", { className: "mt-2 text-sm text-muted-foreground" }, "Search and review profile-scoped memories by project, repo, branch, Discord channel/thread, type, and sensitivity. Approve/delete/merge/edit controls store review state without changing the core schema."),
          error && h("p", { className: "mt-3 text-sm text-destructive" }, error),
        )),
        h(Card, null, h(CardContent, { className: "py-5 text-sm" },
          h("div", { className: "grid grid-cols-2 gap-2" },
            h("span", { className: "text-muted-foreground" }, "Max memories"), h("span", null, String(config.max_memories || "—")),
            h("span", { className: "text-muted-foreground" }, "Token budget"), h("span", null, String(config.max_tokens || "—")),
            h("span", { className: "text-muted-foreground" }, "Min score"), h("span", null, String(config.min_score || "—")),
            h("span", { className: "text-muted-foreground" }, "Retrieve every turn"), h("span", null, config.retrieve_on_every_turn ? "enabled" : "disabled"),
          ),
        )),
      ),
      h("div", { className: "mnemo-grid" },
        h("div", { className: "mnemo-filters" },
          h(Card, null, h(CardContent, { className: "flex flex-col gap-3 py-4" },
            Field({ label: "Search text", value: query, onChange: setQuery, placeholder: "memory text" }),
            h("div", { className: "mnemo-filter-grid" }, FILTERS.map(k => Field({ key: k, label: k, value: filters[k] || "", onChange: v => setFilter(k, v) }))),
            h("div", { className: "mnemo-actions" },
              h(Button, { onClick: load }, "Search"),
              h(Button, { variant: "outline", onClick: () => { setQuery(""); setFilters({}); setTimeout(load, 0); } }, "Clear"),
            ),
          )),
          h(Card, { className: "mnemo-injection mt-4" }, h(CardContent, { className: "flex flex-col gap-3 py-4" },
            Field({ label: "Injection preview query", value: previewQuery, onChange: setPreviewQuery, placeholder: "current user turn" }),
            h(Button, { variant: "outline", onClick: loadPreview }, "Preview scores/budget"),
            preview && h("div", { className: "text-xs text-muted-foreground" }, "approx ", String(preview.budget.approx_tokens), "/", String(preview.budget.max_tokens), " tokens · min score ", String(preview.budget.min_score)),
            preview && (preview.items || []).map(m => h("div", { key: m.id, className: "text-xs" }, Tag({ children: String(m.score) }), " ", compactId(m.id), " — ", (m.text || "").slice(0, 90))),
          )),
        ),
        h("div", { className: "grid gap-4" },
          h(Card, { className: "mnemo-list" }, h(CardContent, { className: "py-4" },
            h("div", { className: "mb-3 flex items-center justify-between" },
              h("h2", { className: "text-lg font-medium" }, "Memories"),
              h("span", { className: "text-sm text-muted-foreground" }, String(data ? data.total : 0), " total"),
            ),
            items.length ? h("div", { className: "mnemo-memory-list" }, items.map(m => h(MemoryCard, { key: m.id, memory: m, active: activeId === m.id, onSelect: setSelected }))) : h("div", { className: "mnemo-empty" }, "No memories match these filters."),
          )),
          h(Card, { className: "mnemo-detail" }, h(CardContent, { className: "flex flex-col gap-3 py-4" },
            h("h2", { className: "text-lg font-medium" }, "Review controls"),
            !selected && h("div", { className: "mnemo-empty" }, "Select a memory to review."),
            selected && h(React.Fragment, null,
              h("div", { className: "mnemo-tags" }, Tag({ children: selected.id }), selected.project && Tag({ children: selected.project }), selected.repo && Tag({ children: selected.repo }), selected.branch && Tag({ children: selected.branch })),
              h("textarea", { className: "min-h-32 rounded-md border border-border bg-background/50 p-3 text-sm", value: draft.text, onChange: e => setDraft(Object.assign({}, draft, { text: e.target.value })) }),
              h("div", { className: "mnemo-filter-grid" },
                Field({ label: "type", value: draft.type, onChange: v => setDraft(Object.assign({}, draft, { type: v })) }),
                Field({ label: "sensitivity", value: draft.sensitivity, onChange: v => setDraft(Object.assign({}, draft, { sensitivity: v })) }),
                Field({ label: "confidence", value: String(draft.confidence), onChange: v => setDraft(Object.assign({}, draft, { confidence: Number(v) || 0 })) }),
              ),
              h("div", { className: "mnemo-actions" },
                h(Button, { onClick: saveEdit }, "Save edit"),
                h(Button, { variant: "outline", onClick: approve }, "Approve"),
                h(Button, { variant: "destructive", onClick: remove }, "Delete"),
              ),
              h("div", { className: "grid gap-2" },
                h(Label, null, "Merge with source ids"),
                h(Input, { value: mergeIds, onChange: e => setMergeIds(e.target.value), placeholder: "comma/space separated IDs" }),
                h("textarea", { className: "min-h-24 rounded-md border border-border bg-background/50 p-3 text-sm", value: mergeText, onChange: e => setMergeText(e.target.value) }),
                h(Button, { variant: "outline", onClick: merge }, "Merge selected + IDs"),
              ),
              h("pre", { className: "mnemo-code text-xs" }, JSON.stringify(selected.metadata || {}, null, 2)),
            ),
          )),
        ),
      ),
    );
  }

  window.__HERMES_PLUGINS__.register("mnemosyne", MnemosynePage);
})();
