/* One-page application.
 *
 * It displays approved results and filters approved pre-aggregations. It never
 * recalculates a trusted number: KPI values come from dashboard.json exactly as
 * the engine proved them, and a filtered figure is a SUM OF PRE-AGGREGATED
 * CELLS - never a formula re-implemented here. Ratios divide two summed parts
 * after filtering, which is the same arithmetic the engine did.
 */
(function () {
  "use strict";

  var KEY = new URLSearchParams(window.location.search).get("k") || "";
  /* A saved copy carries its data inside it: no server, no fetching, no
   * processing - just the result, exactly as it was published. */
  var SAVED = window.__DASHBOARD__ || null;
  var SERIES_SLOTS = 4;   /* validated palette: a fifth series folds into "Other" */

  var state = {
    lang: "en", theme: null, data: null, dashboard: null, polling: null,
    userChoseLanguage: false, filters: null, tables: {}, views: {}
  };

  var T = {
    en: {
      skip: "Skip to content", print: "Print", theme: "Dark", themeLight: "Light",
      saveCopy: "Save a copy",
      process: "Process",
      filesHeading: "1. Add your files", resultHeading: "2. Your result",
      proofHeading: "3. Proof the numbers are right", insightsHeading: "Highlights",
      attentionHeading: "Rows needing attention", historyHeading: "Previous runs",
      dropzone: "Drag your Excel files here, or press to choose them",
      technicalDetail: "Technical detail (for support)", download: "Download as CSV",
      whereFrom: "Where did the data come from?", emptyHeading: "No result yet",
      emptyBody: "Add your files above and press Process.",
      expected: "This report expects: ", noFiles: "No files added yet.",
      needFiles: "Add at least one file first.", working: "Working…",
      rowsRead: "Rows read", rowsAccepted: "Rows used", rowsAttention: "Rows needing attention",
      rowsScope: "Rows out of scope", finished: "Finished", remove: "Remove",
      safe: "Your previous results were not changed.",
      check: "Check", expectedCol: "Expected", actual: "Actual", difference: "Difference",
      status: "Status", file: "File", row: "Row", reason: "Reason",
      when: "When", used: "Rows used", message: "Result",
      attentionNote: "These rows were not used in the totals. Fix them in the source file and process again.",
      source: "Source",
      idle: "Ready", footer: "Everything runs on this computer. Nothing is sent anywhere.",
      from: "From", to: "To", all: "All", reset: "Reset filters",
      showingAll: "Showing everything.", showing: "Showing ",
      of: " of ", periodsWord: " periods", vsPrevious: "vs previous period",
      noPrevious: "no earlier period to compare", wholePeriod: "whole report, not filtered",
      tableView: "Table", chartView: "Chart", search: "Search", noData: "Nothing matches these filters.",
      other: "Other", total: "Total", latest: "Latest", last3: "Last 3", allPeriods: "All periods",
      decisionVerified: "Verified signal", confidenceHigh: "High", confidenceReview: "Review", sourceCurrent: "Current"
    },
    ar: {
      skip: "تخطي إلى المحتوى", print: "طباعة", theme: "داكن", themeLight: "فاتح",
      saveCopy: "حفظ نسخة",
      process: "معالجة",
      filesHeading: "١. أضف ملفاتك", resultHeading: "٢. النتيجة",
      proofHeading: "٣. إثبات صحة الأرقام", insightsHeading: "أبرز النقاط",
      attentionHeading: "صفوف تحتاج مراجعة", historyHeading: "التشغيلات السابقة",
      dropzone: "اسحب ملفات إكسل هنا، أو اضغط لاختيارها",
      technicalDetail: "تفاصيل فنية (للدعم)", download: "تنزيل CSV",
      whereFrom: "من أين جاءت البيانات؟", emptyHeading: "لا توجد نتيجة بعد",
      emptyBody: "أضف ملفاتك بالأعلى ثم اضغط معالجة.",
      expected: "هذا التقرير يتوقع: ", noFiles: "لم تتم إضافة ملفات بعد.",
      needFiles: "أضف ملفاً واحداً على الأقل.", working: "جارٍ العمل…",
      rowsRead: "الصفوف المقروءة", rowsAccepted: "الصفوف المستخدمة",
      rowsAttention: "صفوف تحتاج مراجعة", rowsScope: "صفوف خارج النطاق",
      finished: "انتهى", remove: "إزالة",
      safe: "لم تتغير نتائجك السابقة.",
      check: "الفحص", expectedCol: "المتوقع", actual: "الفعلي", difference: "الفرق",
      status: "الحالة", file: "الملف", row: "الصف", reason: "السبب",
      when: "الوقت", used: "الصفوف المستخدمة", message: "النتيجة",
      attentionNote: "لم تُستخدم هذه الصفوف في المجاميع. صححها في الملف المصدر ثم أعد المعالجة.",
      source: "المصدر",
      idle: "جاهز", footer: "كل شيء يعمل على هذا الجهاز. لا يتم إرسال أي شيء.",
      from: "من", to: "إلى", all: "الكل", reset: "إعادة ضبط عوامل التصفية",
      showingAll: "عرض كل البيانات.", showing: "عرض ",
      of: " من ", periodsWord: " فترات", vsPrevious: "مقارنة بالفترة السابقة",
      noPrevious: "لا توجد فترة سابقة للمقارنة", wholePeriod: "التقرير كامل، بدون تصفية",
      tableView: "جدول", chartView: "رسم", search: "بحث",
      noData: "لا توجد بيانات مطابقة.", other: "أخرى", total: "الإجمالي", latest: "الأحدث", last3: "آخر ٣", allPeriods: "كل الفترات",
      decisionVerified: "إشارة موثقة", confidenceHigh: "مرتفع", confidenceReview: "يحتاج مراجعة", sourceCurrent: "حديث"
    }
  };

  function t(key) { return (T[state.lang] && T[state.lang][key]) || T.en[key] || key; }
  function $(id) { return document.getElementById(id); }
  function clear(node) { while (node.firstChild) { node.removeChild(node.firstChild); } }

  /* A page in Arabic still shows English text - a metric title, a file name, a
   * message the engine wrote. dir="auto" lets the browser decide the direction
   * of each individual string, so a full stop never jumps to the wrong end. */
  function setText(node, text) {
    node.textContent = text === null || text === undefined ? "" : String(text);
    node.setAttribute("dir", "auto");
    return node;
  }
  function _set(id, text) { return setText($(id), text); }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (text !== undefined && text !== null) { setText(node, text); }
    return node;
  }

  function svgEl(tag, attributes) {
    var node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.keys(attributes || {}).forEach(function (name) {
      node.setAttribute(name, String(attributes[name]));
    });
    return node;
  }

  function api(path, options) {
    var separator = path.indexOf("?") === -1 ? "?" : "&";
    return fetch(path + separator + "k=" + encodeURIComponent(KEY), options || {})
      .then(function (response) {
        if (!response.ok && response.status !== 409) { throw new Error("HTTP " + response.status); }
        return response.json();
      });
  }

  /* ---------------- formatting (display only) ---------------- */
  function locale() { return state.lang === "ar" ? "ar-EG" : "en-US"; }

  function formatValue(value, format, unit) {
    if (value === null || value === undefined || (typeof value === "number" && !isFinite(value))) {
      return "—";
    }
    var text;
    if (format === "money") {
      text = Number(value).toLocaleString(locale(), { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    } else if (format === "integer") {
      text = Number(value).toLocaleString(locale(), { maximumFractionDigits: 0 });
    } else if (format === "percent") {
      text = Number(value).toLocaleString(locale(), { maximumFractionDigits: 1 }) + "%";
    } else if (typeof value === "number") {
      text = Number(value).toLocaleString(locale(), { maximumFractionDigits: 2 });
    } else {
      return String(value);
    }
    return unit ? text + " " + unit : text;
  }

  function compact(value) {
    var absolute = Math.abs(value);
    if (absolute >= 1e9) { return (value / 1e9).toFixed(1) + "B"; }
    if (absolute >= 1e6) { return (value / 1e6).toFixed(1) + "M"; }
    if (absolute >= 1e3) { return (value / 1e3).toFixed(absolute >= 1e4 ? 0 : 1) + "K"; }
    return Number(value).toLocaleString(locale(), { maximumFractionDigits: 1 });
  }

  function formatBytes(bytes) {
    if (bytes < 1024) { return bytes + " B"; }
    if (bytes < 1048576) { return (bytes / 1024).toFixed(0) + " KB"; }
    return (bytes / 1048576).toFixed(1) + " MB";
  }

  function formatWhen(value) { return value ? String(value).replace("T", " ") : ""; }

  /* ---------------- files ---------------- */
  function renderFiles() {
    var list = $("file-list");
    clear(list);
    var files = (state.data && state.data.inbox) || [];
    if (!files.length) {
      list.appendChild(el("li", "muted", t("noFiles")));
    } else {
      files.forEach(function (file) {
        var item = el("li");
        item.appendChild(el("span", null, file.name + " · " + formatBytes(file.size_bytes)));
        var button = el("button", "remove", "✕");
        button.type = "button";
        button.setAttribute("aria-label", t("remove") + " " + file.name);
        button.addEventListener("click", function () {
          api("/api/files/remove", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: file.name })
          }).then(function (result) { state.data.inbox = result.inbox; renderFiles(); });
        });
        item.appendChild(button);
        list.appendChild(item);
      });
    }
    var expected = (state.data && state.data.expected_files) || [];
    _set("files-expected", t("expected") + expected.map(function (source) {
      return source.title + " (" + source.patterns.join(", ") + ")";
    }).join(" · "));
    $("process-button").disabled = !files.length;
    _set("process-hint", files.length ? "" : t("needFiles"));
  }

  function uploadFiles(fileList) {
    var files = Array.prototype.slice.call(fileList);
    if (!files.length) { return; }
    var chain = Promise.resolve();
    files.forEach(function (file) {
      chain = chain.then(function () {
        return api("/api/files/raw", {
          method: "POST",
          headers: { "Content-Type": "application/octet-stream", "X-File-Name": encodeURIComponent(file.name) },
          body: file
        }).then(function (result) {
          state.data.inbox = result.inbox || state.data.inbox;
          renderFiles();
          if (result.errors && result.errors.length) { showError(result.errors[0]); }
        });
      });
    });
    return chain.catch(function (error) {
      showError({ what_happened: "The file upload did not finish.",
        next_action: "Add the file again. No partial file is used for processing.", detail: String(error), support_code: "E-IN-002" });
    });
  }

  /* ---------------- running ---------------- */
  function setProgress(progress) {
    $("progress-wrap").hidden = !progress.busy && progress.percent === 0;
    $("progress-fill").style.width = progress.percent + "%";
    $("progress-bar").setAttribute("aria-valuenow", String(progress.percent));
    _set("progress-text", progress.busy
      ? progress.percent + "% · " + progress.message
      : (progress.message || ""));
    var order = ["DETECTED", "OPENING", "EXTRACTING", "VALIDATING", "LOADING", "MERGING",
                 "CALCULATING", "GENERATING_JSON", "GENERATING_DASHBOARD", "VERIFYING", "COMPLETE"];
    var current = order.indexOf(progress.step);
    document.querySelectorAll("[data-state]").forEach(function (node) {
      var index = order.indexOf(node.getAttribute("data-state"));
      node.classList.toggle("active", index === current);
      node.classList.toggle("done", current >= 0 && index >= 0 && index < current);
    });
    $("process-button").disabled = progress.busy || !(state.data.inbox || []).length;
  }

  function poll() {
    api("/api/progress").then(function (progress) {
      setProgress(progress);
      if (progress.busy) { return; }
      window.clearInterval(state.polling);
      state.polling = null;
      refresh().then(function () {
        if (progress.result && progress.result.error) { showError(progress.result.error); }
      });
    });
  }

  function process() {
    hideError();
    api("/api/process", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: "{}"
    }).then(function (result) {
      if (!result.started) { _set("process-hint", result.reason || ""); return; }
      setProgress({ busy: true, percent: 1, message: t("working") });
      if (state.polling) { window.clearInterval(state.polling); }
      state.polling = window.setInterval(poll, 700);
    });
  }

  /* ---------------- errors ---------------- */
  function showError(error) {
    _set("error-heading", error.what_happened || "");
    _set("error-safe", error.trusted_data_safe === false ? "" : t("safe"));
    _set("error-action", error.next_action || "");
    _set("error-code", error.support_code || "");
    _set("error-detail", error.detail || "");
    $("error-card").hidden = false;
    $("error-card").scrollIntoView({ behavior: "smooth", block: "start" });
  }
  function hideError() { $("error-card").hidden = true; }

  /* ---------------- the cube: filter by summing, never by recalculating ------- */
  function analytics() { return state.dashboard && state.dashboard.analytics; }

  function initFilters(force) {
    var cube = analytics();
    if (!cube || !cube.periods.length) { state.filters = null; return; }
    if (state.filters && !force) { return; }
    state.filters = {
      from: cube.periods[0],
      to: cube.periods[cube.periods.length - 1],
      dims: cube.dimensions.map(function () { return null; })   /* null = every value */
    };
  }

  function cellMatches(cell, filters) {
    if (cell.p < filters.from || cell.p > filters.to) { return false; }
    for (var index = 0; index < filters.dims.length; index += 1) {
      var allowed = filters.dims[index];
      if (allowed && allowed.indexOf(cell.k[index]) === -1) { return false; }
    }
    return true;
  }

  /* Sum the additive measures over the matching cells, then divide the ratios.
   * Both steps repeat the engine's own arithmetic - no new formula appears. */
  function aggregate(filters) {
    var cube = analytics();
    var sums = {};
    cube.additive.forEach(function (id) { sums[id] = 0; });
    cube.cells.forEach(function (cell) {
      if (!cellMatches(cell, filters)) { return; }
      cube.additive.forEach(function (id, index) { sums[id] += cell.m[index]; });
    });
    cube.measures.forEach(function (measure) {
      if (measure.aggregate !== "ratio") { return; }
      var denominator = sums[measure.denominator];
      sums[measure.id] = denominator ? sums[measure.numerator] / denominator : null;
    });
    return sums;
  }

  function previousFilters() {
    var cube = analytics();
    var periods = cube.periods;
    var start = periods.indexOf(state.filters.from);
    var end = periods.indexOf(state.filters.to);
    var length = end - start + 1;
    if (start - length < 0) { return null; }
    return {
      from: periods[start - length], to: periods[start - 1], dims: state.filters.dims
    };
  }

  function measureById(id) {
    return analytics().measures.filter(function (m) { return m.id === id; })[0];
  }

  /* Series for one chart: values by period, or by a dimension's values,
   * optionally split into up to four series plus "Other". */
  function chartSeries(chart) {
    var cube = analytics();
    var measure = measureById(chart.measure);
    var additiveIndex = {};
    cube.additive.forEach(function (id, index) { additiveIndex[id] = index; });

    var parts = measure.aggregate === "ratio"
      ? [measure.numerator, measure.denominator] : [measure.id];

    var byDate = (chart.by || "date") === "date";
    var dimensionIndex = byDate ? -1 : cube.dimensions.map(function (d) { return d.id; })
      .indexOf(chart.by);
    var splitIndex = chart.split
      ? cube.dimensions.map(function (d) { return d.id; }).indexOf(chart.split) : -1;

    var labels = [];
    var labelPosition = {};
    if (byDate) {
      cube.periods.forEach(function (period) {
        if (period >= state.filters.from && period <= state.filters.to) {
          labelPosition[period] = labels.length;
          labels.push(period);
        }
      });
    } else {
      var allowed = state.filters.dims[dimensionIndex];
      cube.dimensions[dimensionIndex].values.forEach(function (value, index) {
        if (allowed && allowed.indexOf(index) === -1) { return; }
        labelPosition[index] = labels.length;
        labels.push(value);
      });
    }

    var splitNames = splitIndex >= 0 ? cube.dimensions[splitIndex].values.slice() : [null];
    var buckets = {};   /* seriesKey -> array of [numeratorSum, denominatorSum] */
    function bucketFor(key) {
      if (!buckets[key]) {
        buckets[key] = labels.map(function () { return parts.map(function () { return 0; }); });
      }
      return buckets[key];
    }

    cube.cells.forEach(function (cell) {
      if (!cellMatches(cell, state.filters)) { return; }
      var position = byDate ? labelPosition[cell.p] : labelPosition[cell.k[dimensionIndex]];
      if (position === undefined) { return; }
      var key = splitIndex >= 0 ? splitNames[cell.k[splitIndex]] : "__single__";
      var target = bucketFor(key)[position];
      parts.forEach(function (part, partIndex) {
        target[partIndex] += cell.m[additiveIndex[part]];
      });
    });

    var series = Object.keys(buckets).map(function (key) {
      var values = buckets[key].map(function (cell) {
        if (parts.length === 2) { return cell[1] ? cell[0] / cell[1] : null; }
        return cell[0];
      });
      return {
        name: key === "__single__" ? measure.title : key,
        values: values,
        total: values.reduce(function (sum, value) { return sum + (value || 0); }, 0)
      };
    });
    series.sort(function (a, b) { return b.total - a.total; });

    /* Bars and slices over a dimension read largest-first; a time axis keeps
     * its own order, because chronology is the point. */
    if (!byDate && series.length === 1 && labels.length > 1) {
      var order = labels.map(function (label, index) { return index; });
      order.sort(function (a, b) {
        return (series[0].values[b] || 0) - (series[0].values[a] || 0);
      });
      labels = order.map(function (index) { return labels[index]; });
      series[0].values = order.map(function (index) { return series[0].values[index]; });
    }

    /* Never invent a fifth hue: everything past the palette folds into "Other". */
    if (series.length > SERIES_SLOTS) {
      var kept = series.slice(0, SERIES_SLOTS - 1);
      var rest = series.slice(SERIES_SLOTS - 1);
      var merged = {
        name: t("other"), total: 0,
        values: labels.map(function (_, index) {
          return rest.reduce(function (sum, item) { return sum + (item.values[index] || 0); }, 0);
        })
      };
      merged.total = merged.values.reduce(function (sum, value) { return sum + value; }, 0);
      kept.push(merged);
      series = kept;
    }
    return { labels: labels, series: series, measure: measure, split: splitIndex >= 0 };
  }

  /* ---------------- tooltip ---------------- */
  var tooltip = null;
  function showTooltip(event, title, rows) {
    if (!tooltip) { tooltip = $("tooltip"); }
    clear(tooltip);
    tooltip.appendChild(setText(el("div", "tt-title"), title));
    rows.forEach(function (row) {
      var line = el("div", "tt-row");
      line.appendChild(setText(el("span"), row[0]));
      line.appendChild(setText(el("strong"), row[1]));
      tooltip.appendChild(line);
    });
    tooltip.classList.add("on");
    tooltip.setAttribute("aria-hidden", "false");
    moveTooltip(event);
  }
  function moveTooltip(event) {
    if (!tooltip) { return; }
    var box = tooltip.getBoundingClientRect();
    var left = Math.min(event.clientX + 14, window.innerWidth - box.width - 10);
    var top = Math.max(10, event.clientY - box.height - 12);
    tooltip.style.left = Math.max(10, left) + "px";
    tooltip.style.top = top + "px";
  }
  function hideTooltip() {
    if (!tooltip) { return; }
    tooltip.classList.remove("on");
    tooltip.setAttribute("aria-hidden", "true");
  }

  /* ---------------- chart marks ---------------- */
  function barPath(x, y, width, height, radius, horizontal) {
    var r = Math.max(0, Math.min(radius, horizontal ? width : height));
    if (horizontal) {
      return "M" + x + "," + y +
             "H" + (x + width - r) + "a" + r + "," + r + " 0 0 1 " + r + "," + r +
             "V" + (y + height - r) + "a" + r + "," + r + " 0 0 1 " + (-r) + "," + r +
             "H" + x + "Z";
    }
    return "M" + x + "," + (y + height) +
           "V" + (y + r) + "a" + r + "," + r + " 0 0 1 " + r + "," + (-r) +
           "H" + (x + width - r) + "a" + r + "," + r + " 0 0 1 " + r + "," + r +
           "V" + (y + height) + "Z";
  }

  function renderBarChart(container, data, chart) {
    var labels = data.labels;
    var values = data.series[0] ? data.series[0].values : [];
    var measure = data.measure;
    var width = 640;
    var rowHeight = 34;
    var gap = 8;
    var labelWidth = 132;
    var valueWidth = 96;
    var height = Math.max(60, labels.length * (rowHeight + gap) + 8);
    var maximum = Math.max.apply(null, values.map(function (v) { return Math.abs(v || 0); }).concat([1]));
    var plotWidth = width - labelWidth - valueWidth;

    var svg = svgEl("svg", {
      viewBox: "0 0 " + width + " " + height, class: "chart", role: "img",
      "aria-label": chart.title, preserveAspectRatio: "xMinYMin meet"
    });

    labels.forEach(function (label, index) {
      var y = index * (rowHeight + gap) + 4;
      var value = values[index] || 0;
      var barWidth = Math.max(3, (Math.abs(value) / maximum) * plotWidth);

      var text = svgEl("text", { x: labelWidth - 10, y: y + rowHeight * 0.68, "text-anchor": "end" });
      setText(text, label);
      svg.appendChild(text);

      var bar = svgEl("path", {
        d: barPath(labelWidth, y, barWidth, rowHeight, 4, true), class: "bar mark-1"
      });
      svg.appendChild(bar);

      var valueLabel = svgEl("text", {
        x: labelWidth + barWidth + 8, y: y + rowHeight * 0.68, class: "value-label"
      });
      setText(valueLabel, formatValue(value, measure.format, measure.unit));
      svg.appendChild(valueLabel);

      var hit = svgEl("rect", { x: labelWidth, y: y, width: plotWidth, height: rowHeight, class: "hit" });
      hit.addEventListener("mouseenter", function (event) {
        showTooltip(event, label, [[measure.title, formatValue(value, measure.format, measure.unit)]]);
      });
      hit.addEventListener("mousemove", moveTooltip);
      hit.addEventListener("mouseleave", hideTooltip);
      svg.appendChild(hit);
    });
    container.appendChild(svg);
  }

  function renderLineChart(container, data, chart) {
    var labels = data.labels;
    var measure = data.measure;
    var width = 640, height = 260;
    var padding = { top: 16, right: 18, bottom: 34, left: 62 };
    var plotWidth = width - padding.left - padding.right;
    var plotHeight = height - padding.top - padding.bottom;
    var everyValue = [];
    data.series.forEach(function (series) {
      series.values.forEach(function (value) { if (value !== null) { everyValue.push(value); } });
    });
    var maximum = Math.max.apply(null, everyValue.concat([1]));
    var minimum = Math.min.apply(null, everyValue.concat([0]));
    if (minimum > 0) { minimum = 0; }

    var svg = svgEl("svg", {
      viewBox: "0 0 " + width + " " + height, class: "chart", role: "img",
      "aria-label": chart.title, preserveAspectRatio: "xMinYMin meet"
    });

    function xAt(index) {
      if (labels.length === 1) { return padding.left + plotWidth / 2; }
      return padding.left + (index / (labels.length - 1)) * plotWidth;
    }
    function yAt(value) {
      var span = maximum - minimum || 1;
      return padding.top + plotHeight - ((value - minimum) / span) * plotHeight;
    }

    [0, 0.25, 0.5, 0.75, 1].forEach(function (fraction) {
      var value = minimum + (maximum - minimum) * fraction;
      var y = yAt(value);
      svg.appendChild(svgEl("line", {
        x1: padding.left, x2: width - padding.right, y1: y, y2: y, class: "grid-line"
      }));
      var tick = svgEl("text", { x: padding.left - 10, y: y + 4, "text-anchor": "end" });
      setText(tick, compact(value));
      svg.appendChild(tick);
    });

    labels.forEach(function (label, index) {
      if (labels.length > 12 && index % Math.ceil(labels.length / 12) !== 0) { return; }
      var tick = svgEl("text", {
        x: xAt(index), y: height - padding.bottom + 20, "text-anchor": "middle"
      });
      setText(tick, label);
      svg.appendChild(tick);
    });

    data.series.forEach(function (series, seriesIndex) {
      var slot = (seriesIndex % SERIES_SLOTS) + 1;
      var path = series.values.map(function (value, index) {
        return (index === 0 ? "M" : "L") + xAt(index) + "," + yAt(value || 0);
      }).join(" ");
      svg.appendChild(svgEl("path", { d: path, class: "series-line line-" + slot }));
      series.values.forEach(function (value, index) {
        svg.appendChild(svgEl("circle", {
          cx: xAt(index), cy: yAt(value || 0), r: 4, class: "point mark-" + slot
        }));
      });
    });

    labels.forEach(function (label, index) {
      var band = plotWidth / Math.max(1, labels.length);
      var hit = svgEl("rect", {
        x: xAt(index) - band / 2, y: padding.top, width: band, height: plotHeight, class: "hit"
      });
      hit.addEventListener("mouseenter", function (event) {
        showTooltip(event, label, data.series.map(function (series) {
          return [series.name, formatValue(series.values[index], measure.format, measure.unit)];
        }));
      });
      hit.addEventListener("mousemove", moveTooltip);
      hit.addEventListener("mouseleave", hideTooltip);
      svg.appendChild(hit);
    });
    container.appendChild(svg);
  }

  function renderStackedChart(container, data, chart) {
    var labels = data.labels;
    var measure = data.measure;
    var width = 640, height = 270;
    var padding = { top: 16, right: 18, bottom: 34, left: 62 };
    var plotWidth = width - padding.left - padding.right;
    var plotHeight = height - padding.top - padding.bottom;
    var totals = labels.map(function (_, index) {
      return data.series.reduce(function (sum, series) { return sum + (series.values[index] || 0); }, 0);
    });
    var maximum = Math.max.apply(null, totals.concat([1]));
    var bandWidth = plotWidth / Math.max(1, labels.length);
    var barWidth = Math.min(56, bandWidth * 0.62);

    var svg = svgEl("svg", {
      viewBox: "0 0 " + width + " " + height, class: "chart", role: "img",
      "aria-label": chart.title, preserveAspectRatio: "xMinYMin meet"
    });

    [0, 0.5, 1].forEach(function (fraction) {
      var y = padding.top + plotHeight - fraction * plotHeight;
      svg.appendChild(svgEl("line", {
        x1: padding.left, x2: width - padding.right, y1: y, y2: y, class: "grid-line"
      }));
      var tick = svgEl("text", { x: padding.left - 10, y: y + 4, "text-anchor": "end" });
      setText(tick, compact(maximum * fraction));
      svg.appendChild(tick);
    });

    labels.forEach(function (label, index) {
      var centre = padding.left + bandWidth * (index + 0.5);
      var cursor = padding.top + plotHeight;
      data.series.forEach(function (series, seriesIndex) {
        var value = series.values[index] || 0;
        if (!value) { return; }
        var segment = (value / maximum) * plotHeight;
        /* a 2px surface gap keeps adjacent fills from reading as one block */
        var top = cursor - segment + 1;
        svg.appendChild(svgEl("path", {
          d: barPath(centre - barWidth / 2, top, barWidth, Math.max(1, segment - 2), 4, false),
          class: "bar mark-" + ((seriesIndex % SERIES_SLOTS) + 1)
        }));
        cursor -= segment;
      });
      var tick = svgEl("text", {
        x: centre, y: height - padding.bottom + 20, "text-anchor": "middle"
      });
      setText(tick, label);
      svg.appendChild(tick);

      var hit = svgEl("rect", {
        x: centre - bandWidth / 2, y: padding.top, width: bandWidth, height: plotHeight, class: "hit"
      });
      hit.addEventListener("mouseenter", function (event) {
        showTooltip(event, label, data.series.map(function (series) {
          return [series.name, formatValue(series.values[index], measure.format, measure.unit)];
        }).concat([[t("total"), formatValue(totals[index], measure.format, measure.unit)]]));
      });
      hit.addEventListener("mousemove", moveTooltip);
      hit.addEventListener("mouseleave", hideTooltip);
      svg.appendChild(hit);
    });
    container.appendChild(svg);
  }

  function renderDonutChart(container, data, chart) {
    var measure = data.measure;
    var values = data.labels.map(function (label, index) {
      return { label: label, value: (data.series[0] ? data.series[0].values[index] : 0) || 0 };
    }).filter(function (item) { return item.value > 0; });
    var total = values.reduce(function (sum, item) { return sum + item.value; }, 0) || 1;
    var size = 260, radius = 100, inner = 62, centre = size / 2;
    var svg = svgEl("svg", {
      viewBox: "0 0 " + size + " " + size, class: "chart", role: "img",
      "aria-label": chart.title, preserveAspectRatio: "xMidYMid meet", style: "max-width:300px"
    });
    var angle = -Math.PI / 2;
    values.forEach(function (item, index) {
      var sweep = (item.value / total) * Math.PI * 2;
      var gap = 0.015;
      var start = angle + gap, end = angle + sweep - gap;
      var large = sweep > Math.PI ? 1 : 0;
      var path = "M" + (centre + radius * Math.cos(start)) + "," + (centre + radius * Math.sin(start)) +
        "A" + radius + "," + radius + " 0 " + large + " 1 " +
        (centre + radius * Math.cos(end)) + "," + (centre + radius * Math.sin(end)) +
        "L" + (centre + inner * Math.cos(end)) + "," + (centre + inner * Math.sin(end)) +
        "A" + inner + "," + inner + " 0 " + large + " 0 " +
        (centre + inner * Math.cos(start)) + "," + (centre + inner * Math.sin(start)) + "Z";
      var arc = svgEl("path", { d: path, class: "bar mark-" + ((index % SERIES_SLOTS) + 1) });
      arc.addEventListener("mouseenter", function (event) {
        showTooltip(event, item.label, [
          [measure.title, formatValue(item.value, measure.format, measure.unit)],
          ["%", ((item.value / total) * 100).toFixed(1) + "%"]
        ]);
      });
      arc.addEventListener("mousemove", moveTooltip);
      arc.addEventListener("mouseleave", hideTooltip);
      svg.appendChild(arc);
      angle += sweep;
    });
    container.appendChild(svg);
  }

  function legendFor(data) {
    if (data.series.length < 2) { return null; }
    var legend = el("div", "legend");
    data.series.forEach(function (series, index) {
      var item = el("span");
      var swatch = el("i");
      swatch.style.background = "var(--series-" + ((index % SERIES_SLOTS) + 1) + ")";
      item.appendChild(swatch);
      item.appendChild(setText(el("span"), series.name));
      legend.appendChild(item);
    });
    return legend;
  }

  function chartTable(data) {
    var wrapper = el("div", "table-scroll");
    var table = el("table");
    var head = el("thead");
    var headRow = el("tr");
    headRow.appendChild(el("th", null, data.split ? "" : ""));
    var first = el("th", null, analytics().date_title);
    clear(headRow);
    headRow.appendChild(first);
    data.series.forEach(function (series) {
      headRow.appendChild(el("th", "number", series.name));
    });
    head.appendChild(headRow);
    table.appendChild(head);
    var body = el("tbody");
    data.labels.forEach(function (label, index) {
      var row = el("tr");
      row.appendChild(el("td", null, label));
      data.series.forEach(function (series) {
        row.appendChild(el("td", "number",
          formatValue(series.values[index], data.measure.format, data.measure.unit)));
      });
      body.appendChild(row);
    });
    table.appendChild(body);
    wrapper.appendChild(table);
    return wrapper;
  }

  function renderCharts() {
    var container = $("charts-section");
    clear(container);
    var cube = analytics();
    if (!cube) { return; }

    (cube.charts || []).forEach(function (chart) {
      var card = el("section", "card chart-card");
      var head = el("div", "chart-head");
      head.appendChild(el("h2", null, chart.title || chart.id));

      var toggle = el("button", "linkish");
      toggle.type = "button";
      var showingTable = state.views[chart.id] === "table";
      setText(toggle, showingTable ? t("chartView") : t("tableView"));
      toggle.addEventListener("click", function () {
        state.views[chart.id] = showingTable ? "chart" : "table";
        renderCharts();
      });
      head.appendChild(toggle);
      card.appendChild(head);

      var data = chartSeries(chart);
      if (!data.labels.length) {
        card.appendChild(el("p", "empty-note", t("noData")));
        container.appendChild(card);
        return;
      }

      if (showingTable) {
        card.appendChild(chartTable(data));
      } else {
        var body = el("div");
        var form = chart.form || "bar";
        if (form === "line") { renderLineChart(body, data, chart); }
        else if (form === "stacked") { renderStackedChart(body, data, chart); }
        else if (form === "donut") { renderDonutChart(body, data, chart); }
        else { renderBarChart(body, data, chart); }
        card.appendChild(body);
        var legend = legendFor(data);
        if (legend) { card.appendChild(legend); }
      }
      container.appendChild(card);
    });
  }

  function periodMeasureValues(id) {
    var cube = analytics();
    if (!cube || !state.filters) { return []; }
    return cube.periods.filter(function (period) {
      return period >= state.filters.from && period <= state.filters.to;
    }).map(function (period) {
      var scoped = { from: period, to: period, dims: state.filters.dims };
      return aggregate(scoped)[id];
    });
  }

  function sparkline(values) {
    var numeric = values.map(function (v) { return v === null || v === undefined ? null : Number(v); });
    var present = numeric.filter(function (v) { return v !== null && isFinite(v); });
    if (present.length < 2) { return null; }
    var min = Math.min.apply(null, present), max = Math.max.apply(null, present);
    var range = max - min || 1, width = 120, height = 42, pad = 3;
    var points = [];
    numeric.forEach(function (value, index) {
      if (value === null || !isFinite(value)) { return; }
      var x = pad + (index / Math.max(1, numeric.length - 1)) * (width - pad * 2);
      var y = height - pad - ((value - min) / range) * (height - pad * 2);
      points.push([x, y]);
    });
    if (points.length < 2) { return null; }
    var path = "M" + points.map(function (p) { return p[0].toFixed(1) + "," + p[1].toFixed(1); }).join(" L");
    var area = path + " L" + points[points.length - 1][0].toFixed(1) + "," + (height-pad) +
      " L" + points[0][0].toFixed(1) + "," + (height-pad) + " Z";
    var svg = svgEl("svg", { viewBox:"0 0 120 42", class:"kpi-spark", "aria-hidden":"true" });
    svg.appendChild(svgEl("path", { d:area, class:"spark-area" }));
    svg.appendChild(svgEl("path", { d:path }));
    return svg;
  }

  function renderDecisionCockpit() {
    var data = state.dashboard || {};
    var insights = data.insights || [];
    var decision = data.decision || {};
    var primary = insights.filter(function (item) { return item.severity === "action"; })[0] ||
      insights.filter(function (item) { return item.severity === "watch"; })[0] || insights[0];
    var badge = $("decision-badge");
    badge.className = "signal-badge " + (primary ? (primary.severity || "info") : "info");
    setText(badge, primary ? t("decisionVerified") : "Verified");
    _set("decision-title", primary ? primary.title : "No unusual signal detected");
    _set("decision-body", primary ? primary.body : "The verified result is within the patterns currently available to the report.");
    var evidence = $("decision-evidence"); clear(evidence);
    var ev = primary && primary.evidence ? primary.evidence : {};
    [["Period", ev.current_period || ev.period], ["Previous", ev.previous_period],
     ["Share", ev.share_percent !== undefined ? Number(ev.share_percent).toFixed(1)+"%" : null],
     ["Segment", ev.member], ["Pattern score", ev.robust_z !== undefined ? ev.robust_z : null]].forEach(function (pair) {
       if (pair[1] !== null && pair[1] !== undefined && pair[1] !== "") { evidence.appendChild(el("span", null, pair[0]+": "+pair[1])); }
     });
    _set("signal-count", decision.signal_count !== undefined ? decision.signal_count : insights.length);
    _set("watch-count", (decision.watch_count || 0) + " watch · " + (decision.action_count || 0) + " action");
    var confidence = Number(decision.acceptance_rate === undefined ? 100 : decision.acceptance_rate);
    _set("confidence-label", confidence >= 99 && !(decision.action_count) ? t("confidenceHigh") : t("confidenceReview"));
    _set("confidence-note", confidence.toFixed(1) + "% rows accepted · " + (decision.checks_passed || 0) + "/" + (decision.checks_total || 0) + " controls");
    var files = (data.run && data.run.files) || [];
    var newest = files.map(function (f) { return f.modified_at || ""; }).sort().slice(-1)[0];
    _set("freshness-label", t("sourceCurrent"));
    _set("freshness-note", newest ? formatWhen(newest) : "Source timestamps retained");
  }

  /* ---------------- KPIs ---------------- */
  function renderKpis() {
    var section = $("kpi-section");
    clear(section);
    var cube = analytics();
    var filtered = state.filters && isFiltered();

    if (cube) {
      var current = aggregate(state.filters);
      var previousWindow = previousFilters();
      var previous = previousWindow ? aggregate(previousWindow) : null;
      (cube.kpis || []).forEach(function (id) {
        var measure = measureById(id);
        if (!measure) { return; }
        var card = el("article", "kpi");
        card.appendChild(el("div", "title", measure.title));
        card.appendChild(el("div", "value", formatValue(current[id], measure.format, measure.unit)));
        var canCompare = previous && previous[id] !== null && previous[id] !== undefined && Number(previous[id]) !== 0;
        if (canCompare && current[id] !== null && current[id] !== undefined) {
          var change = ((Number(current[id]) - Number(previous[id])) / Math.abs(Number(previous[id]))) * 100;
          var direction = Math.abs(change) < 0.05 ? "flat"
            : ((change > 0) === (measure.goal_direction !== "down") ? "up" : "down");
          var arrow = Math.abs(change) < 0.05 ? "→" : (change > 0 ? "↑" : "↓");
          card.appendChild(el("div", "delta " + direction,
            arrow + " " + Math.abs(change).toFixed(1) + "% " + t("vsPrevious")));
        } else {
          card.appendChild(el("div", "note", t("noPrevious")));
        }
        var spark = sparkline(periodMeasureValues(id));
        if (spark) { card.appendChild(spark); }
        section.appendChild(card);
      });
    }

    (state.dashboard.kpis || []).forEach(function (kpi) {
      if (cube && cube.kpis && cube.kpis.indexOf(kpi.id) !== -1) { return; }
      var card = el("article", "kpi");
      card.appendChild(el("div", "title", kpi.title));
      card.appendChild(el("div", "value", formatValue(kpi.value, kpi.format, kpi.unit)));
      card.appendChild(el("div", "note", kpi.subtitle || (filtered ? t("wholePeriod") : "Verified whole-report KPI")));
      section.appendChild(card);
    });
  }

  function isFiltered() {
    var cube = analytics();
    if (!cube || !state.filters) { return false; }
    if (state.filters.from !== cube.periods[0]) { return true; }
    if (state.filters.to !== cube.periods[cube.periods.length - 1]) { return true; }
    return state.filters.dims.some(function (allowed) { return allowed !== null; });
  }

  /* ---------------- filters ---------------- */
  function renderFilterBar() {
    var cube = analytics();
    var section = $("filters");
    section.hidden = !cube;
    if (!cube) { return; }
    var grid = $("filters-grid");
    clear(grid);

    function periodSelect(which) {
      var group = el("div", "filter-group");
      group.appendChild(el("div", "filter-label", which === "from" ? t("from") : t("to")));
      var controls = el("div", "filter-controls");
      var select = document.createElement("select");
      select.setAttribute("aria-label", which === "from" ? t("from") : t("to"));
      cube.periods.forEach(function (period) {
        var option = document.createElement("option");
        option.value = period;
        setText(option, period);
        if (state.filters[which] === period) { option.selected = true; }
        select.appendChild(option);
      });
      select.addEventListener("change", function () {
        state.filters[which] = select.value;
        if (state.filters.from > state.filters.to) {
          state.filters[which === "from" ? "to" : "from"] = select.value;
        }
        renderFiltered();
      });
      controls.appendChild(select);
      group.appendChild(controls);
      return group;
    }

    grid.appendChild(periodSelect("from"));
    grid.appendChild(periodSelect("to"));

    cube.dimensions.forEach(function (dimension, dimensionIndex) {
      if (!dimension.values.length) { return; }
      var group = el("div", "filter-group");
      group.appendChild(el("div", "filter-label", dimension.title));
      var controls = el("div", "filter-controls");

      /* High-cardinality dimensions still need a usable filter. Chips become
       * noisy after a dozen values, so use a compact searchable-native select. */
      if (dimension.values.length > 12) {
        var select = document.createElement("select");
        select.setAttribute("aria-label", dimension.title);
        var allOption = document.createElement("option");
        allOption.value = ""; setText(allOption, t("all")); select.appendChild(allOption);
        dimension.values.forEach(function (value, valueIndex) {
          var option = document.createElement("option");
          option.value = String(valueIndex); setText(option, value);
          var chosen = state.filters.dims[dimensionIndex];
          if (chosen && chosen.length === 1 && chosen[0] === valueIndex) { option.selected = true; }
          select.appendChild(option);
        });
        select.addEventListener("change", function () {
          state.filters.dims[dimensionIndex] = select.value === "" ? null : [Number(select.value)];
          renderFiltered();
        });
        controls.appendChild(select);
        group.appendChild(controls);
        grid.appendChild(group);
        return;
      }

      var allChip = el("button", "chip", t("all"));
      allChip.type = "button";
      allChip.setAttribute("aria-pressed", String(state.filters.dims[dimensionIndex] === null));
      allChip.addEventListener("click", function () {
        state.filters.dims[dimensionIndex] = null;
        renderFiltered();
      });
      controls.appendChild(allChip);

      dimension.values.forEach(function (value, valueIndex) {
        var selected = state.filters.dims[dimensionIndex];
        var active = selected !== null && selected.indexOf(valueIndex) !== -1;
        var chip = el("button", "chip", value);
        chip.type = "button";
        chip.setAttribute("aria-pressed", String(active));
        chip.addEventListener("click", function () {
          var chosen = state.filters.dims[dimensionIndex];
          if (chosen === null) { chosen = []; }
          else { chosen = chosen.slice(); }
          var at = chosen.indexOf(valueIndex);
          if (at === -1) { chosen.push(valueIndex); } else { chosen.splice(at, 1); }
          state.filters.dims[dimensionIndex] = chosen.length ? chosen : null;
          renderFiltered();
        });
        controls.appendChild(chip);
      });
      group.appendChild(controls);
      grid.appendChild(group);
    });

    var resetGroup = el("div", "filter-group");
    resetGroup.appendChild(el("div", "filter-label", " "));
    var resetControls = el("div", "filter-controls");
    var reset = el("button", "ghost", t("reset"));
    reset.type = "button";
    reset.addEventListener("click", function () { initFilters(true); renderFiltered(); });
    resetControls.appendChild(reset);
    var presets = el("div", "filter-presets");
    [[t("latest"), 1], [t("last3"), 3], [t("allPeriods"), 0]].forEach(function (preset) {
      var button = el("button", null, preset[0]); button.type = "button";
      button.addEventListener("click", function () {
        if (!preset[1]) { state.filters.from = cube.periods[0]; state.filters.to = cube.periods[cube.periods.length-1]; }
        else { state.filters.to = cube.periods[cube.periods.length-1]; state.filters.from = cube.periods[Math.max(0,cube.periods.length-preset[1])]; }
        renderFiltered();
      }); presets.appendChild(button);
    });
    resetControls.appendChild(presets);
    resetGroup.appendChild(resetControls);
    grid.appendChild(resetGroup);

    _set("filter-summary", filterSummary());
  }

  /* Say exactly what is being shown - a filtered number that looks unfiltered
   * is how people end up quoting the wrong figure. */
  function filterSummary() {
    var cube = analytics();
    if (!isFiltered()) { return t("showingAll"); }
    var parts = [];
    var periodCount = cube.periods.filter(function (period) {
      return period >= state.filters.from && period <= state.filters.to;
    }).length;
    if (periodCount !== cube.periods.length) {
      parts.push(t("showing") + periodCount + t("of") + cube.periods.length + t("periodsWord"));
    }
    cube.dimensions.forEach(function (dimension, index) {
      var chosen = state.filters.dims[index];
      if (!chosen) { return; }
      parts.push(dimension.title + ": " + chosen.map(function (valueIndex) {
        return dimension.values[valueIndex];
      }).join(", "));
    });
    return parts.join(" · ");
  }

  function renderFiltered() {
    renderFilterBar();
    renderKpis();
    renderCharts();
  }

  /* ---------------- metric tables (from the project SQL) ---------------- */
  function renderMetricTables() {
    var container = $("tables-section");
    clear(container);
    (state.dashboard.tables || []).forEach(function (table) {
      var card = el("section", "card");
      card.appendChild(el("h2", null, table.title));

      var tools = el("div", "table-tools");
      var search = document.createElement("input");
      search.type = "search";
      search.placeholder = t("search");
      search.setAttribute("aria-label", t("search") + " " + table.title);
      tools.appendChild(search);
      var link = el("a", "ghost", t("download"));
      link.href = "/api/export/" + encodeURIComponent(table.id) + ".csv?k=" + encodeURIComponent(KEY);
      link.setAttribute("download", "");
      tools.appendChild(link);
      card.appendChild(tools);

      var scroll = el("div", "table-scroll");
      var node = el("table");
      var head = el("thead");
      var headRow = el("tr");
      var sort = state.tables[table.id] || { column: null, direction: 1 };
      (table.columns || []).forEach(function (column, index) {
        var numeric = (table.rows || []).some(function (row) { return typeof row[index] === "number"; });
        var cell = el("th", "sortable" + (numeric ? " number" : ""),
          column + (sort.column === index ? (sort.direction > 0 ? " ↑" : " ↓") : ""));
        cell.addEventListener("click", function () {
          state.tables[table.id] = {
            column: index,
            direction: sort.column === index ? -sort.direction : 1
          };
          renderMetricTables();
        });
        headRow.appendChild(cell);
      });
      head.appendChild(headRow);
      node.appendChild(head);

      var decimalColumns = (table.columns || []).map(function (_, index) {
        return (table.rows || []).some(function (row) {
          return typeof row[index] === "number" && !Number.isInteger(row[index]);
        });
      });

      var rows = (table.rows || []).slice();
      if (sort.column !== null) {
        rows.sort(function (a, b) {
          var left = a[sort.column], right = b[sort.column];
          if (typeof left === "number" && typeof right === "number") {
            return (left - right) * sort.direction;
          }
          return String(left).localeCompare(String(right)) * sort.direction;
        });
      }

      var body = el("tbody");
      function fill(term) {
        clear(body);
        rows.filter(function (row) {
          return !term || row.some(function (cell) {
            return String(cell).toLowerCase().indexOf(term) !== -1;
          });
        }).forEach(function (row) {
          var tr = el("tr");
          row.forEach(function (value, index) {
            var numeric = typeof value === "number";
            tr.appendChild(el("td", numeric ? "number" : null,
              numeric ? formatValue(value, decimalColumns[index] ? "money" : "number")
                      : (value === null ? "—" : value)));
          });
          body.appendChild(tr);
        });
      }
      fill("");
      search.addEventListener("input", function () { fill(search.value.trim().toLowerCase()); });
      node.appendChild(body);
      scroll.appendChild(node);
      card.appendChild(scroll);
      container.appendChild(card);
    });
  }

  function fillTable(tableId, columns, rows, classFor) {
    var node = $(tableId);
    var head = node.querySelector("thead");
    var body = node.querySelector("tbody");
    clear(head); clear(body);
    var headRow = el("tr");
    columns.forEach(function (column) { headRow.appendChild(el("th", null, column)); });
    head.appendChild(headRow);
    rows.forEach(function (row) {
      var tr = el("tr");
      row.forEach(function (value, index) {
        tr.appendChild(el("td", classFor ? classFor(row, index) : null,
          value === null || value === undefined ? "—" : value));
      });
      body.appendChild(tr);
    });
  }

  /* ---------------- whole page ---------------- */
  function renderStatus(status) {
    var pill = $("status-pill");
    pill.className = "pill pill-" + (status || "idle");
    setText(pill, status || t("idle"));
  }

  function render() {
    var data = state.dashboard;
    $("empty-state").hidden = !!data;
    $("result").hidden = !data;
    if (!data) { renderStatus(null); return; }

    var title = data.project.title[state.lang] || data.project.title.en || data.project.name;
    document.title = title;
    _set("project-title", title);
    _set("project-purpose", data.project.purpose || "");
    renderStatus(data.run.status);
    _set("run-message", data.run.message || "");

    var facts = $("run-facts");
    clear(facts);
    [[t("rowsRead"), data.run.rows.read], [t("rowsAccepted"), data.run.rows.accepted],
     [t("rowsAttention"), data.run.rows.needs_attention], [t("rowsScope"), data.run.rows.out_of_scope],
     [t("finished"), formatWhen(data.run.finished_at)]].forEach(function (pair) {
      var group = el("div");
      group.appendChild(el("dt", null, pair[0]));
      group.appendChild(el("dd", null, typeof pair[1] === "number"
        ? formatValue(pair[1], "integer") : (pair[1] || "—")));
      facts.appendChild(group);
    });

    var checks = data.reconciliation || [];
    var passed = checks.filter(function (check) { return check.status === "PASS"; }).length;
    _set("quality-score", checks.length ? passed + "/" + checks.length : "—");
    var decisionMeta = data.decision || {};
    _set("acceptance-rate", decisionMeta.acceptance_rate !== undefined ? Number(decisionMeta.acceptance_rate).toFixed(1) + "%" : "—");
    var sync = data.enterprise_sync || {};
    _set("sync-state", sync.enabled ? (sync.status || "PENDING") : "Local only");
    _set("last-updated", formatWhen(data.run.finished_at) || "—");
    _set("run-state", data.run.state || "COMPLETE");

    initFilters(false);
    renderDecisionCockpit();
    renderFiltered();

    var insights = data.insights || [];
    $("insights-section").hidden = !insights.length;
    var list = $("insights-list");
    clear(list);
    insights.forEach(function (insight) {
      var item = el("li", insight.severity || "info");
      item.appendChild(el("strong", null, insight.title));
      if (insight.body) { item.appendChild(setText(el("span"), insight.body)); }
      var evidence = insight.evidence || {};
      var evidenceParts = [];
      if (evidence.current_period) { evidenceParts.push(evidence.current_period); }
      if (evidence.previous_period) { evidenceParts.push("vs " + evidence.previous_period); }
      if (evidence.share_percent !== undefined) { evidenceParts.push(Number(evidence.share_percent).toFixed(1) + "% share"); }
      if (evidence.member) { evidenceParts.push(String(evidence.member)); }
      if (evidenceParts.length) { item.appendChild(el("span", "evidence-line", evidenceParts.join(" · "))); }
      list.appendChild(item);
    });

    renderMetricTables();

    var attention = data.attention || { total: 0, rows: [] };
    $("attention-section").hidden = !attention.total;
    if (attention.total) {
      _set("attention-note", t("attentionNote") +
        (attention.total > attention.shown
          ? " (" + attention.shown + "/" + attention.total + ")" : ""));
      fillTable("attention-table", [t("file"), t("row"), t("reason")],
        attention.rows.map(function (row) { return [row.file_name, row.excel_row, row.message]; }));
      $("attention-export").href = "/api/export/attention.csv?k=" + encodeURIComponent(KEY);
      setText($("attention-export"), t("download"));
    }

    fillTable("reconciliation-table",
      [t("source"), t("check"), t("expectedCol"), t("actual"), t("difference"), t("status")],
      (data.reconciliation || []).map(function (check) {
        return [check.source_id, check.check, check.expected, check.actual, check.difference,
                check.status];
      }),
      function (row, index) { return index === 5 ? "status-" + row[5] : null; });

    var lineage = $("lineage");
    clear(lineage);
    (data.run.files || []).forEach(function (file) {
      lineage.appendChild(el("p", "mono", file.file_name + " · " + formatBytes(file.size_bytes) +
        " · " + file.sha256.slice(0, 16) + "…"));
    });

    fillTable("history-table", [t("when"), t("status"), t("used"), t("message")],
      (data.history || []).map(function (run) {
        return [formatWhen(run.finished_at || run.started_at), run.status, run.rows_clean,
                run.message];
      }),
      function (row, index) { return index === 1 ? "status-" + row[1] : null; });
  }

  function applyTheme() {
    if (state.theme) { document.documentElement.setAttribute("data-theme", state.theme); }
    var dark = state.theme === "dark" ||
      (!state.theme && window.matchMedia("(prefers-color-scheme: dark)").matches);
    setText($("theme-toggle"), dark ? t("themeLight") : t("theme"));
  }

  function applyLanguage() {
    document.documentElement.lang = state.lang;
    document.documentElement.dir = state.lang === "ar" ? "rtl" : "ltr";
    document.querySelectorAll("[data-i18n]").forEach(function (node) {
      setText(node, t(node.getAttribute("data-i18n")));
    });
    setText($("lang-toggle"), state.lang === "ar" ? "English" : "العربية");
    _set("footer-note", t("footer"));
    applyTheme();
    renderFiles();
    render();
  }

  function refresh() {
    if (SAVED) {
      state.data = { inbox: [], expected_files: [], progress: { busy: false, percent: 0, message: "" },
                     project: SAVED.project };
      state.dashboard = SAVED;
      if (!state.userChoseLanguage && SAVED.project && SAVED.project.language) {
        state.lang = SAVED.project.language === "ar" ? "ar" : "en";
      }
      applyLanguage();
      return Promise.resolve();
    }
    return api("/api/state").then(function (data) {
      state.data = data;
      var previousRun = state.dashboard && state.dashboard.run && state.dashboard.run.run_id;
      state.dashboard = data.dashboard;
      var newRun = state.dashboard && state.dashboard.run && state.dashboard.run.run_id;
      if (previousRun !== newRun) { state.filters = null; }
      if (!state.userChoseLanguage && data.project && data.project.language) {
        state.lang = data.project.language === "ar" ? "ar" : "en";
      }
      applyLanguage();
      setProgress(data.progress);
      if (data.progress.busy && !state.polling) {
        state.polling = window.setInterval(poll, 700);
      }
    });
  }

  /* ---------------- wiring ---------------- */
  document.addEventListener("DOMContentLoaded", function () {
    if (SAVED) {
      $("files-card").hidden = true;
      var saveLink = $("save-copy");
      if (saveLink) { saveLink.hidden = true; }
      $("print-button").addEventListener("click", function () { window.print(); });
      $("lang-toggle").addEventListener("click", function () {
        state.lang = state.lang === "ar" ? "en" : "ar";
        state.userChoseLanguage = true;
        applyLanguage();
      });
      $("theme-toggle").addEventListener("click", function () {
        var isDark = state.theme === "dark" ||
          (!state.theme && window.matchMedia("(prefers-color-scheme: dark)").matches);
        state.theme = isDark ? "light" : "dark";
        applyTheme();
      });
      refresh();
      return;
    }
    var dropzone = $("dropzone");
    var input = $("file-input");
    dropzone.addEventListener("click", function () { input.click(); });
    dropzone.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); input.click(); }
    });
    ["dragenter", "dragover"].forEach(function (name) {
      dropzone.addEventListener(name, function (event) {
        event.preventDefault(); dropzone.classList.add("over");
      });
    });
    ["dragleave", "drop"].forEach(function (name) {
      dropzone.addEventListener(name, function (event) {
        event.preventDefault(); dropzone.classList.remove("over");
      });
    });
    dropzone.addEventListener("drop", function (event) { uploadFiles(event.dataTransfer.files); });
    input.addEventListener("change", function () { uploadFiles(input.files); input.value = ""; });
    var save = $("save-copy");
    save.href = "/api/export/dashboard.html?k=" + encodeURIComponent(KEY);
    $("process-button").addEventListener("click", process);
    $("print-button").addEventListener("click", function () { window.print(); });
    $("lang-toggle").addEventListener("click", function () {
      state.lang = state.lang === "ar" ? "en" : "ar";
      state.userChoseLanguage = true;
      applyLanguage();
    });
    $("theme-toggle").addEventListener("click", function () {
      var dark = state.theme === "dark" ||
        (!state.theme && window.matchMedia("(prefers-color-scheme: dark)").matches);
      state.theme = dark ? "light" : "dark";
      applyTheme();
    });
    refresh();
  });
})();
