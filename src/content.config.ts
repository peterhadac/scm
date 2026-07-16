import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

// Plain replacement for Starlight's docsLoader/docsSchema (issue #121) —
// only the still-live prose pages remain here (drinks, brew-methods,
// ai-coffee, about-data); pages with bespoke UI (coffees, this-week,
// origins, map, landing) are hand-written .astro files that don't go
// through this collection at all.
export const collections = {
  docs: defineCollection({
    loader: glob({ pattern: '**/*.mdx', base: './src/content/docs' }),
    schema: z.object({
      title: z.string(),
      description: z.string(),
    }),
  }),
};
