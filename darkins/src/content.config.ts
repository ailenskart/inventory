import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const journal = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/journal' }),
  schema: z.object({
    title: z.string(),
    date: z.coerce.date(),
    author: z.string().default('Darkins'),
    excerpt: z.string(),
    cover: z.string().optional().default(''),
    sourceUrl: z.string().optional(),
  }),
});

export const collections = { journal };
