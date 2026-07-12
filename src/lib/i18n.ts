// EN/SK translation tables for the coffee table UI chrome and the
// controlled-vocabulary data fields (origin/process/roast_type). Starlight's
// own chrome (search, nav, pagination, 404...) ships a complete `sk`
// translation already (see node_modules/@astrojs/starlight/translations/sk.json)
// and needs nothing here. Scraped proper nouns (coffee `name`, `roaster`) are
// never translated — they link out to the roaster's own untranslated page.
export type Lang = 'en' | 'sk';

// Slovak nouns decline by count (1 / 2-4 / 0,5+) unlike English's simple
// singular/plural — a shared helper so every counted phrase in the sk table
// below applies the same rule instead of re-deriving it per word.
function skCount(n: number, one: string, few: string, many: string): string {
  if (n === 1) return one;
  if (n >= 2 && n <= 4) return few;
  return many;
}

export const UI = {
  en: {
    search: 'Search',
    searchPlaceholder: 'Coffee or roaster…',
    filters: 'Filters',
    roaster: 'Roaster',
    origin: 'Origin',
    process: 'Process',
    roast: 'Roast',
    all: 'All',
    clear: 'Clear',
    coffee: 'Coffee',
    weight: 'Weight',
    price: 'Price',
    per100g: 'Per 100g',
    from: 'from',
    updated: 'updated',
    emptyFiltered: 'No coffees match the selected filters.',
    emptyNoData: 'No coffees available right now — check back soon.',
    processLegendLabel: 'Process:',
    bestValue: 'best value',
    bestValueTitle: 'Lowest price per 100g',
    bestValueDesc: '= lowest €/100g',
    processColourKey: 'Process colour key',
    staleTitle: (lastSeen: string) => `Price last confirmed over 3 weeks ago (last checked ${lastSeen})`,
    staleAriaLabel: (lastSeen: string) => `Price may be outdated — last confirmed ${lastSeen}`,
    coffeeCount: (n: number) => `${n} coffee${n !== 1 ? 's' : ''}`,
    roasterCount: (n: number) => `${n} roaster${n !== 1 ? 's' : ''}`,
  },
  sk: {
    search: 'Hľadať',
    searchPlaceholder: 'Káva alebo pražiareň…',
    filters: 'Filtre',
    roaster: 'Pražiareň',
    origin: 'Pôvod',
    process: 'Spracovanie',
    roast: 'Praženie',
    all: 'Všetky',
    clear: 'Zrušiť',
    coffee: 'Káva',
    weight: 'Hmotnosť',
    price: 'Cena',
    per100g: 'Za 100 g',
    from: 'od',
    updated: 'aktualizované',
    emptyFiltered: 'Žiadna káva nezodpovedá zvoleným filtrom.',
    emptyNoData: 'Momentálne nie sú dostupné žiadne kávy — skúste to neskôr.',
    processLegendLabel: 'Spracovanie:',
    bestValue: 'najlepšia cena',
    bestValueTitle: 'Najnižšia cena za 100 g',
    bestValueDesc: '= najnižšia €/100 g',
    processColourKey: 'Farebné označenie spracovania',
    staleTitle: (lastSeen: string) => `Cena naposledy overená pred viac ako 3 týždňami (posledná kontrola ${lastSeen})`,
    staleAriaLabel: (lastSeen: string) => `Cena môže byť neaktuálna — posledná kontrola ${lastSeen}`,
    coffeeCount: (n: number) => `${n} ${skCount(n, 'káva', 'kávy', 'káv')}`,
    roasterCount: (n: number) => `${n} ${skCount(n, 'pražiareň', 'pražiarne', 'pražiarní')}`,
  },
} satisfies Record<Lang, Record<string, string | ((...args: never[]) => string)>>;

// Display labels for controlled-vocabulary fields, keyed by the canonical
// English value stored in data/products.yaml (see CLAUDE.md's Data Schema).
// These only change the *rendered* text — filtering/sorting keeps comparing
// the stable English key (see CoffeeTable.astro), so switching language
// never changes which rows match a given filter.
export const PROCESS_LABELS: Record<string, Record<Lang, string>> = {
  washed: { en: 'Washed', sk: 'Umytá' },
  natural: { en: 'Natural', sk: 'Prírodná' },
  honey: { en: 'Honey', sk: 'Medová' },
  'wet-hulled': { en: 'Wet-hulled', sk: 'Mokro lúpaná' },
  anaerobic: { en: 'Anaerobic', sk: 'Anaeróbna' },
  'carbonic-maceration': { en: 'Carbonic maceration', sk: 'Karbonická macerácia' },
  other: { en: 'Other', sk: 'Iné' },
};

