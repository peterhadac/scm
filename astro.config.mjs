import { defineConfig } from 'astro/config';
import mdx from '@astrojs/mdx';
import sitemap from '@astrojs/sitemap';

export default defineConfig({
  site: 'https://peterhadac.github.io',
  base: '/scm',
  integrations: [mdx(), sitemap()],
});
