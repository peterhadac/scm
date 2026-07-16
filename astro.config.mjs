import { defineConfig } from 'astro/config';
import mdx from '@astrojs/mdx';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  site: 'https://peterhadac.github.io',
  base: '/scm',
  integrations: [mdx(), sitemap()],
  // Tailwind is scoped to shadcn-style components only (see
  // src/styles/tailwind.css) — Preflight is intentionally NOT loaded here,
  // since it would reset typography/spacing globally across the
  // still-Starlight-rendered docs pages this migration hasn't reached yet.
  vite: {
    plugins: [tailwindcss()],
  },
});
