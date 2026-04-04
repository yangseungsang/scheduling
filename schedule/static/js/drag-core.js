/**
 * Drag infrastructure — target finding, ghost, highlight, location guides.
 * Registers helpers on window.ScheduleApp.
 */
(function (App) {
  'use strict';

  // Private state
  var weekGuideEl = null;
  var weekGuideLocs = null;
  var highlighted = null;
  var highlightedZone = null;

  // Aliases from utils.js
  var GRID_MINUTES = App.GRID_MINUTES;
  var SLOT_HEIGHT = App.SLOT_HEIGHT;
  var isReadonly = App.isReadonly;

  // =====================================================================
  // Block visibility toggle — hide all blocks so elementFromPoint hits time-slots
  // =====================================================================
  function hideAllBlocks() {
    document.querySelectorAll('.schedule-block, .month-block-item').forEach(function (b) {
      b.style.pointerEvents = 'none';
    });
  }
  function showAllBlocks() {
    document.querySelectorAll('.schedule-block, .month-block-item').forEach(function (b) {
      b.style.pointerEvents = '';
    });
  }

  // =====================================================================
  // Week location guides — show location zones during drag
  // =====================================================================
  function getLocations() {
    var locs = [];
    document.querySelectorAll('.loc-filter-btn[data-loc-id]').forEach(function (b) {
      if (b.dataset.locId) locs.push({ id: b.dataset.locId, name: b.textContent.trim(), color: '' });
    });
    document.querySelectorAll('.loc-filter-btn[data-loc-id]').forEach(function (b) {
      if (!b.dataset.locId) return;
      var dot = b.querySelector('.loc-filter-dot');
      for (var i = 0; i < locs.length; i++) {
        if (locs[i].id === b.dataset.locId && dot) {
          locs[i].color = dot.style.background || dot.style.backgroundColor || '#94a3b8';
          break;
        }
      }
    });
    return locs;
  }

  function getWeekGuideLocs() {
    if (weekGuideLocs) return weekGuideLocs;
    var locs = getLocations();
    if (locs.length === 0) return locs;
    // Check if "전체" is active
    var allBtn = document.querySelector('.loc-filter-btn.active[data-loc-id=""]');
    if (!allBtn) {
      // Filter to only active locations
      var activeIds = {};
      document.querySelectorAll('.loc-filter-btn.active[data-loc-id]').forEach(function (b) {
        if (b.dataset.locId) activeIds[b.dataset.locId] = true;
      });
      if (Object.keys(activeIds).length > 0) {
        locs = locs.filter(function (l) { return activeIds[l.id]; });
      }
    }
    weekGuideLocs = locs;
    return locs;
  }

  function ensureWeekGuide(slotsEl) {
    // Already showing on this column
    if (weekGuideEl && weekGuideEl.parentNode === slotsEl) return weekGuideEl;
    // Remove from previous column
    if (weekGuideEl) { weekGuideEl.remove(); weekGuideEl = null; }

    var locs = getWeekGuideLocs();
    if (locs.length <= 1) return null;

    var overlay = document.createElement('div');
    overlay.className = 'week-loc-guide-overlay';
    overlay.style.cssText = 'position:absolute;top:0;left:0;right:0;bottom:0;z-index:8;pointer-events:none;display:flex;';
    for (var i = 0; i < locs.length; i++) {
      var zone = document.createElement('div');
      zone.className = 'week-loc-guide-zone';
      zone.dataset.locationId = locs[i].id;
      zone.style.cssText = 'flex:1;border-right:1px dashed ' + locs[i].color + ';position:relative;';
      if (i === locs.length - 1) zone.style.borderRight = 'none';
      var label = document.createElement('div');
      label.className = 'week-loc-guide-label';
      label.textContent = locs[i].name;
      label.style.cssText = 'position:sticky;top:0;font-size:0.6rem;font-weight:600;color:' + locs[i].color +
        ';text-align:center;padding:2px 0;background:rgba(255,255,255,0.85);border-bottom:2px solid ' + locs[i].color + ';white-space:nowrap;overflow:hidden;text-overflow:ellipsis;';
      zone.appendChild(label);
      overlay.appendChild(zone);
    }
    slotsEl.appendChild(overlay);
    weekGuideEl = overlay;
    return overlay;
  }

  function showWeekLocationGuides() { /* no-op: guides are now shown per-column on hover */ }
  function hideWeekLocationGuides() {
    if (weekGuideEl) { weekGuideEl.remove(); weekGuideEl = null; }
  }

  function resolveWeekLocation(x, slot) {
    if (slot.dataset.locationId) return slot.dataset.locationId;
    var slotsEl = slot.closest('.week-day-slots');
    if (!slotsEl) return '';
    var overlay = ensureWeekGuide(slotsEl);
    if (!overlay) return '';
    var zones = overlay.querySelectorAll('.week-loc-guide-zone');
    if (zones.length === 0) return '';
    var rect = slotsEl.getBoundingClientRect();
    var relX = x - rect.left;
    var zoneWidth = rect.width / zones.length;
    var idx = Math.max(0, Math.min(zones.length - 1, Math.floor(relX / zoneWidth)));
    return zones[idx].dataset.locationId || '';
  }

  // =====================================================================
  // Find target under cursor
  // =====================================================================
  function findTarget(x, y) {
    var el = document.elementFromPoint(x, y);
    if (!el) return null;
    var slot = el.closest('.time-slot');
    if (slot && slot.dataset.date && slot.dataset.time) {
      var locId = slot.dataset.locationId || resolveWeekLocation(x, slot);
      return { type: 'slot', date: slot.dataset.date, time: slot.dataset.time, locationId: locId, el: slot };
    }
    var cell = el.closest('.month-day-cell[data-date]');
    if (cell) {
      return { type: 'month', date: cell.dataset.date, el: cell };
    }
    var queue = el.closest('#task-queue');
    if (queue) {
      return { type: 'queue', el: queue };
    }
    return null;
  }

  // =====================================================================
  // Ghost element
  // =====================================================================
  function createGhost(text, color, w, h) {
    var g = document.createElement('div');
    g.textContent = text;
    g.style.cssText =
      'position:fixed;z-index:9999;pointer-events:none;opacity:0.8;' +
      'padding:4px 8px;border-radius:4px;font-size:0.75rem;color:#fff;' +
      'overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.3);' +
      'background:' + (color || '#0d6efd') + ';' +
      'width:' + (w || 120) + 'px;' +
      (h ? 'height:' + h + 'px;' : '');
    document.body.appendChild(g);
    return g;
  }

  // =====================================================================
  // Highlight
  // =====================================================================
  function setHighlight(target, x) {
    clearHighlight();
    if (!target || !target.el) {
      // Cursor left the grid — remove guide
      hideWeekLocationGuides();
      return;
    }
    // For weekly view with location guides, highlight the zone instead of the full slot
    if (target.type === 'slot' && target.locationId && !target.el.dataset.locationId) {
      var slotsEl = target.el.closest('.week-day-slots');
      if (slotsEl) {
        var overlay = slotsEl.querySelector('.week-loc-guide-overlay');
        if (overlay) {
          var zones = overlay.querySelectorAll('.week-loc-guide-zone');
          for (var i = 0; i < zones.length; i++) {
            if (zones[i].dataset.locationId === target.locationId) {
              zones[i].classList.add('week-loc-guide-active');
              highlightedZone = zones[i];
              break;
            }
          }
        }
      }
    } else {
      // Not on a weekly slot — remove guide from previous column
      hideWeekLocationGuides();
    }
    target.el.classList.add('drag-over');
    highlighted = target.el;
  }
  function clearHighlight() {
    if (highlighted) highlighted.classList.remove('drag-over');
    highlighted = null;
    if (highlightedZone) highlightedZone.classList.remove('week-loc-guide-active');
    highlightedZone = null;
  }

  // =====================================================================
  // Generic drag helper
  // =====================================================================
  function startDrag(e, opts) {
    if (e.button !== 0) return;
    if (isReadonly()) return;
    e.preventDefault();

    var startX = e.clientX, startY = e.clientY;
    var dragging = false;
    var ghost = null;

    function onMove(ev) {
      ev.preventDefault();
      var dx = ev.clientX - startX, dy = ev.clientY - startY;
      if (!dragging && Math.abs(dx) + Math.abs(dy) < 5) return;

      if (!dragging) {
        dragging = true;
        ghost = createGhost(opts.ghostText, opts.ghostColor, opts.ghostWidth, opts.ghostHeight);
        hideAllBlocks();
        showWeekLocationGuides();
        if (opts.sourceEl) opts.sourceEl.style.opacity = '0.3';
        document.body.style.userSelect = 'none';
        document.body.style.cursor = 'grabbing';
      }

      ghost.style.left = ev.clientX - (ghost.offsetWidth / 2) + 'px';
      ghost.style.top = ev.clientY - 10 + 'px';

      var target = findTarget(ev.clientX, ev.clientY);
      setHighlight(target, ev.clientX);
    }

    function onUp(ev) {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);

      var target = null;
      if (dragging) {
        target = findTarget(ev.clientX, ev.clientY);
      }

      clearHighlight();
      hideWeekLocationGuides();
      weekGuideLocs = null;
      showAllBlocks();
      if (ghost) ghost.remove();
      if (opts.sourceEl) opts.sourceEl.style.opacity = '';
      document.body.style.userSelect = '';
      document.body.style.cursor = '';

      if (!dragging) return;

      if (target) opts.onDrop(target);
    }

    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }

  // Register on App
  App.hideAllBlocks = hideAllBlocks;
  App.showAllBlocks = showAllBlocks;
  App.getLocations = getLocations;
  App.getWeekGuideLocs = getWeekGuideLocs;
  App.ensureWeekGuide = ensureWeekGuide;
  App.resolveWeekLocation = resolveWeekLocation;
  App.showWeekLocationGuides = showWeekLocationGuides;
  App.hideWeekLocationGuides = hideWeekLocationGuides;
  App.findTarget = findTarget;
  App.createGhost = createGhost;
  App.setHighlight = setHighlight;
  App.clearHighlight = clearHighlight;
  App.startDrag = startDrag;
})(window.ScheduleApp);
