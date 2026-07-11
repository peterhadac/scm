// Client-side favourite-roastery storage. Coffees are re-scraped and
// re-flattened at build time with no server-side user account to persist
// against, so favourites live only in the visitor's own browser
// (localStorage), keyed by the stable roaster `slug` from roasters.yaml
// rather than the display name, which could change on a rename.
const STORAGE_KEY = 'scm-favorite-roasters';
const CHANGE_EVENT = 'scm-favorites-change';

function readSlugs(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((s): s is string => typeof s === 'string') : [];
  } catch {
    return [];
  }
}

function writeSlugs(slugs: string[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...new Set(slugs)]));
  } catch {
    // Storage unavailable (private-browsing quota, disabled storage, etc.) —
    // favouriting silently becomes a no-op rather than throwing.
  }
  // Same-tab listeners (e.g. the coffee table and a favourites toggle on the
  // same page) don't get a native `storage` event — that only fires in
  // *other* tabs — so broadcast one ourselves for this tab too.
  window.dispatchEvent(new CustomEvent(CHANGE_EVENT));
}

export function getFavoriteSlugs(): string[] {
  return readSlugs();
}

export function isFavoriteRoaster(slug: string): boolean {
  return readSlugs().includes(slug);
}

export function setFavoriteRoaster(slug: string, favorite: boolean): void {
  const current = readSlugs();
  const next = favorite ? [...current, slug] : current.filter((s) => s !== slug);
  writeSlugs(next);
}

export function toggleFavoriteRoaster(slug: string): boolean {
  const next = !isFavoriteRoaster(slug);
  setFavoriteRoaster(slug, next);
  return next;
}

// Fires on any favourites change, in this tab (custom event) or another tab
// with the same site open (native `storage` event). Returns an unsubscribe
// function.
export function onFavoritesChange(callback: () => void): () => void {
  const customHandler = () => callback();
  const storageHandler = (e: StorageEvent) => {
    if (e.key === STORAGE_KEY) callback();
  };
  window.addEventListener(CHANGE_EVENT, customHandler);
  window.addEventListener('storage', storageHandler);
  return () => {
    window.removeEventListener(CHANGE_EVENT, customHandler);
    window.removeEventListener('storage', storageHandler);
  };
}
