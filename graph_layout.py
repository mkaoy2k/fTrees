"""Spread a Pyvis graph across the iframe that displays it.

Both family graphs draw one generation per horizontal row and then leave
vis.js at its default spacing, which clusters a small tree in the middle of
a wide frame. The script below runs after that layout. It keeps each
generation on its row, spaces the rows across the iframe, and scales the
view down only when the labels would overlap.
"""

_LAYOUT_SCRIPT = r"""
(function () {
  var style = document.createElement("style");
  style.textContent = [
    "html,body{margin:0;padding:0;background:#fff;overflow:hidden;}",
    "h1{display:none;}",
    "#mynetwork{float:none !important;border:none !important;margin:0 !important;}"
  ].join("");
  document.head.appendChild(style);

  var lastW = -1;
  var lastH = -1;
  var timer = null;

  function evenSlots(count, start, end) {
    var slots = [];
    if (count <= 1) {
      slots.push((start + end) / 2);
      return slots;
    }
    var step = (end - start) / (count - 1);
    for (var i = 0; i < count; i++) slots.push(start + (step * i));
    return slots;
  }

  function spreadGraphNodes() {
    var el = document.getElementById("mynetwork");
    if (!el || typeof network === "undefined" || !network || typeof nodes === "undefined" || !nodes) {
      return false;
    }
    var width = el.clientWidth;
    var height = el.clientHeight;
    if (width < 40 || height < 40) return false;
    if (width === lastW && height === lastH) return true;

    var list = nodes.get();
    if (!list.length) return false;
    var positions = network.getPositions();
    var groups = {};
    list.forEach(function (node) {
      var level = node.level;
      if (level === undefined || level === null || level === "") level = 0;
      var key = String(level);
      if (!groups[key]) groups[key] = [];
      groups[key].push(String(node.id));
    });
    var levels = Object.keys(groups).map(Number).sort(function (a, b) { return a - b; });
    levels.forEach(function (level) {
      groups[String(level)].sort(function (a, b) {
        var ax = positions[a] ? positions[a].x : 0;
        var bx = positions[b] ? positions[b].x : 0;
        if (ax !== bx) return ax - bx;
        return a < b ? -1 : (a > b ? 1 : 0);
      });
    });

    var maxW = 0;
    var maxH = 0;
    list.forEach(function (node) {
      var bb = network.getBoundingBox(node.id);
      if (!bb) return;
      maxW = Math.max(maxW, bb.right - bb.left);
      maxH = Math.max(maxH, bb.bottom - bb.top);
    });
    if (maxW < 8 || maxH < 8) return false;

    var pad = 12;
    var nRows = levels.length;
    var widest = 1;
    levels.forEach(function (level) {
      widest = Math.max(widest, groups[String(level)].length);
    });
    // Keep boxes apart, then stretch the looser axis so the tree's box
    // matches the iframe. A uniform fit then fills both width and height.
    var minSpanX = widest <= 1 ? 0 : (widest - 1) * (maxW + pad);
    var minSpanY = nRows <= 1 ? 0 : (nRows - 1) * (maxH + pad);
    var innerW = Math.max(width - maxW - (pad * 2), 1);
    var innerH = Math.max(height - maxH - (pad * 2), 1);
    var spanX = widest <= 1 ? 0 : Math.max(minSpanX, innerW);
    var spanY = nRows <= 1 ? 0 : Math.max(minSpanY, innerH);
    if (spanX > 0 && spanY > 0) {
      var target = innerW / innerH;
      if ((spanX / spanY) > target) spanY = Math.max(spanY, spanX / target);
      else spanX = Math.max(spanX, spanY * target);
    }
    var ys = evenSlots(nRows, -spanY / 2, spanY / 2);
    levels.forEach(function (level, r) {
      var row = groups[String(level)];
      var rowX = evenSlots(row.length, -spanX / 2, spanX / 2);
      row.forEach(function (id, c) { network.moveNode(id, rowX[c], ys[r]); });
    });
    var contentW = spanX + maxW + (pad * 2);
    var contentH = spanY + maxH + (pad * 2);
    if (contentW <= width + 1 && contentH <= height + 1) {
      network.moveTo({position: {x: 0, y: 0}, scale: 1, animation: false});
    } else {
      network.fit({animation: false});
      if (network.getScale() > 1) {
        network.moveTo({position: {x: 0, y: 0}, scale: 1, animation: false});
      }
    }
    lastW = width;
    lastH = height;
    return true;
  }

  function attempt(n) {
    if (spreadGraphNodes()) return;
    if (n < 40) setTimeout(function () { attempt(n + 1); }, 50);
  }

  function schedule() {
    if (timer) clearTimeout(timer);
    timer = setTimeout(function () { attempt(0); }, 30);
  }

  requestAnimationFrame(function () {
    requestAnimationFrame(function () { attempt(0); });
  });
  window.addEventListener("resize", schedule);
  var frame = document.getElementById("mynetwork");
  if (frame && typeof ResizeObserver !== "undefined") {
    new ResizeObserver(function () {
      if (!frame || frame.clientWidth !== lastW || frame.clientHeight !== lastH) schedule();
    }).observe(frame);
  }
})();
"""


def spread_nodes_across_iframe(graph):
    """Return the graph with HTML that spaces each generation across the iframe."""
    original = graph.generate_html

    def generate_html(*args, **kwargs):
        html = original(*args, **kwargs)
        marker = "drawGraph();"
        if marker not in html:
            return html
        return html.replace(marker, marker + "\n" + _LAYOUT_SCRIPT, 1)

    graph.generate_html = generate_html
    return graph
