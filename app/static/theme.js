/* ROSE — Theme toggle (dark / light / auto) */
(function () {
    var stored = localStorage.getItem('rose-theme');
    if (stored) document.documentElement.setAttribute('data-theme', stored);

    function isDark() {
        var th = document.documentElement.getAttribute('data-theme');
        if (th === 'dark')  return true;
        if (th === 'light') return false;
        return window.matchMedia('(prefers-color-scheme: dark)').matches;
    }

    document.addEventListener('DOMContentLoaded', function () {
        var nav = document.querySelector('nav.nav');
        if (!nav) return;

        var btn = document.createElement('button');
        btn.id = 'theme-toggle';
        btn.style.cssText = 'background:none;border:none;cursor:pointer;font-size:16px;'
                          + 'padding:2px 6px;border-radius:5px;line-height:1;opacity:0.65;';

        function refresh() {
            btn.textContent = isDark() ? '☀️' : '🌙';
            btn.title = isDark() ? 'Switch to light mode' : 'Switch to dark mode';
        }

        btn.addEventListener('click', function () {
            var next = isDark() ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', next);
            localStorage.setItem('rose-theme', next);
            refresh();
        });

        refresh();

        var spacer = nav.querySelector('.nav-spacer');
        if (spacer) {
            nav.insertBefore(btn, spacer.nextSibling);
        } else {
            nav.appendChild(btn);
        }
    });
})();
