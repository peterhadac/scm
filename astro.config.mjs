import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import md3Theme from 'starlight-theme-md3';

// GoatCounter site code (issue #56): analytics scripts are only emitted
// when GOATCOUNTER_CODE is set at build time (pages.yml passes the
// GOATCOUNTER_CODE repository variable), so local dev builds and forks
// never report into the production property. GoatCounter is cookie-less
// and GDPR-friendly — no consent banner needed.
const goatcounterCode = process.env.GOATCOUNTER_CODE;
const goatcounterHead = goatcounterCode
  ? [
      {
        tag: 'script',
        attrs: {
          'data-goatcounter': `https://${goatcounterCode}.goatcounter.com/count`,
          async: true,
          src: '//gc.zgo.at/count.js',
        },
      },
      {
        // Outbound-click events ("out:<host><path>"): the numbers behind
        // any referral/sponsorship conversation with a roaster. count.js
        // only tracks pageviews by itself.
        tag: 'script',
        content: `
          document.addEventListener('click', function (e) {
            var a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
            if (!a) return;
            var url;
            try { url = new URL(a.href); } catch (err) { return; }
            if (url.host === window.location.host) return;
            if (window.goatcounter && window.goatcounter.count) {
              window.goatcounter.count({
                path: 'out:' + url.host + url.pathname,
                title: (a.textContent || '').trim().slice(0, 100),
                event: true,
              });
            }
          });
        `,
      },
    ]
  : [];

export default defineConfig({
  site: 'https://peterhadac.github.io',
  base: '/scm',
  integrations: [
    starlight({
      title: 'Slovak Coffee Map',
      plugins: [md3Theme({ seed: '#FF6037', variant: 'tonalSpot' })],
      locales: {
        root: { label: 'English', lang: 'en' },
        sk: { label: 'Slovensky', lang: 'sk' },
      },
      components: {
        SiteTitle: './src/components/SiteTitle.astro',
        Footer: './src/components/Footer.astro',
      },
      head: [
        ...goatcounterHead,
        { tag: 'script', attrs: { src: 'https://storage.ko-fi.com/cdn/scripts/overlay-widget.js' } },
        {
          tag: 'script',
          content: `
            window.addEventListener('load', function () {
              kofiWidgetOverlay.draw('slovakcoffeemap', {
                type: 'floating-chat',
                'floating-chat.donateButton.text': 'Donate',
                'floating-chat.donateButton.background-color': '#ff5f5f',
                'floating-chat.donateButton.text-color': '#fff',
              });
              // Ko-fi injects its iframe without a title attribute — a real
              // screen-reader gap and a weight-7 Lighthouse a11y audit
              // (frame-title) that fails whenever the widget loads before
              // the audit runs. Title it ourselves as soon as it appears;
              // the observer disconnects once done.
              var titleKofiFrames = function () {
                var frames = document.querySelectorAll(
                  '[id*="kofi"] iframe:not([title]), iframe[id*="kofi"]:not([title])'
                );
                frames.forEach(function (f) { f.title = 'Ko-fi donations widget'; });
                return frames.length > 0;
              };
              if (!titleKofiFrames()) {
                var observer = new MutationObserver(function () {
                  if (titleKofiFrames()) observer.disconnect();
                });
                observer.observe(document.body, { childList: true, subtree: true });
              }
            });
          `,
        },
        {
          // Persists the user's language choice (localStorage, since this is
          // a static site with no server to set a cookie) across page
          // navigation and repeat visits. Starlight's own language picker
          // (LanguageSelect.astro) is purely URL-based with no memory of its
          // own — see docs/superpowers/specs for the reasoning. Every page
          // under this site mirrors its English/Slovak counterpart 1:1, so a
          // stored preference can always be applied by swapping the `/sk`
          // path segment right after the `/scm` base.
          tag: 'script',
          content: `
            (function () {
              var BASE = '/scm';
              var KEY = 'scm-lang';
              var skPrefix = BASE + '/sk';
              var path = window.location.pathname;
              var isSk = path === skPrefix || path.indexOf(skPrefix + '/') === 0;
              var stored = null;
              try { stored = localStorage.getItem(KEY); } catch (e) {}

              if (stored === 'sk' && !isSk) {
                window.location.replace(skPrefix + path.slice(BASE.length));
                return;
              }
              if (stored === 'en' && isSk) {
                var rest = path.slice(skPrefix.length);
                window.location.replace(BASE + (rest || '/'));
                return;
              }

              document.addEventListener('change', function (e) {
                var target = e.target;
                if (!target || target.tagName !== 'SELECT' || !target.closest('starlight-lang-select')) return;
                var newPath = target.value;
                var newIsSk = newPath === skPrefix || newPath.indexOf(skPrefix + '/') === 0;
                try { localStorage.setItem(KEY, newIsSk ? 'sk' : 'en'); } catch (e2) {}
              });
            })();
          `,
        },
      ],
      sidebar: [
        { label: 'This week', translations: { sk: 'Tento týždeň' }, link: '/this-week/' },
        {
          label: 'Roasted coffee',
          translations: { sk: 'Pražená káva' },
          items: [
            { label: 'All', translations: { sk: 'Všetky' }, link: '/coffees/' },
            { label: 'Filter coffees', translations: { sk: 'Filter kávy' }, link: '/coffees/filter/' },
            { label: 'Espresso coffees', translations: { sk: 'Espresso kávy' }, link: '/coffees/espresso/' },
            { label: 'Blends', translations: { sk: 'Zmesi' }, link: '/coffees/blends/' },
            { label: 'Nespresso capsules', translations: { sk: 'Nespresso kapsuly' }, link: '/coffees/nespresso/' },
            { label: 'Drip bags', translations: { sk: 'Drip bagy' }, link: '/coffees/drip-bags/' },
            { label: 'By origin', translations: { sk: 'Podľa pôvodu' }, link: '/origins/' },
          ]
        },
        {
          label: 'Drinks',
          translations: { sk: 'Nápoje' },
          items: [
            { label: 'Espresso Cube Tonic', link: '/drinks/espresso-cube-tonic/' },
            { label: 'Espresso Cube Cappuccino', link: '/drinks/espresso-cube-cappuccino/' },
            { label: 'Filterccino', link: '/drinks/filterccino/' },
            { label: 'Filter Ice Cappuccino', link: '/drinks/filter-ice-cappuccino/' },
            { label: 'French Press', link: '/drinks/french-press/' },
          ],
        },
        {
          label: 'Brew Methods',
          translations: { sk: 'Spôsoby prípravy' },
          items: [
            { label: 'V60', link: '/brew-methods/v60/' },
            { label: 'Aeropress', link: '/brew-methods/aeropress/' },
            { label: 'French Press', link: '/brew-methods/french-press/' },
            { label: 'Cold Brew', translations: { sk: 'Studená káva' }, link: '/brew-methods/cold-brew/' },
          ],
        },
        { label: 'About the data', translations: { sk: 'O dátach' }, link: '/about-data/' },
      ],
      customCss: ['./src/styles/custom.css'],
      social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/peterhadac/scm' }],
    }),
  ],
});
