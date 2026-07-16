// Lang detection for pages rendered outside Starlight (issue #121). Every
// page has a 1:1 /sk/ mirror at the same path suffix, so the URL prefix
// alone is enough — no routing integration needed.
import type { Lang } from './i18n';

export function langFromPath(pathname: string): Lang {
  const base = import.meta.env.BASE_URL.replace(/\/$/, '');
  const rest = pathname.startsWith(base) ? pathname.slice(base.length) : pathname;
  return rest === '/sk' || rest.startsWith('/sk/') ? 'sk' : 'en';
}

// Strips a leading /sk (if present) so the remainder can be re-prefixed for
// the other locale, e.g. localePath('/coffees/', 'sk') -> '/sk/coffees/'.
export function localePath(path: string, lang: Lang): string {
  const withoutSk = path === '/sk' || path.startsWith('/sk/') ? path.slice(3) || '/' : path;
  return lang === 'sk' ? `/sk${withoutSk === '/' ? '/' : withoutSk}` : withoutSk;
}
