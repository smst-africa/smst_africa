/* Adverts inside the SmSt apps.
   The wide card moves itself above the first table on the page. The tall card
   only opens when the view changes, and never blocks the page. */

(function () {
  'use strict';

  var lastPath = window.location.pathname + window.location.search;

  function placeShelf() {
    var shelf = document.querySelector('[data-vert-shelf]');
    if (!shelf) {
      return;
    }
    var root = document.getElementById('mainContent');
    var table = root && root.querySelector('.table-scroll, table');
    if (!table) {
      return;
    }
    var box = table.closest('.table-scroll') || table;
    box.parentNode.insertBefore(shelf, box);
    shelf.hidden = false;
  }

  function showPop() {
    var pop = document.querySelector('[data-vert-pop]');
    if (pop) {
      pop.hidden = false;
    }
  }

  function closePop(pop) {
    if (pop) {
      pop.hidden = true;
    }
  }

  function afterSwap(event) {
    if (!event.detail.target || event.detail.target.id !== 'mainContent') {
      return;
    }
    placeShelf();
    var path = window.location.pathname + window.location.search;
    if (path !== lastPath) {
      lastPath = path;
      showPop();
    }
  }

  document.addEventListener('click', function (event) {
    var close = event.target.closest('[data-vert-close]');
    if (close) {
      closePop(close.closest('[data-vert-pop]'));
    }
  });

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') {
      closePop(document.querySelector('[data-vert-pop]'));
    }
  });

  document.addEventListener('submit', function (event) {
    if (
      event.target.matches('[data-vert-delete]') &&
      !window.confirm('Remove this vert?')
    ) {
      event.preventDefault();
    }
  });

  document.addEventListener('htmx:afterSwap', afterSwap);
  document.addEventListener('htmx:historyRestore', function () {
    lastPath = window.location.pathname + window.location.search;
    placeShelf();
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', placeShelf);
  } else {
    placeShelf();
  }
})();
