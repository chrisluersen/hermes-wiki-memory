/**
 * Hermes Wiki Memory — Dashboard Plugin
 *
 * Status + activity pane for the wiki memory provider:
 *   - Overview — wiki location, git head/branch, gbrain availability, last commit
 *   - Counts   — pages by knowledge/ category and by entities subdir
 *   - Activity — recent commits to the knowledge base (the durable activity log)
 *
 * Plain IIFE, no build step. Uses window.__HERMES_PLUGIN_SDK__ for React +
 * shadcn primitives, same as the rollup and kanban plugins. Read-only — no
 * mutating endpoints, no state written.
 */
(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK) return;

  const { React } = SDK;
  const h = React.createElement;
  const { Card, CardContent, Badge } = SDK.components;
  const { useState, useEffect, useCallback } = SDK.hooks;
  const { cn, isoTimeAgo } = SDK.utils;

  const API = "/api/plugins/wiki";

  function Icon(props) {
    const name = props.name || "";
    return h("svg", {
      className: props.className || "",
      width: props.size || 16,
      height: props.size || 16,
      viewBox: "0 0 24 24",
      fill: "none",
      stroke: "currentColor",
      strokeWidth: 2,
      strokeLinecap: "round",
      strokeLinejoin: "round",
      "aria-hidden": "true",
      dangerouslySetInnerHTML: { __html: ICON_PATHS[name] || "" },
    });
  }

  const ICON_PATHS = {
    book: '<path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/><path d="M8 7h8"/><path d="M8 11h8"/>',
    activity: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    layers: '<path d="m12 2 10 6-10 6L2 8Z"/><path d="m2 12 10 6 10-6"/><path d="m2 16 10 6 10-6"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    git: '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="6" r="3"/><path d="M6 9v6"/><path d="M18 9a9 9 0 0 1-9 9"/>',
    alert: '<path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/>',
  };

  const CATEGORY_LABELS = {
    concepts: "Concepts",
    entities: "Entities",
    comparisons: "Comparisons",
    queries: "Queries",
    references: "References",
  };

  // ---------------------------------------------------------------------
  // Section: overview
  // ---------------------------------------------------------------------

  function OverviewCard({ data }) {
    if (!data) return null;
    const git = data.git_branch || "?";
    const head = data.git_head || "—";
    const ahead = data.git_ahead && data.git_ahead !== "0" ? data.git_ahead : null;
    const gb = data.gbrain || {};
    const gbOk = gb.binary_on_path && gb.config_exists;
    const last = data.last_commit;

    const rows = [
      { label: "Wiki root", value: data.wiki_exists ? data.wiki_root : "(missing)", ok: !!data.wiki_exists },
      { label: "Branch", value: git },
      { label: "Head", value: head, extra: ahead ? `${ahead} unpushed` : null, ok: !ahead },
      { label: "gbrain", value: gbOk ? "available" : "unavailable", ok: gbOk },
    ];

    return h(
      Card,
      null,
      h(
        CardContent,
        null,
        h("h3", { className: "wiki-sec-title" },
          h(Icon, { name: "activity", size: 14, className: "wiki-icon" }),
          " Brain health"
        ),
        h(
          "div",
          { className: "wiki-rows" },
          rows.map(function (r) {
            return h(
              "div",
              { className: "wiki-row" },
              h("span", { className: "wiki-row-label" }, r.label),
              h("span", { className: "wiki-row-value" },
                h("span", { className: cn("wiki-dot", r.ok === false && "wiki-dot-bad") }),
                r.value,
                r.extra ? h("span", { className: "wiki-row-extra" }, r.extra) : null
              )
            );
          })
        ),
        last
          ? h(
              "div",
              { className: "wiki-last-commit" },
              h("span", { className: "wiki-last-subj" }, last.subject),
              h("span", { className: "wiki-last-meta" },
                last.hash,
                " · ",
                last.date ? isoTimeAgo(last.date) : ""
              )
            )
          : null
      )
    );
  }

  // ---------------------------------------------------------------------
  // Section: counts
  // ---------------------------------------------------------------------

  function CountBar({ label, value, total }) {
    const pct = total > 0 ? Math.round((value / total) * 100) : 0;
    return h(
      "div",
      { className: "wiki-countbar" },
      h(
        "div",
        { className: "wiki-countbar-head" },
        h("span", { className: "wiki-countbar-label" }, label),
        h("span", { className: "wiki-countbar-val" }, value)
      ),
      h(
        "div",
        { className: "wiki-countbar-track" },
        h("div", { className: "wiki-countbar-fill", style: { width: pct + "%" } })
      )
    );
  }

  function CountsCard({ data }) {
    if (!data) return null;
    const cats = data.categories || {};
    const subs = data.entities_subdirs || {};
    const total = data.total || 0;
    const entries = Object.keys(cats).map(function (k) {
      return h(CountBar, { key: k, label: CATEGORY_LABELS[k] || k, value: cats[k], total: total });
    });
    const subEntries = Object.keys(subs).map(function (k) {
      return h(CountBar, { key: k, label: k, value: subs[k], total: total });
    });
    return h(
      Card,
      null,
      h(
        CardContent,
        null,
        h("h3", { className: "wiki-sec-title" },
          h(Icon, { name: "layers", size: 14, className: "wiki-icon" }),
          " Knowledge base · ",
          total,
          " pages"
        ),
        h("div", { className: "wiki-counts" }, entries),
        subEntries.length
          ? h("h4", { className: "wiki-sec-subtitle" }, "Entities subdirs (provider writes)")
          : null,
        subEntries.length ? h("div", { className: "wiki-counts" }, subEntries) : null
      )
    );
  }

  // ---------------------------------------------------------------------
  // Section: activity
  // ---------------------------------------------------------------------

  function ActivityCard({ data }) {
    if (!data) return null;
    const commits = data.commits || [];
    return h(
      Card,
      null,
      h(
        CardContent,
        null,
        h("h3", { className: "wiki-sec-title" },
          h(Icon, { name: "git", size: 14, className: "wiki-icon" }),
          " Recent activity"
        ),
        commits.length === 0
          ? h("p", { className: "wiki-empty" }, "No wiki commits yet.")
          : h(
              "ul",
              { className: "wiki-commits" },
              commits.map(function (c) {
                return h(
                  "li",
                  { key: c.hash, className: "wiki-commit" },
                  h("span", { className: "wiki-commit-hash" }, c.hash),
                  h("span", { className: "wiki-commit-subj" }, c.subject),
                  h("span", { className: "wiki-commit-date" },
                    c.date ? isoTimeAgo(c.date) : ""
                  )
                );
              })
            )
      )
    );
  }

  // ---------------------------------------------------------------------
  // Root
  // ---------------------------------------------------------------------

  function WikiPage() {
    const [overview, setOverview] = useState(null);
    const [counts, setCounts] = useState(null);
    const [activity, setActivity] = useState(null);
    const [error, setError] = useState(null);

    const load = useCallback(function () {
      SDK.fetchJSON(API + "/overview").then(setOverview).catch(function (e) { setError(e.message); });
      SDK.fetchJSON(API + "/counts").then(setCounts).catch(function () {});
      SDK.fetchJSON(API + "/activity?limit=12").then(setActivity).catch(function () {});
    }, []);

    useEffect(function () {
      load();
      const timer = setInterval(load, 30000);
      function onVisible() { if (!document.hidden) load(); }
      document.addEventListener("visibilitychange", onVisible);
      return function () {
        clearInterval(timer);
        document.removeEventListener("visibilitychange", onVisible);
      };
    }, [load]);

    return h(
      "div",
      { className: "wiki-page" },
      error
        ? h("p", { className: "wiki-error" }, "Failed to load wiki status: " + error)
        : h(
            "div",
            { className: "wiki-grid" },
            h(OverviewCard, { data: overview }),
            h(CountsCard, { data: counts }),
            h(ActivityCard, { data: activity })
          )
    );
  }

  if (window.__HERMES_PLUGINS__ && typeof window.__HERMES_PLUGINS__.register === "function") {
    window.__HERMES_PLUGINS__.register("wiki", WikiPage);
  }
})();
