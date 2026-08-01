(function () {
  "use strict";

  var LG_MIN = 1024;
  var chartFont = { family: "Inter, sans-serif", size: 11 };
  var gridColor = "rgba(148, 163, 184, 0.12)";
  var primaryGreen = "#0d6b4f";
  var instances = { consumption: null, cost: null };

  function isDesktop() {
    return window.matchMedia("(min-width: " + LG_MIN + "px)").matches;
  }

  function readJson(id) {
    var el = document.getElementById(id);
    if (!el) {
      return [];
    }
    try {
      return JSON.parse(el.textContent || "[]");
    } catch (err) {
      return [];
    }
  }

  function showEmpty(name, show) {
    var empty = document.querySelector('[data-chart-empty="' + name + '"]');
    var wrap = document.querySelector(
      '[data-chart-panel="' + name + '"] .t-dashboard-chart-wrap'
    );
    if (empty) {
      empty.hidden = !show;
    }
    if (wrap) {
      wrap.hidden = !!show;
    }
  }

  function createConsumptionChart(canvas, data) {
    if (!window.Chart || !canvas || !data.length) {
      return null;
    }
    return new window.Chart(canvas, {
      type: "line",
      data: {
        labels: data.map(function (row) {
          return row.label;
        }),
        datasets: [
          {
            label: "Verbrauch",
            data: data.map(function (row) {
              return row.consumption;
            }),
            borderColor: primaryGreen,
            backgroundColor: "rgba(13, 107, 79, 0.12)",
            borderWidth: 2.5,
            pointRadius: 3,
            pointBackgroundColor: primaryGreen,
            pointBorderColor: "#fff",
            pointBorderWidth: 2,
            tension: 0.35,
            fill: true,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: "#94a3b8", font: chartFont, maxTicksLimit: 5 },
          },
          y: {
            beginAtZero: false,
            grid: { color: gridColor },
            ticks: { color: "#94a3b8", font: chartFont },
          },
        },
      },
    });
  }

  function createCostChart(canvas, data) {
    if (!window.Chart || !canvas) {
      return null;
    }
    var hasValues = data.some(function (row) {
      return Number(row.cost_eur) > 0;
    });
    if (!hasValues) {
      return null;
    }
    return new window.Chart(canvas, {
      type: "bar",
      data: {
        labels: data.map(function (row) {
          return row.label;
        }),
        datasets: [
          {
            label: "Kosten (€)",
            data: data.map(function (row) {
              return row.cost_eur;
            }),
            backgroundColor: primaryGreen,
            borderRadius: 6,
            maxBarThickness: 32,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: "#94a3b8", font: chartFont },
          },
          y: {
            beginAtZero: true,
            grid: { color: gridColor },
            ticks: { color: "#94a3b8", font: chartFont },
          },
        },
      },
    });
  }

  function ensureChart(name, datasets) {
    if (instances[name]) {
      return;
    }
    var canvas = document.getElementById(
      name === "consumption" ? "consumption-chart" : "cost-bar-chart"
    );
    if (!canvas) {
      return;
    }
    var data = datasets[name] || [];
    var chart =
      name === "consumption"
        ? createConsumptionChart(canvas, data)
        : createCostChart(canvas, data);
    if (chart) {
      instances[name] = chart;
      showEmpty(name, false);
    } else {
      showEmpty(name, true);
    }
  }

  function activateTab(name, datasets) {
    var tabs = document.querySelectorAll("[data-chart-tab]");
    var panels = document.querySelectorAll("[data-chart-panel]");
    tabs.forEach(function (tab) {
      var selected = tab.getAttribute("data-chart-tab") === name;
      tab.setAttribute("aria-selected", selected ? "true" : "false");
      tab.classList.toggle("t-dashboard-chart-tab--active", selected);
    });
    panels.forEach(function (panel) {
      var match = panel.getAttribute("data-chart-panel") === name;
      panel.hidden = !match;
    });
    ensureChart(name, datasets);
  }

  function initCharts() {
    var root = document.querySelector(".t-dashboard-charts");
    if (!root || !isDesktop()) {
      return;
    }

    var datasets = {
      consumption: readJson("dashboard-consumption-data"),
      cost: readJson("dashboard-cost-data"),
    };
    var defaultTab = root.getAttribute("data-default-tab") || "consumption";
    if (defaultTab === "consumption" && !datasets.consumption.length) {
      defaultTab = "cost";
    }

    activateTab(defaultTab, datasets);

    root.querySelectorAll("[data-chart-tab]").forEach(function (tab) {
      tab.addEventListener("click", function () {
        activateTab(tab.getAttribute("data-chart-tab"), datasets);
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initCharts);
  } else {
    initCharts();
  }
})();
