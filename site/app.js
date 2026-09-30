// Forecasting the Future: the project page's charts, drawn from data.json.
// data.json is written by `forecast page-assets` from the committed record; nothing
// here computes a result, it only draws one. Colours come from CSS classes, so the
// charts follow the reader's light or dark setting without redrawing.

(function () {
  "use strict";

  var SVG = "http://www.w3.org/2000/svg";
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var NAMES = { blend: "Blend (ships)", model: "Regime model", chain: "Condition chain", average: "Historical average" };

  function el(tag, attributes, parent, text) {
    var node = document.createElementNS(SVG, tag);
    for (var key in attributes) node.setAttribute(key, attributes[key]);
    if (text !== undefined) node.textContent = text;
    if (parent) parent.appendChild(node);
    return node;
  }

  function signed(value, digits) {
    if (value === null || value === undefined) return "–";
    var fixed = Math.abs(value).toFixed(digits);
    if (Number(fixed) === 0) return "+" + fixed;
    return (value < 0 ? "−" : "+") + fixed;
  }

  function percent(value) {
    return value === null || value === undefined ? "–" : (100 * value).toFixed(0) + "%";
  }

  function interval(low, high) {
    return "[" + signed(low, 3) + ", " + signed(high, 3) + "]";
  }

  function monthName(text) {
    var parts = text.split("-");
    var names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    return names[Number(parts[1]) - 1] + " " + parts[0];
  }

  function path(points) {
    var d = "";
    var pen = false;
    points.forEach(function (point) {
      if (point === null) { pen = false; return; }
      d += (pen ? "L" : "M") + point[0].toFixed(1) + "," + point[1].toFixed(1);
      pen = true;
    });
    return d;
  }

  function drawIn(node) {
    if (reduceMotion) return;
    var length = node.getTotalLength ? node.getTotalLength() : 0;
    if (!length) return;
    node.style.setProperty("--length", length.toFixed(0));
    node.classList.add("draw");
  }

  function span(parent, className, text) {
    var node = document.createElement("span");
    if (className) node.className = className;
    node.textContent = text;
    parent.appendChild(node);
    return node;
  }

  function readoutItem(box, key, label, value, extra) {
    var item = document.createElement("span");
    var swatch = document.createElement("span");
    swatch.className = "key " + key;
    item.appendChild(swatch);
    item.appendChild(document.createTextNode(label + " "));
    var strong = document.createElement("strong");
    strong.textContent = value;
    item.appendChild(strong);
    if (extra) item.appendChild(document.createTextNode(" " + extra));
    box.appendChild(item);
  }

  function pointerToViewBox(svg, event) {
    var point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    return point.matrixTransform(svg.getScreenCTM().inverse());
  }

  // ------------------------------------------------------- skill at every horizon

  function horizonChart(data) {
    var host = document.getElementById("horizon-chart");
    var slider = document.getElementById("horizon-month");
    var readout = document.getElementById("horizon-readout");
    var W = 1000, H = 420, L = 58, R = 18, T = 26, B = 46;
    var yMin = -0.42, yMax = 0.65;
    var x = function (m) { return L + (m - 1) / 119 * (W - L - R); };
    var y = function (v) { return T + (yMax - v) / (yMax - yMin) * (H - T - B); };
    var clampY = function (v) { return y(Math.max(yMin, Math.min(yMax, v))); };
    var order = ["model", "chain", "blend"];
    var first = true;

    function render() {
      host.textContent = "";
      var svg = el("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "Skill against the historical average at every horizon from 1 to 120 months" }, host);
      el("rect", { x: x(data.informative_through + 0.5), y: T, width: x(120) - x(data.informative_through + 0.5), height: H - T - B, "class": "shade" }, svg);
      el("text", { x: (x(data.informative_through) + x(120)) / 2, y: T + 16, "text-anchor": "middle", "class": "note" }, svg, "too few independent observations to read");
      for (var v = -0.4; v <= 0.61; v += 0.1) {
        var value = Math.round(v * 10) / 10;
        el("line", { x1: L, x2: W - R, y1: y(value), y2: y(value), "class": value === 0 ? "zero" : "grid" }, svg);
        el("text", { x: L - 10, y: y(value) + 4, "text-anchor": "end", "class": "tick" }, svg, signed(value, 1));
      }
      [1, 12, 24, 36, 48, 60, 72, 84, 96, 108, 120].forEach(function (m) {
        el("text", { x: x(m), y: H - B + 20, "text-anchor": "middle", "class": "tick" }, svg, m);
      });
      el("text", { x: (L + W - R) / 2, y: H - 6, "text-anchor": "middle", "class": "axis-label" }, svg, "forecast horizon in months");
      order.forEach(function (key) {
        if (!document.getElementById("band-" + key).checked) return;
        var rows = data.curves[key];
        var upper = rows.map(function (r) { return x(r[0]).toFixed(1) + "," + clampY(r[3]).toFixed(1); });
        var lower = rows.slice().reverse().map(function (r) { return x(r[0]).toFixed(1) + "," + clampY(r[2]).toFixed(1); });
        el("polygon", { points: upper.concat(lower).join(" "), "class": "band " + key }, svg);
      });
      order.forEach(function (key) {
        var line = el("path", { d: path(data.curves[key].map(function (r) { return [x(r[0]), y(r[1])]; })), "class": "line " + key }, svg);
        if (first) drawIn(line);
      });
      [["model", data.horizons.model], ["blend", data.horizons.blend]].forEach(function (pair) {
        el("line", { x1: x(pair[1]), x2: x(pair[1]), y1: T + 30, y2: H - B, "class": "marker " + pair[0] }, svg);
        el("text", { x: x(pair[1]) + 5, y: T + 42, "class": "marker-label " + pair[0] }, svg, pair[1] + " months");
      });
      var month = Number(slider.value);
      el("line", { x1: x(month), x2: x(month), y1: T, y2: H - B, "class": "cursor" }, svg);
      order.forEach(function (key) {
        var r = data.curves[key][month - 1];
        el("circle", { cx: x(month), cy: y(r[1]), r: 4.5, "class": "dot " + key }, svg);
      });
      var hit = el("rect", { x: L, y: T, width: W - L - R, height: H - T - B, fill: "transparent" }, svg);
      hit.style.cursor = "crosshair";
      var pick = function (event) {
        var p = pointerToViewBox(svg, event);
        var m = Math.max(1, Math.min(120, Math.round(1 + (p.x - L) / (W - L - R) * 119)));
        if (m !== Number(slider.value)) { slider.value = m; render(); }
      };
      hit.addEventListener("pointermove", pick);
      hit.addEventListener("pointerdown", pick);
      first = false;
      update(month);
    }

    function update(month) {
      readout.textContent = "";
      var label = month === 12 ? "one year" : month === 60 ? "five years" : month === 120 ? "ten years" : null;
      span(readout, "when", "Month " + month + (label ? " · " + label : ""));
      ["blend", "chain", "model"].forEach(function (key) {
        var r = data.curves[key][month - 1];
        readoutItem(readout, key, NAMES[key], signed(r[1], 3), interval(r[2], r[3]));
      });
    }

    slider.addEventListener("input", render);
    ["blend", "chain", "model"].forEach(function (key) {
      document.getElementById("band-" + key).addEventListener("change", render);
    });
    render();
  }

  // --------------------------------------------------------- blend minus chain

  function gapChart(data) {
    var host = document.getElementById("gap-chart");
    var readout = document.getElementById("gap-readout");
    var rows = data.blend_minus_chain;
    var W = 620, H = 300, L = 54, R = 14, T = 16, B = 42;
    var yMin = -0.165, yMax = 0.08;
    var x = function (m) { return L + (m - 1) / 119 * (W - L - R); };
    var y = function (v) { return T + (yMax - v) / (yMax - yMin) * (H - T - B); };
    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "Blend minus condition chain skill at every horizon" }, host);
    el("rect", { x: x(data.informative_through + 0.5), y: T, width: x(120) - x(data.informative_through + 0.5), height: H - T - B, "class": "shade" }, svg);
    [-0.15, -0.1, -0.05, 0, 0.05].forEach(function (v) {
      el("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), "class": v === 0 ? "zero" : "grid" }, svg);
      el("text", { x: L - 8, y: y(v) + 4, "text-anchor": "end", "class": "tick" }, svg, signed(v, 2));
    });
    [1, 24, 48, 72, 96, 120].forEach(function (m) {
      el("text", { x: x(m), y: H - B + 18, "text-anchor": "middle", "class": "tick" }, svg, m);
    });
    el("text", { x: (L + W - R) / 2, y: H - 6, "text-anchor": "middle", "class": "axis-label" }, svg, "horizon in months");
    var upper = rows.map(function (r) { return x(r[0]).toFixed(1) + "," + y(Math.min(r[3], yMax)).toFixed(1); });
    var lower = rows.slice().reverse().map(function (r) { return x(r[0]).toFixed(1) + "," + y(Math.max(r[2], yMin)).toFixed(1); });
    el("polygon", { points: upper.concat(lower).join(" "), "class": "band blend" }, svg);
    rows.forEach(function (r) {
      if (r[3] < 0) el("rect", { x: x(r[0]) - 1.6, y: H - B - 8, width: 3.2, height: 8, "class": "tickmark" }, svg);
    });
    drawIn(el("path", { d: path(rows.map(function (r) { return [x(r[0]), y(r[1])]; })), "class": "line blend" }, svg));
    var cursor = el("line", { x1: 0, x2: 0, y1: T, y2: H - B, "class": "cursor", visibility: "hidden" }, svg);
    function update(m) {
      var r = rows[m - 1];
      cursor.setAttribute("x1", x(m)); cursor.setAttribute("x2", x(m)); cursor.setAttribute("visibility", "visible");
      readout.textContent = "";
      span(readout, "when", "Month " + m);
      readoutItem(readout, "blend", "blend − chain", signed(r[1], 3), interval(r[2], r[3]));
    }
    var hit = el("rect", { x: L, y: T, width: W - L - R, height: H - T - B, fill: "transparent" }, svg);
    hit.addEventListener("pointermove", function (event) {
      var p = pointerToViewBox(svg, event);
      update(Math.max(1, Math.min(120, Math.round(1 + (p.x - L) / (W - L - R) * 119))));
    });
    update(12);
  }

  // ------------------------------------------------------ one year, by question

  function questionChart(data) {
    var host = document.getElementById("question-chart");
    var readout = document.getElementById("question-readout");
    var rows = data.by_question;
    var W = 620, rowH = 27, T = 10, B = 40, L = 250, R = 16;
    var H = T + rows.length * rowH + B;
    var xMin = -0.35, xMax = 0.75;
    var x = function (v) { return L + (v - xMin) / (xMax - xMin) * (W - L - R); };
    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "One-year skill by question for the three forecasters" }, host);
    [-0.2, 0, 0.2, 0.4, 0.6].forEach(function (v) {
      el("line", { x1: x(v), x2: x(v), y1: T, y2: H - B, "class": v === 0 ? "zero" : "grid" }, svg);
      el("text", { x: x(v), y: H - B + 18, "text-anchor": "middle", "class": "tick" }, svg, signed(v, 1));
    });
    el("text", { x: (L + W - R) / 2, y: H - 6, "text-anchor": "middle", "class": "axis-label" }, svg, "Brier skill against the historical average");
    rows.forEach(function (row, index) {
      var cy = T + index * rowH + rowH / 2;
      el("line", { x1: L, x2: W - R, y1: cy, y2: cy, "class": "row-rule" }, svg);
      el("text", { x: L - 10, y: cy + 4, "text-anchor": "end", "class": "row-label" }, svg, row.question);
      [["model", -5], ["chain", 0], ["blend", 5]].forEach(function (pair) {
        if (row[pair[0]] === null) return;
        el("circle", { cx: x(row[pair[0]]), cy: cy + pair[1], r: 5, "class": "dot " + pair[0] }, svg);
      });
      var hit = el("rect", { x: 0, y: cy - rowH / 2, width: W, height: rowH, fill: "transparent" }, svg);
      hit.addEventListener("pointerenter", function () { show(row); });
    });
    function show(row) {
      readout.textContent = "";
      span(readout, "when", row.question);
      ["blend", "chain", "model"].forEach(function (key) { readoutItem(readout, key, NAMES[key], signed(row[key], 3)); });
    }
    show(rows[0]);
  }

  // ----------------------------------------------------------- the timelines

  function timelineChart(data) {
    var host = document.getElementById("timeline-chart");
    var select = document.getElementById("question-select");
    var readout = document.getElementById("timeline-readout");
    var dates = data.dates;
    var W = 1000, H = 360, L = 50, R = 16, T = 14, B = 40;
    var n = dates.length;
    var x = function (i) { return L + i / (n - 1) * (W - L - R); };
    var y = function (v) { return T + (1 - v) * (H - T - B); };
    var step = (W - L - R) / (n - 1);

    data.shipped.forEach(function (row) {
      var option = document.createElement("option");
      option.value = row.indicator;
      option.textContent = row.short;
      select.appendChild(option);
    });
    select.value = "federal_funds_rate_below_one_percent_within_horizon";

    var chosen = null;
    function render(animate) {
      var series = data.timelines[select.value];
      host.textContent = "";
      var svg = el("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "One-year probabilities through history for " + series.question }, host);
      // One block per run of consecutive dates that resolved yes, so no seams show between months.
      var start = null;
      series.outcome.concat([null]).forEach(function (outcome, i) {
        if (outcome === 1 && start === null) start = i;
        if (outcome !== 1 && start !== null) {
          var left = Math.max(L, x(start) - step / 2), right = Math.min(W - R, x(i - 1) + step / 2);
          el("rect", { x: left, y: T, width: right - left, height: H - T - B, "class": "happened" }, svg);
          start = null;
        }
      });
      [0, 0.25, 0.5, 0.75, 1].forEach(function (v) {
        el("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), "class": "grid" }, svg);
        el("text", { x: L - 8, y: y(v) + 4, "text-anchor": "end", "class": "tick" }, svg, (100 * v).toFixed(0) + "%");
      });
      dates.forEach(function (date, i) {
        var year = Number(date.slice(0, 4));
        if (date.slice(5) === "01" && year % 4 === 0) {
          el("text", { x: x(i), y: H - B + 18, "text-anchor": "middle", "class": "tick" }, svg, year);
        }
      });
      var keys = ["average", "chain", "model", "blend"].filter(function (key) {
        return key === "blend" || document.getElementById("show-" + key).checked;
      });
      keys.forEach(function (key) {
        var line = el("path", {
          d: path(series[key].map(function (v, i) { return v === null ? null : [x(i), y(v)]; })),
          "class": "line " + key
        }, svg);
        if (animate && key === "blend") drawIn(line);
      });
      var cursor = el("line", { x1: 0, x2: 0, y1: T, y2: H - B, "class": "cursor", visibility: "hidden" }, svg);
      var hit = el("rect", { x: L, y: T, width: W - L - R, height: H - T - B, fill: "transparent" }, svg);
      hit.addEventListener("pointermove", function (event) {
        var p = pointerToViewBox(svg, event);
        chosen = Math.max(0, Math.min(n - 1, Math.round((p.x - L) / step)));
        cursor.setAttribute("x1", x(chosen)); cursor.setAttribute("x2", x(chosen)); cursor.setAttribute("visibility", "visible");
        update(series, chosen);
      });
      update(series, chosen === null ? n - 1 : chosen);
    }

    function update(series, i) {
      readout.textContent = "";
      span(readout, "when", monthName(dates[i]));
      readoutItem(readout, "blend", "blend", percent(series.blend[i]));
      if (document.getElementById("show-model").checked) readoutItem(readout, "model", "model", percent(series.model[i]));
      if (document.getElementById("show-chain").checked) readoutItem(readout, "chain", "chain", percent(series.chain[i]));
      if (document.getElementById("show-average").checked) readoutItem(readout, "average", "average", percent(series.average[i]));
      var outcome = series.outcome[i];
      span(readout, null, outcome === null ? "outcome not yet known" : outcome === 1 ? "it happened within the year" : "it did not happen within the year");
    }

    select.addEventListener("change", function () { chosen = null; render(true); });
    ["model", "chain", "average"].forEach(function (key) {
      document.getElementById("show-" + key).addEventListener("change", function () { render(false); });
    });
    render(true);
  }

  // ------------------------------------------------------------ today's table

  function forecastTable(data) {
    var table = document.getElementById("forecast-table");
    var head = document.createElement("thead");
    head.innerHTML = "<tr><th>Question</th><th>1 year (blend)</th><th>5 years (average)</th><th>10 years (average)</th></tr>";
    table.appendChild(head);
    var body = document.createElement("tbody");
    function cell(value, kind, halves) {
      var td = document.createElement("td");
      td.className = "num";
      td.appendChild(document.createTextNode(percent(value)));
      var bar = document.createElement("span");
      bar.className = "bar" + (kind === "average" ? " average" : "");
      var fill = document.createElement("span");
      fill.style.width = (100 * value).toFixed(1) + "%";
      bar.appendChild(fill);
      td.appendChild(bar);
      if (halves) {
        var note = document.createElement("span");
        note.className = "halves";
        note.textContent = halves;
        td.appendChild(note);
      }
      return td;
    }
    data.shipped.forEach(function (row) {
      var tr = document.createElement("tr");
      var question = document.createElement("td");
      span(question, "short", row.short);
      span(question, "long", row.question);
      tr.appendChild(question);
      tr.appendChild(cell(row.one_year, "blend", "model " + percent(row.model_half) + " · chain " + percent(row.chain_half)));
      tr.appendChild(cell(row.five_years, "average"));
      tr.appendChild(cell(row.ten_years, "average"));
      body.appendChild(tr);
    });
    table.appendChild(body);
  }

  // ------------------------------------------------------------------ the rest

  function bind(data) {
    var binds = {
      blendHorizon: data.horizons.blend,
      modelHorizon: data.horizons.model,
      forecastDates: data.forecast_dates
    };
    document.querySelectorAll("[data-bind]").forEach(function (node) {
      var value = binds[node.getAttribute("data-bind")];
      if (value === undefined) return;
      var small = node.querySelector("small");
      node.textContent = String(value);
      if (small) node.appendChild(small);
    });
    var configuration = document.getElementById("configuration");
    if (configuration) configuration.textContent = data.configuration;
  }

  function copyButton() {
    var button = document.getElementById("copy-bibtex");
    if (!button) return;
    button.addEventListener("click", function () {
      var text = document.getElementById("bibtex").textContent.replace(/^Copy/, "");
      var done = function () { button.textContent = "Copied"; setTimeout(function () { button.textContent = "Copy"; }, 1600); };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () { button.textContent = "Select and copy"; });
      } else {
        button.textContent = "Select and copy";
      }
    });
  }

  fetch("data.json")
    .then(function (response) {
      if (!response.ok) throw new Error("data.json: " + response.status);
      return response.json();
    })
    .then(function (data) {
      bind(data);
      horizonChart(data);
      gapChart(data);
      questionChart(data);
      timelineChart(data);
      forecastTable(data);
    })
    .catch(function (error) {
      document.querySelectorAll(".chart").forEach(function (node) {
        node.textContent = "The chart data could not be loaded (" + error.message + "). Serve the page over HTTP rather than opening the file directly.";
      });
    });
  copyButton();
})();
