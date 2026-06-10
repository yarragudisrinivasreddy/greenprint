/* GreenPrint client — vanilla JS, no inline handlers (CSP-safe). */
(function () {
  "use strict";

  var sessionId = null;

  function language() {
    return document.getElementById("language-select").value;
  }

  function setBusy(regionId, message) {
    document.getElementById(regionId).innerHTML = "<p>" + message + "</p>";
  }

  function postJson(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (response) { return response.json(); });
  }

  function renderEstimates(data) {
    var region = document.getElementById("result-region");
    if (data.status !== "ok") {
      region.innerHTML = "<p role='alert'>" + (data.message || "Something went wrong.") + "</p>";
      return;
    }
    sessionId = data.session_id;
    var html = "";
    data.estimates.forEach(function (estimate) {
      html += "<div class='estimate-row'><span>" + estimate.label +
        " — " + estimate.quantity + " " + estimate.unit + "</span><span>" +
        estimate.emission_kg_co2e + " kgCO2e</span></div>";
    });
    html += "<p class='total-row'>Total: " + data.total_kg_co2e + " kgCO2e</p>";
    if (data.eco_tip) {
      html += "<p class='eco-tip'>" + data.eco_tip + "</p>";
    }
    region.innerHTML = html;
  }

  function renderInsights(data) {
    var region = document.getElementById("insights-region");
    if (data.status !== "ok") {
      region.innerHTML = "<p role='alert'>" + (data.message || "Could not load insights.") + "</p>";
      return;
    }
    var html = "<p>EcoScore: <span class='score-badge'>" + data.eco_score.score +
      "</span> / 100 · Streak: " + data.eco_score.streak_days + " days</p>" +
      "<p>" + data.eco_score.explanation + "</p>" + data.weekly_trend_svg;
    if (data.top_actions && data.top_actions.length) {
      html += "<h3>Top actions for you</h3>";
      data.top_actions.forEach(function (action) {
        html += "<div class='estimate-row'><span>" + action.action + "</span><span>" +
          action.weekly_saving_kg + " kg/wk · " + action.annual_saving_kg + " kg/yr</span></div>";
      });
    }
    region.innerHTML = html;
  }

  function renderSimulation(data) {
    var region = document.getElementById("simulate-region");
    if (data.status !== "ok") {
      region.innerHTML = "<p role='alert'>" + (data.message || "Could not simulate.") + "</p>";
      return;
    }
    region.innerHTML = "<p class='total-row'>Weekly saving: " + data.weekly_saving_kg +
      " kgCO2e (" + data.annual_saving_kg + " kg/year)</p>" +
      "<p>Current weekly: " + data.current_weekly_kg + " → Projected: " +
      data.projected_weekly_kg + " kgCO2e</p>" +
      (data.narrative ? "<p class='eco-tip'>" + data.narrative + "</p>" : "");
  }

  function loadChips() {
    fetch("/api/factors").then(function (r) { return r.json(); }).then(function (data) {
      if (data.status !== "ok") { return; }
      var row = document.getElementById("chip-row");
      var preferred = [
        "transport.car_petrol_km", "transport.metro_km", "transport.bus_km",
        "energy.ac_hour", "food.meal_nonveg", "food.meal_veg", "shopping.parcel_delivery"
      ];
      preferred.forEach(function (key) {
        var factor = data.factors[key];
        if (!factor) { return; }
        var chip = document.createElement("button");
        chip.type = "button";
        chip.className = "chip";
        chip.textContent = factor.label;
        chip.setAttribute("aria-label", "Add one " + factor.unit + " of " + factor.label);
        chip.addEventListener("click", function () {
          setBusy("result-region", "Estimating…");
          postJson("/api/track", {
            session_id: sessionId,
            language: language(),
            activities: [{ factor_key: key, quantity: 1 }]
          }).then(renderEstimates);
        });
        row.appendChild(chip);
      });
    });
  }

  document.getElementById("track-btn").addEventListener("click", function () {
    var text = document.getElementById("activity-text").value.trim();
    if (!text) {
      document.getElementById("result-region").innerHTML =
        "<p role='alert'>Describe at least one activity first.</p>";
      return;
    }
    setBusy("result-region", "Estimating…");
    postJson("/api/track", { text: text, language: language(), session_id: sessionId })
      .then(renderEstimates);
  });

  document.getElementById("insights-btn").addEventListener("click", function () {
    if (!sessionId) {
      document.getElementById("insights-region").innerHTML =
        "<p role='alert'>Track at least one activity first.</p>";
      return;
    }
    setBusy("insights-region", "Composing insights…");
    fetch("/api/insights?session_id=" + encodeURIComponent(sessionId) +
      "&language=" + encodeURIComponent(language()))
      .then(function (r) { return r.json(); })
      .then(renderInsights);
  });

  document.getElementById("simulate-btn").addEventListener("click", function () {
    var scenario = document.getElementById("scenario-text").value.trim();
    if (!scenario) {
      document.getElementById("simulate-region").innerHTML =
        "<p role='alert'>Describe a change to simulate.</p>";
      return;
    }
    setBusy("simulate-region", "Projecting…");
    postJson("/api/simulate", { scenario: scenario, language: language(), session_id: sessionId })
      .then(renderSimulation);
  });

  loadChips();
})();
