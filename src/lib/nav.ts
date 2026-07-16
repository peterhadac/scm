// Nav data mirroring the Starlight sidebar in astro.config.mjs (issue #121).
// Kept here so both the old Starlight sidebar and the new Layout.astro nav
// can eventually read from one source; for now only Layout.astro uses it.
export interface NavLink {
  en: string;
  sk: string;
  href: string;
}

export interface NavGroup {
  en: string;
  sk: string;
  items: NavLink[];
}

export type NavEntry = NavLink | NavGroup;

export function isNavGroup(entry: NavEntry): entry is NavGroup {
  return 'items' in entry;
}

export const NAV: NavEntry[] = [
  { en: 'This week', sk: 'Tento týždeň', href: '/this-week/' },
  { en: 'AI Coffee choose', sk: 'AI výber kávy', href: '/ai-coffee/' },
  { en: 'Roaster map', sk: 'Mapa pražiarní', href: '/map/' },
  {
    en: 'Roasted coffee',
    sk: 'Pražená káva',
    items: [
      { en: 'All', sk: 'Všetky', href: '/coffees/' },
      { en: 'Filter coffees', sk: 'Filter kávy', href: '/coffees/filter/' },
      { en: 'Espresso coffees', sk: 'Espresso kávy', href: '/coffees/espresso/' },
      { en: 'Blends', sk: 'Zmesi', href: '/coffees/blends/' },
      { en: 'Nespresso capsules', sk: 'Nespresso kapsuly', href: '/coffees/nespresso/' },
      { en: 'Drip bags', sk: 'Drip bagy', href: '/coffees/drip-bags/' },
      { en: 'By origin', sk: 'Podľa pôvodu', href: '/origins/' },
    ],
  },
  {
    en: 'Drinks',
    sk: 'Nápoje',
    items: [
      { en: 'Espresso Cube Tonic', sk: 'Espresso Cube Tonic', href: '/drinks/espresso-cube-tonic/' },
      { en: 'Espresso Cube Cappuccino', sk: 'Espresso Cube Cappuccino', href: '/drinks/espresso-cube-cappuccino/' },
      { en: 'Filterccino', sk: 'Filterccino', href: '/drinks/filterccino/' },
      { en: 'Filter Ice Cappuccino', sk: 'Filter Ice Cappuccino', href: '/drinks/filter-ice-cappuccino/' },
      { en: 'French Press', sk: 'French Press', href: '/drinks/french-press/' },
    ],
  },
  {
    en: 'Brew Methods',
    sk: 'Spôsoby prípravy',
    items: [
      { en: 'V60', sk: 'V60', href: '/brew-methods/v60/' },
      { en: 'Aeropress', sk: 'Aeropress', href: '/brew-methods/aeropress/' },
      { en: 'French Press', sk: 'French Press', href: '/brew-methods/french-press/' },
      { en: 'Cold Brew', sk: 'Studená káva', href: '/brew-methods/cold-brew/' },
    ],
  },
  { en: 'About the data', sk: 'O dátach', href: '/about-data/' },
];
