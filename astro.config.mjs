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