export const ROAST_TYPE_LABELS: Record<string, Record<Lang, string>> = {
  filter: { en: 'Filter', sk: 'Filter' },
  espresso: { en: 'Espresso', sk: 'Espresso' },
  // "Nespresso" is a brand/format name and "drip bag" the borrowed term
  // Slovak roasters themselves use — neither gets a translated label.
  nespresso: { en: 'Nespresso', sk: 'Nespresso' },
  'drip-bag': { en: 'Drip bag', sk: 'Drip bag' },
};

// Proper-cased Slovak display names for data/coffee_origins.yaml's canonical
// English keys (that file's own Slovak entries are lowercase parsing
// aliases, not display-cased names, so they aren't reused directly here).
// "Blend" is the sentinel CLAUDE.md documents for unmatched multi-origin
// products, not a country from coffee_origins.yaml.
export const ORIGIN_LABELS: Record<string, Record<Lang, string>> = {
  Ethiopia: { en: 'Ethiopia', sk: 'Etiópia' },
  Brazil: { en: 'Brazil', sk: 'Brazília' },
  Colombia: { en: 'Colombia', sk: 'Kolumbia' },
  Kenya: { en: 'Kenya', sk: 'Keňa' },
  Guatemala: { en: 'Guatemala', sk: 'Guatemala' },
  Rwanda: { en: 'Rwanda', sk: 'Rwanda' },
  Burundi: { en: 'Burundi', sk: 'Burundi' },
  Honduras: { en: 'Honduras', sk: 'Honduras' },
  Peru: { en: 'Peru', sk: 'Peru' },
  Mexico: { en: 'Mexico', sk: 'Mexiko' },
  Nicaragua: { en: 'Nicaragua', sk: 'Nikaragua' },
  'Costa Rica': { en: 'Costa Rica', sk: 'Kostarika' },
  Panama: { en: 'Panama', sk: 'Panama' },
  'El Salvador': { en: 'El Salvador', sk: 'Salvádor' },
  Bolivia: { en: 'Bolivia', sk: 'Bolívia' },
  Ecuador: { en: 'Ecuador', sk: 'Ekvádor' },
  Vietnam: { en: 'Vietnam', sk: 'Vietnam' },
  Indonesia: { en: 'Indonesia', sk: 'Indonézia' },
  India: { en: 'India', sk: 'India' },
  Yemen: { en: 'Yemen', sk: 'Jemen' },
  China: { en: 'China', sk: 'Čína' },
  Tanzania: { en: 'Tanzania', sk: 'Tanzánia' },
  Uganda: { en: 'Uganda', sk: 'Uganda' },
  Malawi: { en: 'Malawi', sk: 'Malawi' },
  Zambia: { en: 'Zambia', sk: 'Zambia' },
  'Papua New Guinea': { en: 'Papua New Guinea', sk: 'Papua Nová Guinea' },
  'Democratic Republic of the Congo': { en: 'Democratic Republic of the Congo', sk: 'Konžská demokratická republika' },
  'Ivory Coast': { en: 'Ivory Coast', sk: 'Pobrežie Slonoviny' },
  'Dominican Republic': { en: 'Dominican Republic', sk: 'Dominikánska republika' },
  Jamaica: { en: 'Jamaica', sk: 'Jamajka' },
  Cuba: { en: 'Cuba', sk: 'Kuba' },
  Haiti: { en: 'Haiti', sk: 'Haiti' },
  Philippines: { en: 'Philippines', sk: 'Filipíny' },
  Thailand: { en: 'Thailand', sk: 'Thajsko' },
  Myanmar: { en: 'Myanmar', sk: 'Mjanmarsko' },
  Laos: { en: 'Laos', sk: 'Laos' },
  'Timor-Leste': { en: 'Timor-Leste', sk: 'Východný Timor' },
  Blend: { en: 'Blend', sk: 'Zmes' },
};

export function localizedOrigin(origin: string | null | undefined, lang: Lang): string | null {
  if (!origin) return null;
  return ORIGIN_LABELS[origin]?.[lang] ?? origin;
}

export function localizedProcess(process: string | null | undefined, lang: Lang): string | null {
  if (!process) return null;
  return PROCESS_LABELS[process]?.[lang] ?? process;
}

export function localizedRoastType(roastType: string | null | undefined, lang: Lang): string | null {
  if (!roastType) return null;
  return ROAST_TYPE_LABELS[roastType]?.[lang] ?? roastType;
}
