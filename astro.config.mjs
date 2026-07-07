import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import md3Theme from 'starlight-theme-md3';

export default defineConfig({
  site: 'https://peterhadac.github.io',
  base: '/scm',
  integrations: [
    starlight({
      title: 'Slovak Coffee Map',
      plugins: [md3Theme({ seed: '#FF6037', variant: 'tonalSpot' })],
      components: {
        SiteTitle: './src/components/SiteTitle.astro',
      },
      head: [
        { tag: 'link', attrs: { rel: 'preconnect', href: 'https://fonts.googleapis.com' } },
        { tag: 'link', attrs: { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: true } },
        {
          tag: 'link',
          attrs: {
            rel: 'stylesheet',
            href: 'https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500&display=swap',
          },
        },
      ],
      sidebar: [
        {
          label: 'Coffees',
          items: [
            { label: 'All', link: '/coffees/' },
            { label: 'Filter coffees', link: '/coffees/filter/' },
            { label: 'Espresso coffees', link: '/coffees/espresso/' },
          ]
        },
        {
          label: 'Brew Methods',
          items: [
            { label: 'V60', link: '/brew-methods/v60/' },
            { label: 'French Press', link: '/brew-methods/french-press/' },
          ],
        },
      ],
      customCss: ['./src/styles/custom.css'],
      social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/peterhadac/scm' }],
    }),
  ],
});
