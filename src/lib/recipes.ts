// Structured brew recipes for the brew-method pages (issue #88).
// Parameters follow widely-published, recognized recipes (credited per
// entry) rewritten in our own words — recipe parameters are facts, their
// prose isn't copied. Grinder clicks are starting ranges counted from the
// fully-closed zero point, cross-checked between per-grinder guides
// (Comandante C40 ≈ 30 µm/click, Timemore C2 ≈ 33 µm/click, so C2 ≈ C40
// × 0.9); individual units and burr seating vary, so they're ranges, not
// gospel.
import type { Lang } from './i18n';

export interface Recipe {
  dose: string;
  water: string;
  ratio: string;
  temp: string;
  time: string;
  grindLabel: Record<Lang, string>;
  // Position band on the fine→coarse scale, 0 = finest, 1 = coarsest.
  grindBand: [number, number];
  c40: string;
  c2: string;
  steps: Record<Lang, string[]>;
  basedOn: { label: Record<Lang, string>; href: string };
}

export const RECIPES: Record<string, Recipe> = {
  v60: {
    dose: '15 g',
    water: '250 g (~95 °C)',
    ratio: '1:16.7 (60 g/L)',
    temp: '92–96 °C',
    time: '3:00–3:30',
    grindLabel: { en: 'medium-fine', sk: 'stredne jemné' },
    grindBand: [0.3, 0.45],
    c40: '20–24',
    c2: '17–19',
    steps: {
      en: [
        'Rinse the paper filter, add coffee, make a well in the middle.',
        'Bloom: pour 2× the coffee weight (30 g) of water, swirl, wait 45 s.',
        'Pour to 60 % of total (150 g) in slow circles by ~1:15.',
        'Top up to 250 g by ~1:45, stir once, swirl gently.',
        'Drawdown should finish around 3:00–3:30. Finer if sour, coarser if bitter.',
      ],
      sk: [
        'Prepláchnite papierový filter, nasypte kávu, urobte v strede jamku.',
        'Bloom: zalejte 2× hmotnosť kávy (30 g) vody, zakrúžte, počkajte 45 s.',
        'Do ~1:15 dolejte pomalými kruhmi na 60 % celku (150 g).',
        'Do ~1:45 dolejte na 250 g, raz premiešajte, jemne zakrúžte.',
        'Pretečenie má skončiť okolo 3:00–3:30. Kyslé → jemnejšie, horké → hrubšie.',
      ],
    },
    basedOn: {
      label: { en: "James Hoffmann's Ultimate V60 Technique", sk: 'Ultimate V60 Technique Jamesa Hoffmanna' },
      href: 'https://www.youtube.com/watch?v=AI4ynXzkSQo',
    },
  },
  aeropress: {
    dose: '14 g',
    water: '200 g',
    ratio: '1:14',
    temp: '85–90 °C',
    time: '~2:30',
    grindLabel: { en: 'medium', sk: 'stredné' },
    grindBand: [0.25, 0.4],
    c40: '16–18',
    c2: '14–16',
    steps: {
      en: [
        'Standard (upright) position, rinsed paper filter.',
        'Add coffee, pour all 200 g of water within ~15 s.',
        'Stir 3× gently, cap on, steep to 2:00.',
        'Press slowly for ~30 s, stopping at the hiss.',
      ],
      sk: [
        'Štandardná (vzpriamená) poloha, prepláchnutý papierový filter.',
        'Nasypte kávu a do ~15 s zalejte všetkých 200 g vody.',
        'Trikrát jemne premiešajte, nasaďte piest, lúhujte do 2:00.',
        'Tlačte pomaly ~30 s a zastavte pri zasyčaní.',
      ],
    },
    basedOn: {
      label: { en: 'World AeroPress Championship recipes', sk: 'recepty World AeroPress Championship' },
      href: 'https://www.worldaeropresschampionship.com/recipes',
    },
  },
  'french-press': {
    dose: '30 g',
    water: '500 g',
    ratio: '1:16.7 (60 g/L)',
    temp: '~95 °C',
    time: '4:00 + 5–8 min rest',
    grindLabel: { en: 'medium-coarse', sk: 'stredne hrubé' },
    grindBand: [0.6, 0.8],
    c40: '30–35',
    c2: '26–29',
    steps: {
      en: [
        'Add coffee, pour all the water, steep 4 minutes.',
        'Stir the crust, scoop off the foam and floating grounds.',
        'Rest another 5–8 minutes so fines settle.',
        'Press the plunger only to the surface — don\'t plunge through — and pour gently.',
      ],
      sk: [
        'Nasypte kávu, zalejte všetkou vodou a lúhujte 4 minúty.',
        'Premiešajte kôrku a zoberte penu s plávajúcimi časticami.',
        'Nechajte ešte 5–8 minút odstáť, aby jemné častice klesli.',
        'Piest zatlačte len po hladinu — nepretláčajte — a nalievajte opatrne.',
      ],
    },
    basedOn: {
      label: { en: "James Hoffmann's French press method", sk: 'French press metóda Jamesa Hoffmanna' },
      href: 'https://www.youtube.com/watch?v=st571DYYTR8',
    },
  },
  'cold-brew': {
    dose: '70 g',
    water: '1000 g (cold)',
    ratio: '1:14',
    temp: '4–20 °C',
    time: '12–24 h',
    grindLabel: { en: 'coarse', sk: 'hrubé' },
    grindBand: [0.8, 1.0],
    c40: '35–40',
    c2: '30–34',
    steps: {
      en: [
        'Combine coffee and cold water in a jar, stir until wetted.',
        'Steep 12–24 h in the fridge (longer = stronger and heavier).',
        'Strain through a paper filter or fine sieve.',
        'Serve over ice; dilute with water or milk to taste.',
      ],
      sk: [
        'Zmiešajte kávu so studenou vodou v nádobe a premiešajte, kým nie je celá zmáčaná.',
        'Lúhujte 12–24 h v chladničke (dlhšie = silnejšie a plnšie).',
        'Preceďte cez papierový filter alebo jemné sitko.',
        'Podávajte na ľade; podľa chuti zrieďte vodou alebo mliekom.',
      ],
    },
    basedOn: {
      label: { en: 'standard immersion cold-brew practice', sk: 'štandardný imerzný cold brew' },
      href: 'https://www.youtube.com/watch?v=PApBycDrPo0',
    },
  },
};
