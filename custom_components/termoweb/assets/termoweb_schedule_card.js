// Minimal 7x24 schedule editor for TermoWeb heaters
// Usage in Lovelace:
// resources:
//   - url: /local/termoweb/termoweb-schedule-card.js
//     type: module
// card:
//   - type: custom:termoweb-schedule-card
//     title: Bedroom heater schedule
//     entity: climate.bedroom_heater

(() => {
  const CARD_TAG = "termoweb-schedule-card";
  const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const LABELS = ["Cold", "Night", "Day"];
  const VALID = new Set([0, 1, 2]);

  class TermoWebScheduleCard extends HTMLElement {
    static getConfigElement() { return document.createElement("hui-generic-entity-row"); }
    static getStubConfig() { return { entity: "climate.some_heater" }; }

    setConfig(config) {
      if (!config || !config.entity) throw new Error("Required config: entity");
      this._config = config;
      if (!this.shadowRoot) this.attachShadow({ mode: "open" });
      this._selected = 2;          // default paint state: day
      this._dragging = false;
      this._prog = null;           // working copy
      this._origProg = null;       // last state from HA
      this._ptemp = null;
      this._entity = null;
      this._saving = false;
      this._render();
    }

    set hass(hass) {
      this._hass = hass;
      if (!this._config) return;
      const st = hass.states[this._config.entity];
      if (!st) return;
      this._entity = st;
      const attrs = st.attributes || {};
      const prog = Array.isArray(attrs.prog) ? attrs.prog.map((v) => parseInt(v)) : null;
      const ptemp = Array.isArray(attrs.ptemp) ? attrs.ptemp.map((v) => parseFloat(v)) : null;

      let shouldRender = false;

      if (prog && prog.length === 168 && prog.every((x) => VALID.has(Number(x)))) {
        const key = prog.join(",");
        if (!this._origProg || this._origProg.join(",") !== key) {
          this._origProg = prog.slice();
          if (!this._prog || this._saving === false) {
            // if not in the middle of saving, sync working copy
            this._prog = prog.slice();
            shouldRender = true;
          }
        }
      }

      if (ptemp && ptemp.length === 3) {
        if (!this._ptemp || this._ptemp.join(",") !== ptemp.join(",")) {
          this._ptemp = ptemp.slice();
          shouldRender = true;
        }
      }

      if (shouldRender) this._render();
    }

    getCardSize() { return 8; }

    _hourLabel(h) { return (h < 10 ? "0" + h : "" + h) + ":00"; }

    _render() {
      if (!this.shadowRoot) return;
      const style = `
        :host { display: block; }
        .wrap { padding: 12px; }
        .hdr { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
        .legend { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
        .legend button { border: 1px solid var(--divider-color); padding: 6px 10px; border-radius: 8px; cursor: pointer; background: transparent; }
        .legend button.sel { border-width: 2px; }
        .grid { display: grid; grid-template-columns: 64px repeat(7, 1fr); gap: 4px; }
        .cell { height: 26px; border-radius: 6px; background: var(--ha-card-background, #1c1c1c); display: flex; align-items: center; justify-content: center; cursor: pointer; border: 1px solid var(--divider-color); user-select: none; }
        .hour { text-align: right; padding-right: 8px; font-size: 12px; align-self: center; }
        .dayhdr { font-weight: 600; text-align: center; font-size: 12px; }
        .c0 { background: rgba(130,160,255,0.25); }
        .c1 { background: rgba(255,180,0,0.25); }
        .c2 { background: rgba(0,200,120,0.25); }
        .btns { display: flex; gap: 8px; justify-content: flex-end; margin-top: 10px; }
        .btn { padding: 6px 10px; border-radius: 8px; border: 1px solid var(--divider-color); cursor: pointer; background: transparent; }
        .btn[disabled] { opacity: .6; cursor: default; }
        .muted { opacity: .75; }
      `;

      const title = this._config.title || (this._entity && this._entity.attributes.friendly_name) || "Schedule";
      const prog = (this._prog && this._prog.length === 168) ? this._prog.slice() : new Array(168).fill(0);
      const ptemp = (this._ptemp && this._ptemp.length === 3) ? this._ptemp.slice() : [10, 20, 22];

      const makeDayHdr = () => {
        const hdr = document.createElement("div");
        hdr.className = "grid";
        hdr.appendChild(document.createElement("div")); // corner
        for (let d = 0; d < 7; d++) {
          const el = document.createElement("div");
          el.className = "dayhdr";
          el.textContent = DAYS[d];
          hdr.appendChild(el);
        }
        return hdr;
      };

      const grid = document.createElement("div");
      grid.className = "grid";

      for (let h = 0; h < 24; h++) {
        const hour = document.createElement("div");
        hour.className = "hour";
        hour.textContent = this._hourLabel(h);
        grid.appendChild(hour);

        for (let d = 0; d < 7; d++) {
          const idx = d * 24 + h; // Monday-based indexing
          const v = Number(prog[idx] ?? 0);
          const cell = document.createElement("div");
          cell.dataset.idx = String(idx);
          cell.className = `cell c${v}`;
          cell.title = `${DAYS[d]} ${this._hourLabel(h)} → ${LABELS[v]} (${Number.isFinite(ptemp[v]) ? ptemp[v].toFixed(1) : ptemp[v]}°C)`;
          cell.addEventListener("mousedown", () => { this._dragging = true; this._paintCell(cell); });
          cell.addEventListener("mouseenter", () => { if (this._dragging) this._paintCell(cell); });
          cell.addEventListener("mouseup", () => { this._dragging = false; });
          cell.addEventListener("click", () => { this._paintCell(cell); });
          grid.appendChild(cell);
        }
      }
      document.addEventListener("mouseup", () => { this._dragging = false; });

      const legend = document.createElement("div");
      legend.className = "legend";
      const mkBtn = (label, idx, temp) => {
        const b = document.createElement("button");
        b.textContent = `${label} ${Number.isFinite(temp) ? temp.toFixed(1) : temp}°C`;
        if (this._selected === idx) b.classList.add("sel");
        b.addEventListener("click", () => { this._selected = idx; this._render(); });
        return b;
      };
      legend.appendChild(mkBtn(LABELS[0], 0, ptemp[0]));
      legend.appendChild(mkBtn(LABELS[1], 1, ptemp[1]));
      legend.appendChild(mkBtn(LABELS[2], 2, ptemp[2]));

      const btns = document.createElement("div");
      btns.className = "btns";
      const revert = document.createElement("button");
      revert.className = "btn";
      revert.textContent = "Revert";
      revert.addEventListener("click", () => { if (this._origProg) { this._prog = this._origProg.slice(); this._render(); } });
      const save = document.createElement("button");
      save.className = "btn";
      save.textContent = this._saving ? "Saving..." : "Save";
      save.disabled = this._saving;
      save.addEventListener("click", () => this._save());
      btns.appendChild(revert);
      btns.appendChild(save);

      const root = document.createElement("div");
      root.className = "wrap";
      root.innerHTML = `<style>${style}</style><div class="hdr"><div>${title}</div><div class="muted">${this._config.entity}</div></div>`;
      root.appendChild(makeDayHdr());
      root.appendChild(grid);
      root.appendChild(legend);
      root.appendChild(btns);

      this.shadowRoot.innerHTML = "";
      this.shadowRoot.appendChild(root);
    }

    _paintCell(cell) {
      if (!cell || !this._prog) return;
      const idx = parseInt(cell.dataset.idx, 10);
      if (!Number.isInteger(idx) || idx < 0 || idx >= 168) return;
      this._prog[idx] = this._selected;
      cell.className = `cell c${this._selected}`;
    }

    async _save() {
      if (!this._hass || !this._config || !Array.isArray(this._prog) || this._prog.length !== 168) return;
      // Validate contents
      for (let i = 0; i < 168; i++) {
        const v = Number(this._prog[i]);
        if (!VALID.has(v)) return;
      }
      this._saving = true;
      this._render();
      try {
        await this._hass.callService("termoweb", "set_schedule", {
          entity_id: this._config.entity,
          prog: this._prog,
        });
      } catch (e) {
        // eslint-disable-next-line no-console
        console.error("termoweb-schedule: save failed", e);
      } finally {
        this._saving = false;
        this._render();
      }
    }
  }

  if (!customElements.get(CARD_TAG)) {
    customElements.define(CARD_TAG, TermoWebScheduleCard);
  }

  // Optional: register metadata for some dashboards
  window.customCards = window.customCards || [];
  const exists = window.customCards.some((c) => c.type === CARD_TAG);
  if (!exists) {
    window.customCards.push({
      type: CARD_TAG,
      name: "TermoWeb Schedule Card",
      description: "Edit the weekly 7x24 tri-state (Cold/Night/Day) schedule for a TermoWeb heater.",
      preview: false,
    });
  }
})();
