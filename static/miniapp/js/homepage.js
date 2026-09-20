// Public pages — mobile nav toggle for the floating pill nav.
(function () {
  var toggle = document.querySelector('.cw-nav-toggle');
  var panel = document.getElementById('cw-mobile-nav');
  if (!toggle || !panel) return;

  function setOpen(open) {
    panel.classList.toggle('open', open);
    toggle.classList.toggle('open', open);
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  toggle.addEventListener('click', function () {
    setOpen(!panel.classList.contains('open'));
  });

  panel.querySelectorAll('a').forEach(function (link) {
    link.addEventListener('click', function () { setOpen(false); });
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') setOpen(false);
  });
})();

// Neighbourhood pages: curated-shortlist and guide-download forms.
(function () {
  document.querySelectorAll('[data-lead-form]').forEach(function (form) {
    var msg = form.querySelector('.cw-form-msg');
    var button = form.querySelector('button[type=submit]');

    function say(text, kind, html) {
      msg.hidden = false;
      msg.className = 'cw-form-msg ' + kind;
      if (html) { msg.innerHTML = html; } else { msg.textContent = text; }
    }

    function firstError(errors) {
      var keys = Object.keys(errors || {});
      if (!keys.length) return 'Please check your details and try again.';
      var e = errors[keys[0]];
      return (Array.isArray(e) ? e[0] : e).message || (Array.isArray(e) ? e[0] : e) || 'Please check your details and try again.';
    }

    form.addEventListener('submit', function (event) {
      event.preventDefault();
      msg.hidden = true;
      if (!form.email.value || !form.first_name.value || !form.last_name.value) {
        say('Please add your name and email.', 'error'); return;
      }
      if (!form.consent.checked) {
        say('Please tick the box so we can contact you.', 'error'); return;
      }
      button.disabled = true;
      var original = button.textContent;
      button.textContent = 'Sending...';

      fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin'
      })
        .then(function (r) { return r.json().then(function (data) { return { ok: r.ok, data: data }; }); })
        .then(function (res) {
          if (res.ok && res.data.success) {
            var isGuide = form.dataset.intent === 'guide';
            form.reset();
            if (isGuide && res.data.download_url) {
              var a = document.createElement('a');
              a.href = res.data.download_url; a.target = '_blank'; a.rel = 'noopener';
              a.textContent = 'Download ' + (res.data.title || 'the guide');
              say('', 'ok', 'Thank you. ');
              msg.appendChild(a);
            } else if (form.dataset.intent === 'access') {
              say('Thank you. An adviser will contact you within 2 business days about access.', 'ok');
            } else {
              say('Thank you. An adviser will be in touch shortly with your shortlist.', 'ok');
            }
            button.textContent = 'Sent';
          } else {
            say(res.data.error || firstError(res.data.errors), 'error');
            button.disabled = false; button.textContent = original;
          }
        })
        .catch(function () {
          say('Something went wrong. Please try again in a moment.', 'error');
          button.disabled = false; button.textContent = original;
        });
    });
  });
})();
