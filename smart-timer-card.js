/**
 * Smart Timer Card — custom Lovelace card for the smart_timer integration.
 *
 * Features:
 * - Device state toggle (on/off)
 * - Live countdown timer with animated ring
 * - Quick timer buttons (15m, 30m, 1h, 2h)
 * - Auto-off duration control
 * - Schedule list with add/remove
 * - Away mode toggle
 * - Daily runtime display
 */

class SmartTimerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._countdownInterval = null;
  }

  static getStubConfig() {
    return { entity: "" };
  }

  setConfig(config) {
    if (!config.entity) throw new Error("Please define an entity");
    this._config = {
      entity: config.entity,
      name: config.name || null,
      show_schedules: config.show_schedules !== false,
      show_away: config.show_away !== false,
      show_runtime: config.show_runtime !== false,
      presets: config.presets || [15, 30, 60, 120],
    };
    this._slug = config.entity.split(".").pop();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
    this._startCountdown();
  }

  getCardSize() {
    return 4;
  }

  _getEntities() {
    const s = this._slug;
    return {
      device: this._hass.states[this._config.entity],
      autoOff: this._hass.states[`number.${s}_auto_off`],
      timerActive: this._hass.states[`binary_sensor.${s}_timer_active`],
      timeRemaining: this._hass.states[`sensor.${s}_time_remaining`],
      dailyRuntime: this._hass.states[`sensor.${s}_daily_runtime`],
      nextSchedule: this._hass.states[`sensor.${s}_next_schedule`],
      awayMode: this._hass.states[`switch.${s}_away_mode`],
    };
  }

  _startCountdown() {
    if (this._countdownInterval) clearInterval(this._countdownInterval);
    this._countdownInterval = setInterval(() => {
      const e = this._getEntities();
      if (!e.timerActive || e.timerActive.state !== "on") return;
      const cd = this.shadowRoot.getElementById("countdown-value");
      const ring = this.shadowRoot.getElementById("countdown-ring");
      if (!cd || !e.timerActive.attributes.expiry) return;
      const exp = new Date(e.timerActive.attributes.expiry);
      const now = new Date();
      const diff = Math.max(0, Math.floor((exp - now) / 1000));
      const m = Math.floor(diff / 60);
      const s = diff % 60;
      cd.textContent = m > 0 ? `${m}:${s.toString().padStart(2, "0")}` : `${s}s`;
    }, 1000);
  }

  disconnectedCallback() {
    if (this._countdownInterval) clearInterval(this._countdownInterval);
  }

  async _callService(domain, service, data) {
    await this._hass.callService(domain, service, data);
  }

  _render() {
    if (!this._hass) return;
    const e = this._getEntities();
    if (!e.device) {
      this.shadowRoot.innerHTML = `<ha-card><div style="padding:16px;">Entity ${this._config.entity} not found</div></ha-card>`;
      return;
    }

    const isOn = e.device.state === "on" || e.device.state === "open" || e.device.state === "playing";
    const name = this._config.name || e.device.attributes.friendly_name || this._config.entity;
    const timerOn = e.timerActive && e.timerActive.state === "on";
    const remaining = timerOn ? (e.timerActive.attributes.remaining || "0s") : null;
    const timerAction = timerOn ? e.timerActive.attributes.action : null;
    const autoOff = e.autoOff ? parseFloat(e.autoOff.state) || 0 : 0;
    const runtime = e.dailyRuntime ? e.dailyRuntime.state : "0m";
    const runtimeSecs = e.dailyRuntime ? (e.dailyRuntime.attributes.seconds || 0) : 0;
    const nextSched = e.nextSchedule ? e.nextSchedule.state : "none";
    const schedules = e.nextSchedule ? (e.nextSchedule.attributes.schedules || []) : [];
    const awayOn = e.awayMode && e.awayMode.state === "on";

    const presetBtns = this._config.presets.map(mins => {
      const label = mins >= 60 ? `${mins / 60}h` : `${mins}m`;
      return `<button class="preset-btn" data-minutes="${mins}" data-action="turn_off">${label}</button>`;
    }).join("");

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        ha-card {
          padding: 16px;
          font-family: var(--ha-card-font-family, inherit);
        }
        .header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 12px;
        }
        .header-left {
          display: flex;
          align-items: center;
          gap: 10px;
        }
        .device-name {
          font-size: 1.1em;
          font-weight: 500;
          color: var(--primary-text-color);
        }
        .state-badge {
          display: inline-block;
          padding: 2px 8px;
          border-radius: 10px;
          font-size: 0.75em;
          font-weight: 600;
          text-transform: uppercase;
        }
        .state-on { background: var(--success-color, #4caf50); color: #fff; }
        .state-off { background: var(--disabled-color, #9e9e9e); color: #fff; }
        .toggle-btn {
          background: none;
          border: 2px solid var(--primary-color);
          border-radius: 50%;
          width: 36px;
          height: 36px;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--primary-color);
          font-size: 16px;
          transition: all 0.2s;
        }
        .toggle-btn:hover { background: var(--primary-color); color: #fff; }

        /* Timer section */
        .timer-section {
          background: var(--card-background-color, var(--secondary-background-color));
          border-radius: 12px;
          padding: 12px;
          margin-bottom: 10px;
          border: 1px solid var(--divider-color, #e0e0e0);
        }
        .timer-active {
          border-color: var(--warning-color, #ff9800);
          background: color-mix(in srgb, var(--warning-color, #ff9800) 8%, transparent);
        }
        .timer-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 8px;
        }
        .timer-label {
          font-size: 0.85em;
          color: var(--secondary-text-color);
          font-weight: 500;
        }
        .countdown-display {
          font-size: 1.8em;
          font-weight: 700;
          font-variant-numeric: tabular-nums;
          color: var(--primary-text-color);
          text-align: center;
          padding: 4px 0;
        }
        .countdown-action {
          font-size: 0.7em;
          color: var(--secondary-text-color);
          text-align: center;
          margin-top: -4px;
          margin-bottom: 8px;
        }
        .cancel-btn {
          background: var(--error-color, #f44336);
          color: #fff;
          border: none;
          border-radius: 8px;
          padding: 6px 16px;
          cursor: pointer;
          font-size: 0.8em;
          font-weight: 500;
        }
        .cancel-btn:hover { opacity: 0.85; }

        /* Presets */
        .presets {
          display: flex;
          gap: 6px;
          margin-bottom: 10px;
        }
        .preset-btn {
          flex: 1;
          background: var(--primary-color);
          color: var(--text-primary-color, #fff);
          border: none;
          border-radius: 8px;
          padding: 8px 4px;
          cursor: pointer;
          font-size: 0.85em;
          font-weight: 500;
          transition: opacity 0.2s;
        }
        .preset-btn:hover { opacity: 0.85; }

        /* Delayed on presets */
        .presets-on .preset-btn {
          background: var(--success-color, #4caf50);
        }

        /* Timer direction tabs */
        .timer-tabs {
          display: flex;
          gap: 4px;
          margin-bottom: 8px;
        }
        .timer-tab {
          flex: 1;
          padding: 6px;
          text-align: center;
          font-size: 0.8em;
          border-radius: 6px;
          cursor: pointer;
          border: 1px solid var(--divider-color);
          background: transparent;
          color: var(--primary-text-color);
          font-weight: 500;
        }
        .timer-tab.active {
          background: var(--primary-color);
          color: var(--text-primary-color, #fff);
          border-color: var(--primary-color);
        }

        /* Auto-off row */
        .setting-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 8px 0;
          border-top: 1px solid var(--divider-color, #e0e0e0);
        }
        .setting-label {
          font-size: 0.85em;
          color: var(--secondary-text-color);
        }
        .setting-value {
          font-size: 0.85em;
          font-weight: 500;
        }
        .auto-off-input {
          width: 70px;
          padding: 4px 6px;
          border: 1px solid var(--divider-color);
          border-radius: 6px;
          text-align: center;
          font-size: 0.85em;
          background: var(--card-background-color);
          color: var(--primary-text-color);
        }

        /* Schedule section */
        .section-title {
          font-size: 0.85em;
          font-weight: 600;
          color: var(--secondary-text-color);
          margin: 12px 0 6px;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        .schedule-item {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 6px 0;
          font-size: 0.85em;
        }
        .schedule-info {
          display: flex;
          gap: 8px;
          align-items: center;
        }
        .schedule-time {
          font-weight: 600;
          font-variant-numeric: tabular-nums;
        }
        .schedule-action {
          padding: 1px 6px;
          border-radius: 4px;
          font-size: 0.75em;
          font-weight: 600;
        }
        .schedule-action.on { background: var(--success-color, #4caf50); color: #fff; }
        .schedule-action.off { background: var(--error-color, #f44336); color: #fff; }
        .schedule-days {
          color: var(--secondary-text-color);
          font-size: 0.8em;
        }
        .schedule-remove {
          background: none;
          border: none;
          color: var(--error-color, #f44336);
          cursor: pointer;
          font-size: 1em;
          padding: 2px 6px;
        }
        .add-schedule-btn {
          background: none;
          border: 1px dashed var(--divider-color);
          border-radius: 8px;
          padding: 6px;
          width: 100%;
          cursor: pointer;
          color: var(--secondary-text-color);
          font-size: 0.8em;
          margin-top: 4px;
        }
        .add-schedule-btn:hover { border-color: var(--primary-color); color: var(--primary-color); }

        /* Add schedule form */
        .add-form {
          display: none;
          border: 1px solid var(--divider-color);
          border-radius: 8px;
          padding: 10px;
          margin-top: 6px;
        }
        .add-form.visible { display: block; }
        .form-row {
          display: flex;
          gap: 8px;
          align-items: center;
          margin-bottom: 8px;
        }
        .form-row label {
          font-size: 0.8em;
          color: var(--secondary-text-color);
          min-width: 50px;
        }
        .form-row input, .form-row select {
          padding: 4px 6px;
          border: 1px solid var(--divider-color);
          border-radius: 6px;
          font-size: 0.85em;
          background: var(--card-background-color);
          color: var(--primary-text-color);
        }
        .day-toggles {
          display: flex;
          gap: 3px;
        }
        .day-toggle {
          width: 28px;
          height: 28px;
          border-radius: 50%;
          border: 1px solid var(--divider-color);
          background: transparent;
          font-size: 0.7em;
          cursor: pointer;
          color: var(--primary-text-color);
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .day-toggle.active {
          background: var(--primary-color);
          color: var(--text-primary-color, #fff);
          border-color: var(--primary-color);
        }
        .form-actions {
          display: flex;
          gap: 8px;
          justify-content: flex-end;
        }
        .form-actions button {
          padding: 5px 14px;
          border-radius: 6px;
          border: none;
          cursor: pointer;
          font-size: 0.8em;
          font-weight: 500;
        }
        .btn-save { background: var(--primary-color); color: var(--text-primary-color, #fff); }
        .btn-cancel { background: var(--disabled-color, #9e9e9e); color: #fff; }

        /* Away mode */
        .away-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 8px 0;
        }
        .away-toggle {
          position: relative;
          width: 40px;
          height: 22px;
          border-radius: 11px;
          background: var(--disabled-color, #9e9e9e);
          border: none;
          cursor: pointer;
          transition: background 0.2s;
        }
        .away-toggle.on { background: var(--primary-color); }
        .away-toggle::after {
          content: '';
          position: absolute;
          top: 2px;
          left: 2px;
          width: 18px;
          height: 18px;
          border-radius: 50%;
          background: #fff;
          transition: transform 0.2s;
        }
        .away-toggle.on::after { transform: translateX(18px); }

        /* Footer stats */
        .footer {
          display: flex;
          justify-content: space-between;
          padding-top: 8px;
          margin-top: 4px;
          border-top: 1px solid var(--divider-color, #e0e0e0);
          font-size: 0.8em;
          color: var(--secondary-text-color);
        }
        .footer-stat {
          display: flex;
          align-items: center;
          gap: 4px;
        }
        .footer-value { font-weight: 600; color: var(--primary-text-color); }
        .empty-text {
          color: var(--secondary-text-color);
          font-size: 0.8em;
          text-align: center;
          padding: 8px 0;
        }
      </style>

      <ha-card>
        <!-- Header -->
        <div class="header">
          <div class="header-left">
            <span class="device-name">${name}</span>
            <span class="state-badge ${isOn ? "state-on" : "state-off"}">${isOn ? "ON" : "OFF"}</span>
          </div>
          <button class="toggle-btn" id="toggle-device" title="Toggle device">
            ${isOn ? "⏻" : "⏻"}
          </button>
        </div>

        <!-- Timer section -->
        <div class="timer-section ${timerOn ? "timer-active" : ""}">
          ${timerOn ? `
            <div class="timer-header">
              <span class="timer-label">Timer Active</span>
              <button class="cancel-btn" id="cancel-timer">Cancel</button>
            </div>
            <div class="countdown-display" id="countdown-value">${remaining}</div>
            <div class="countdown-action">will ${timerAction === "turn_on" ? "turn ON" : "turn OFF"}</div>
          ` : `
            <div class="timer-label" style="margin-bottom:8px">Quick Timer (turn off in...)</div>
            <div class="presets" id="presets-off">
              ${presetBtns}
            </div>
            <div class="timer-label" style="margin-bottom:8px">Delayed Turn On (turn on in...)</div>
            <div class="presets presets-on" id="presets-on">
              ${this._config.presets.map(mins => {
                const label = mins >= 60 ? `${mins / 60}h` : `${mins}m`;
                return `<button class="preset-btn" data-minutes="${mins}" data-action="turn_on">${label}</button>`;
              }).join("")}
            </div>
          `}
        </div>

        <!-- Auto-off setting -->
        <div class="setting-row">
          <span class="setting-label">Auto-Off Duration</span>
          <div style="display:flex;align-items:center;gap:4px;">
            <input type="number" class="auto-off-input" id="auto-off-input"
              value="${autoOff}" min="0" max="1440" step="1" />
            <span class="setting-label">min</span>
          </div>
        </div>

        ${this._config.show_away ? `
        <!-- Away mode -->
        <div class="away-row">
          <span class="setting-label">Away Mode</span>
          <button class="away-toggle ${awayOn ? "on" : ""}" id="away-toggle"></button>
        </div>
        ` : ""}

        ${this._config.show_schedules ? `
        <!-- Schedules -->
        <div class="section-title">Schedules</div>
        ${schedules.length > 0 ? schedules.map(s => `
          <div class="schedule-item">
            <div class="schedule-info">
              <span class="schedule-time">${s.time}</span>
              <span class="schedule-action ${s.action === "turn_on" ? "on" : "off"}">${s.action === "turn_on" ? "ON" : "OFF"}</span>
              <span class="schedule-days">${s.days}</span>
            </div>
            <button class="schedule-remove" data-schedule-id="${s.id}" title="Remove">✕</button>
          </div>
        `).join("") : '<div class="empty-text">No schedules configured</div>'}
        <button class="add-schedule-btn" id="add-schedule-btn">+ Add Schedule</button>
        <div class="add-form" id="add-form">
          <div class="form-row">
            <label>Time</label>
            <input type="time" id="sched-time" value="07:00" />
          </div>
          <div class="form-row">
            <label>Action</label>
            <select id="sched-action">
              <option value="turn_on">Turn ON</option>
              <option value="turn_off">Turn OFF</option>
            </select>
          </div>
          <div class="form-row">
            <label>Days</label>
            <div class="day-toggles" id="day-toggles">
              <button class="day-toggle" data-day="0">M</button>
              <button class="day-toggle" data-day="1">T</button>
              <button class="day-toggle" data-day="2">W</button>
              <button class="day-toggle" data-day="3">T</button>
              <button class="day-toggle" data-day="4">F</button>
              <button class="day-toggle" data-day="5">S</button>
              <button class="day-toggle" data-day="6">S</button>
            </div>
          </div>
          <div class="form-actions">
            <button class="btn-cancel" id="form-cancel">Cancel</button>
            <button class="btn-save" id="form-save">Add</button>
          </div>
        </div>
        ` : ""}

        ${this._config.show_runtime ? `
        <!-- Footer stats -->
        <div class="footer">
          <div class="footer-stat">
            <span>Runtime today:</span>
            <span class="footer-value">${runtime}</span>
          </div>
          ${nextSched !== "none" ? `
          <div class="footer-stat">
            <span>Next:</span>
            <span class="footer-value">${nextSched}</span>
          </div>
          ` : ""}
        </div>
        ` : ""}
      </ha-card>
    `;

    this._attachEvents();
  }

  _attachEvents() {
    const entity = this._config.entity;

    // Toggle device
    const toggle = this.shadowRoot.getElementById("toggle-device");
    if (toggle) {
      toggle.addEventListener("click", () => {
        const e = this._getEntities();
        const isOn = e.device && (e.device.state === "on" || e.device.state === "open");
        this._callService("homeassistant", isOn ? "turn_off" : "turn_on", { entity_id: entity });
      });
    }

    // Cancel timer
    const cancel = this.shadowRoot.getElementById("cancel-timer");
    if (cancel) {
      cancel.addEventListener("click", () => {
        this._callService("smart_timer", "cancel_timer", { entity_id: entity });
      });
    }

    // Preset buttons (off and on)
    this.shadowRoot.querySelectorAll(".preset-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const minutes = parseInt(btn.dataset.minutes);
        const action = btn.dataset.action || "turn_off";
        this._callService("smart_timer", "start_timer", { entity_id: entity, minutes, action });
      });
    });

    // Auto-off input
    const autoOffInput = this.shadowRoot.getElementById("auto-off-input");
    if (autoOffInput) {
      let debounce;
      autoOffInput.addEventListener("change", () => {
        clearTimeout(debounce);
        debounce = setTimeout(() => {
          const val = parseFloat(autoOffInput.value) || 0;
          this._callService("number", "set_value", {
            entity_id: `number.${this._slug}_auto_off`,
            value: val,
          });
        }, 300);
      });
    }

    // Away mode toggle
    const awayToggle = this.shadowRoot.getElementById("away-toggle");
    if (awayToggle) {
      awayToggle.addEventListener("click", () => {
        const e = this._getEntities();
        const isOn = e.awayMode && e.awayMode.state === "on";
        this._callService("switch", isOn ? "turn_off" : "turn_on", {
          entity_id: `switch.${this._slug}_away_mode`,
        });
      });
    }

    // Schedule remove buttons
    this.shadowRoot.querySelectorAll(".schedule-remove").forEach(btn => {
      btn.addEventListener("click", () => {
        this._callService("smart_timer", "remove_schedule", {
          entity_id: entity,
          schedule_id: btn.dataset.scheduleId,
        });
      });
    });

    // Add schedule form
    const addBtn = this.shadowRoot.getElementById("add-schedule-btn");
    const form = this.shadowRoot.getElementById("add-form");
    if (addBtn && form) {
      addBtn.addEventListener("click", () => form.classList.toggle("visible"));

      // Day toggles
      this.shadowRoot.querySelectorAll(".day-toggle").forEach(dt => {
        dt.addEventListener("click", () => dt.classList.toggle("active"));
      });

      // Cancel form
      const formCancel = this.shadowRoot.getElementById("form-cancel");
      if (formCancel) formCancel.addEventListener("click", () => form.classList.remove("visible"));

      // Save schedule
      const formSave = this.shadowRoot.getElementById("form-save");
      if (formSave) {
        formSave.addEventListener("click", () => {
          const time = this.shadowRoot.getElementById("sched-time").value;
          const action = this.shadowRoot.getElementById("sched-action").value;
          const days = [];
          this.shadowRoot.querySelectorAll(".day-toggle.active").forEach(dt => {
            days.push(dt.dataset.day);
          });

          const data = { entity_id: entity, action, time };
          if (days.length > 0) data.days = days;

          this._callService("smart_timer", "add_schedule", data);
          form.classList.remove("visible");
        });
      }
    }
  }
}

customElements.define("smart-timer-card", SmartTimerCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "smart-timer-card",
  name: "Smart Timer",
  description: "Control device timers, schedules, away mode, and runtime tracking.",
});
