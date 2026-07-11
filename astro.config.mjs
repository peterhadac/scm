import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import md3Theme from 'starlight-theme-md3';

export default defineConfig({
  site: 'https://peterhadac.github.io',
  base: '/scm',
  integrations: [
    starlight({
      title: 'Slovak Coffee Map',
      locales: {
        root: { label: 'English', lang: 'en' },
        sk: { label: 'Slovensky', lang: 'sk' },
      },
      components: {
        SiteTitle: './src/components/SiteTitle.astro',
      },
      head: [
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
        {
          label: 'Roasted coffee',
          translations: { sk: 'Pražená káva' },
          items: [
            { label: 'All', translations: { sk: 'Všetky' }, link: '/coffees/' },
            { label: 'Filter coffees', translations: { sk: 'Filter kávy' }, link: '/coffees/filter/' },
            { label: 'Espresso coffees', translations: { sk: 'Espresso kávy' }, link: '/coffees/espresso/' },
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
            { label: 'FTS - Filter To Survive', link: '/drinks/v60/' },
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
      ],
      customCss: ['./src/styles/custom.css'],
      social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/peterhadac/scm' }],
    }),
  ],
});
