(function () {
  function closest(el, selector) {
    while (el && el.nodeType === 1) {
      if (el.matches(selector)) return el
      el = el.parentElement
    }
    return null
  }

  function setupProfileMenu() {
    var wrap = document.querySelector('[data-profile-wrap]')
    if (!wrap) return
    var toggle = wrap.querySelector('[data-profile-toggle]')
    var menu = wrap.querySelector('[data-profile-menu]')
    if (!toggle || !menu) return

    function closeMenu() {
      menu.hidden = true
    }

    function openMenu() {
      menu.hidden = false
    }

    toggle.addEventListener('click', function (e) {
      e.preventDefault()
      if (menu.hidden) openMenu()
      else closeMenu()
    })

    document.addEventListener('click', function (e) {
      if (!wrap.contains(e.target)) closeMenu()
    }, { capture: true })

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeMenu()
    })
  }

  function setupActions() {
    document.addEventListener('click', function (e) {
      var actionEl = closest(e.target, '[data-action]')
      if (!actionEl) return
      var action = actionEl.getAttribute('data-action')
      if (action === 'logout') {
        e.preventDefault()
        window.location.href = '/logout/'
      }
    })
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      setupProfileMenu()
      setupActions()
    })
  } else {
    setupProfileMenu()
    setupActions()
  }
})()
