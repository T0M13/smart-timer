class SmartTimerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._interval = null;
  }

  setConfig(config) {
    if (!config.entity) throw new Error("Please define an entity");
    this._config = {
      entity: config.entity,
      name: config.name || null,
      presets: config.presets || [15, 30, 60, 120],
      show_schedules: config.show_schedules !== false,
    };
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _render() {
    const hass = this._hass;
    const config = this._config;
    if (!hass || !config) return;

    const entity = config.entity;
    const slug = entity.split(".")[1];
    const stateObj = hass.states[entity];
    const isOn = stateObj && !["off", "unavailable", "unknown", "closed", "idle", "docked", "standby"].includes(stateObj.state);

    const timerSensor = hass.states[`sensor.${slug}_time_remaining`];
    const timerActive = hass.states[`binary_sensor.${slug}_timer_active`];
    const autoOff = hass.states[`number.${slug}_auto_off`];
    const nextSched = hass.states[`sensor.${slug}_next_schedule`];

    const remaining = timerSensor ? timerSensor.state : "idle";
    const timerIsActive = timerActive && timerActive.state === "on";
    const timerAction = timerActive?.attributes?.action || timerSensor?.attributes?.action || null;
    const autoOffVal = autoOff ? parseFloat(autoOff.state) || 0 : 0;

    const schedules = nextSched?.attributes?.schedules || [];
    const displayName = config.name || stateObj?.attributes?.friendly_name || slug;

    const root = this.shadowRoot;
    root.innerHTML = `
      <style>
        :host { display: block; }
        .card {
          background: var(--ha-card-background, var(--card-background-color, #fff));
          border-radius: var(--ha-card-border-radius, 12px);
          box-shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0,0,0,.15));
          padding: 16px;
          font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
          color: var(--primary-text-color);
        }
        .header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 12px;
        }
        .name { font-size: 16px; font-weight: 500; }
        .toggle {
          width: 48px; height: 26px;
          border-radius: 13px;
          border: none;
          cursor: pointer;
          position: relative;
          transition: background .2s;
        }
        .toggle.on { background: var(--primary-color, #03a9f4); }
        .toggle.off { background: var(--disabled-color, #bdbdbd); }
        .toggle::after {
          content: '';
          position: absolute;
          top: 3px;
          width: 20px; height: 20px;
          border-radius: 50%;
          background: #fff;
          transition: left .2s;
        }
        .toggle.on::after { left: 25px; }
        .toggle.off::after { left: 3px; }

        .countdown {
          text-align: center;
          padding: 12px 0;
          font-size: 32px;
          font-weight: 300;
          letter-spacing: 2px;
          color: var(--primary-color);
        }
        .countdown.idle { color: var(--secondary-text-color); font-size: 18px; }
        .countdown-action {
          font-size: 12px;
          color: var(--secondary-text-color);
          text-align: center;
          margin-top: -8px;
          margin-bottom: 8px;
        }

        .section-label {
          font-size: 11px;
          font-weight: 500;
          text-transform: uppercase;
          color: var(--secondary-text-color);
          margin: 12px 0 6px;
          letter-spacing: .5px;
        }

        .presets {
          display: flex;
          gap: 6px;
          flex-wrap: wrap;
        }
        .preset-btn {
          flex: 1;
          min-width: 50px;
          padding: 8px 4px;
          border: 1px solid var(--divider-color, #e0e0e0);
          border-radius: 8px;
          background: transparent;
          color: var(--primary-text-color);
          cursor: pointer;
          font-size: 13px;
          text-align: center;
          transition: background .15s, border-color .15s;
        }
        .preset-btn:hover { background: var(--primary-color); color: #fff; border-color: var(--primary-color); }

        .cancel-btn {
          display: block;
          width: 100%;
          padding: 8px;
          margin-top: 8px;
          border: 1px solid var(--error-color, #f44336);
          border-radius: 8px;
          background: transparent;
          color: var(--error-color, #f44336);
          cursor: pointer;
          font-size: 13px;
        }
        .cancel-btn:hover { background: var(--error-color, #f44336); color: #fff; }

        .auto-off-row {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-top: 4px;
        }
        .auto-off-row label { font-size: 13px; flex-shrink: 0; }
        .auto-off-row input {
          flex: 1;
          padding: 6px 8px;
          border: 1px solid var(--divider-color, #e0e0e0);
          border-radius: 6px;
          background: transparent;
          color: var(--primary-text-color);
          font-size: 13px;
          max-width: 80px;
        }
        .auto-off-row span { font-size: 12px; color: var(--secondary-text-color); }

        .schedules-list { margin-top: 4px; }
        .sched-item {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 6px 0;
          border-bottom: 1px solid var(--divider-color, #e0e0e0);
          font-size: 13px;
        }
        .sched-item:last-child { border-bottom: none; }
        .sched-info { display: flex; gap: 8px; align-items: center; }
        .sched-action {
          padding: 2px 6px;
          border-radius: 4px;
          font-size: 11px;
          font-weight: 500;
        }
        .sched-action.on { background: #e8f5e9; color: #2e7d32; }
        .sched-action.off { background: #fce4ec; color: #c62828; }
        .sched-item.disabled { opacity: 0.45; }
        .sched-toggle {
          width: 36px; height: 20px;
          border-radius: 10px;
          border: none;
          cursor: pointer;
          position: relative;
          transition: background .2s;
          flex-shrink: 0;
        }
        .sched-toggle.on { background: var(--primary-color, #03a9f4); }
        .sched-toggle.off { background: var(--disabled-color, #bdbdbd); }
        .sched-toggle::after {
          content: '';
          position: absolute;
          top: 2px;
          width: 16px; height: 16px;
          border-radius: 50%;
          background: #fff;
          transition: left .2s;
        }
        .sched-toggle.on::after { left: 18px; }
        .sched-toggle.off::after { left: 2px; }
        .sched-actions { display: flex; gap: 4px; align-items: center; }
        .sched-del {
          background: none; border: none;
          color: var(--secondary-text-color);
          cursor: pointer; font-size: 16px; padding: 2px 6px;
        }
        .sched-del:hover { color: var(--error-color, #f44336); }

        .add-sched {
          display: flex;
          gap: 6px;
          align-items: center;
          margin-top: 8px;
          flex-wrap: wrap;
        }
        .add-sched select, .add-sched input {
          padding: 6px 8px;
          border: 1px solid var(--divider-color, #e0e0e0);
          border-radius: 6px;
          background: transparent;
          color: var(--primary-text-color);
          font-size: 12px;
        }
        .add-sched-btn {
          padding: 6px 12px;
          border: none;
          border-radius: 6px;
          background: var(--primary-color, #03a9f4);
          color: #fff;
          cursor: pointer;
          font-size: 12px;
        }

        .days-row { display: flex; gap: 3px; margin-top: 4px; }
        .day-chip {
          width: 28px; height: 28px;
          border-radius: 50%;
          border: 1px solid var(--divider-color, #e0e0e0);
          background: transparent;
          color: var(--primary-text-color);
          cursor: pointer;
          font-size: 10px;
          display: flex; align-items: center; justify-content: center;
        }
        .day-chip.sel {
          background: var(--primary-color, #03a9f4);
          color: #fff;
          border-color: var(--primary-color, #03a9f4);
        }
      </style>
      <div class="card">
        <div class="header">
          <span class="name">${displayName}</span>
          <button class="toggle ${isOn ? 'on' : 'off'}" id="toggle"></button>
        </div>

        <div class="countdown ${timerIsActive ? '' : 'idle'}" id="countdown">
          ${timerIsActive ? remaining : 'No timer active'}
        </div>
        ${timerIsActive && timerAction ? `<div class="countdown-action">will ${timerAction === 'turn_on' ? 'turn ON' : 'turn OFF'}</div>` : ''}
        ${timerIsActive ? `<button class="cancel-btn" id="cancel">Cancel Timer</button>` : ''}

        <div class="section-label">Turn Off In</div>
        <div class="presets" id="presets-off"></div>

        <div class="section-label">Turn On In</div>
        <div class="presets" id="presets-on"></div>

        <div class="section-label">Auto-Off</div>
        <div class="auto-off-row">
          <label>Duration</label>
          <input type="number" id="auto-off" min="0" max="1440" step="1" value="${autoOffVal}">
          <span>min (0 = off)</span>
        </div>

        ${config.show_schedules ? `
          <div class="section-label">Schedules</div>
          <div class="schedules-list" id="schedules"></div>
          <div class="add-sched">
            <input type="time" id="sched-time" value="08:00">
            <select id="sched-action">
              <option value="turn_on">ON</option>
              <option value="turn_off">OFF</option>
            </select>
            <button class="add-sched-btn" id="add-sched">+ Add</button>
          </div>
          <div class="days-row" id="days-row"></div>
        ` : ''}
      </div>
    `;

    // Toggle
    root.getElementById("toggle").addEventListener("click", () => {
      this._hass.callService("homeassistant", isOn ? "turn_off" : "turn_on", { entity_id: entity });
    });

    // Cancel
    const cancelBtn = root.getElementById("cancel");
    if (cancelBtn) {
      cancelBtn.addEventListener("click", () => {
        this._hass.callService("smart_timer", "cancel_timer", { entity_id: entity });
      });
    }

    // Presets — Turn Off
    const presetsOff = root.getElementById("presets-off");
    for (const min of config.presets) {
      const btn = document.createElement("button");
      btn.className = "preset-btn";
      btn.textContent = min >= 60 ? `${min / 60}h` : `${min}m`;
      btn.addEventListener("click", () => {
        this._hass.callService("smart_timer", "start_timer", {
          entity_id: entity, minutes: min, action: "turn_off"
        });
      });
      presetsOff.appendChild(btn);
    }

    // Presets — Turn On
    const presetsOn = root.getElementById("presets-on");
    for (const min of config.presets) {
      const btn = document.createElement("button");
      btn.className = "preset-btn";
      btn.textContent = min >= 60 ? `${min / 60}h` : `${min}m`;
      btn.addEventListener("click", () => {
        this._hass.callService("smart_timer", "start_timer", {
          entity_id: entity, minutes: min, action: "turn_on"
        });
      });
      presetsOn.appendChild(btn);
    }

    // Auto-off
    root.getElementById("auto-off").addEventListener("change", (e) => {
      const val = parseFloat(e.target.value) || 0;
      this._hass.callService("number", "set_value", {
        entity_id: `number.${slug}_auto_off`, value: val
      });
    });

    // Schedules
    if (config.show_schedules) {
      const schedList = root.getElementById("schedules");
      for (const s of schedules) {
        const item = document.createElement("div");
        const isEnabled = s.enabled !== false;
        item.className = `sched-item${isEnabled ? '' : ' disabled'}`;
        const actionClass = s.action === "turn_on" ? "on" : "off";
        item.innerHTML = `
          <div class="sched-info">
            <span class="sched-action ${actionClass}">${s.action === 'turn_on' ? 'ON' : 'OFF'}</span>
            <span>${s.time}</span>
            <span style="color:var(--secondary-text-color);font-size:11px">${s.days}</span>
          </div>
          <div class="sched-actions">
            <button class="sched-toggle ${isEnabled ? 'on' : 'off'}" data-id="${s.id}"></button>
            <button class="sched-del" data-id="${s.id}">&times;</button>
          </div>
        `;
        schedList.appendChild(item);
      }
      schedList.querySelectorAll(".sched-toggle").forEach(btn => {
        btn.addEventListener("click", () => {
          this._hass.callService("smart_timer", "toggle_schedule", {
            entity_id: entity, schedule_id: btn.dataset.id
          });
        });
      });
      schedList.querySelectorAll(".sched-del").forEach(btn => {
        btn.addEventListener("click", () => {
          this._hass.callService("smart_timer", "remove_schedule", {
            entity_id: entity, schedule_id: btn.dataset.id
          });
        });
      });

      // Day chips
      const daysRow = root.getElementById("days-row");
      const dayLabels = ["M", "T", "W", "T", "F", "S", "S"];
      this._selectedDays = this._selectedDays || new Set();
      dayLabels.forEach((label, i) => {
        const chip = document.createElement("button");
        chip.className = `day-chip ${this._selectedDays.has(i) ? 'sel' : ''}`;
        chip.textContent = label;
        chip.addEventListener("click", () => {
          if (this._selectedDays.has(i)) this._selectedDays.delete(i);
          else this._selectedDays.add(i);
          chip.classList.toggle("sel");
        });
        daysRow.appendChild(chip);
      });

      // Add schedule
      root.getElementById("add-sched").addEventListener("click", () => {
        const time = root.getElementById("sched-time").value;
        const action = root.getElementById("sched-action").value;
        const days = this._selectedDays.size > 0 ? Array.from(this._selectedDays).map(String) : [];
        this._hass.callService("smart_timer", "add_schedule", {
          entity_id: entity, action, time, days
        });
        this._selectedDays = new Set();
      });
    }

    this._startCountdown(timerIsActive);
  }

  _startCountdown(active) {
    if (this._interval) clearInterval(this._interval);
    if (!active) return;
    this._interval = setInterval(() => {
      const el = this.shadowRoot?.getElementById("countdown");
      if (!el || !this._hass) return;
      const slug = this._config.entity.split(".")[1];
      const sensor = this._hass.states[`sensor.${slug}_time_remaining`];
      if (sensor && sensor.state !== "idle") {
        el.textContent = sensor.state;
      } else {
        clearInterval(this._interval);
        this._interval = null;
      }
    }, 1000);
  }

  disconnectedCallback() {
    if (this._interval) {
      clearInterval(this._interval);
      this._interval = null;
    }
  }

  getCardSize() { return 4; }

  static getStubConfig() {
    return { entity: "", presets: [15, 30, 60, 120] };
  }
}

customElements.define("smart-timer-card", SmartTimerCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "smart-timer-card",
  name: "Smart Timer Card",
  description: "Timer controls and schedules for any device",
});
