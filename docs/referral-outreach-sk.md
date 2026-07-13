# Referral outreach — pražiarne (SK)

**Issue:** #57 · Technical scaffolding is in place (`referral: {code, note}` in
`roasters.yaml` → a copyable discount chip on that roaster's rows). Sending
these emails and agreeing terms is the human step; this is the template.

## Ako to funguje na strane webu

Keď pražiareň súhlasí, pridá sa jej do `roasters.yaml`:

```yaml
  - name: Príklad Pražiareň
    slug: priklad-praziaren
    url: https://priklad.sk/
    scrape_url: https://priklad.sk/
    referral:
      code: COFFEEMAP10      # kód, ktorý zákazník zadá pri objednávke
      note: 10% zľava        # voliteľný kontext zobrazený v tooltipe
```

Na každom riadku danej pražiarne sa potom zobrazí malý kliknuteľný „zľava:
COFFEEMAP10" čip, ktorý kód po kliknutí skopíruje. Žiadny iný krok netreba —
zmena sa prejaví pri najbližšom nasadení webu.

## E-mailová šablóna

> **Predmet:** Slovak Coffee Map — spolupráca a zľavový kód pre vašich zákazníkov
>
> Dobrý deň,
>
> volám sa [MENO] a prevádzkujem [Slovak Coffee Map](https://peterhadac.github.io/scm/)
> — nezávislý web, ktorý každý týždeň zbiera ponuku špecialitovej kávy od
> slovenských pražiarní do jednej prehľadnej, filtrovateľnej tabuľky. Vaša
> pražiareň [NÁZOV] je medzi nimi.
>
> Web posiela návštevníkov priamo na vaše produktové stránky. Za posledné
> [OBDOBIE] sme na [NÁZOV] preklikli **[POČET] návštevníkov** (čísla viem
> doložiť — merané cez GoatCounter, výstupné kliknutia na vašu doménu).
>
> Rád by som ponúkol vašim zákazníkom **zľavový kód**, ktorý by sa zobrazoval
> priamo pri vašich kávach v tabuľke. Pre vás to znamená:
>
> - viditeľné odlíšenie od ostatných pražiarní v zozname,
> - merateľný prílev objednávok s vaším kódom,
> - žiadne náklady ani provízia — web je nekomerčný, ide mi len o to, aby
>   ľudia kupovali dobrú kávu od vás.
>
> Ak máte záujem, stačí mi poslať kód (napr. `NAZOV10`) a jednu vetu, čo
> ponúka (napr. „10% na prvý nákup"). Zvyšok zariadim ja.
>
> Ďakujem za váš čas a za kávu, ktorú robíte.
>
> S pozdravom,
> [MENO]
> [odkaz na web] · [kontakt]

## Poznámky k oslovovaniu

- **Čísla najprv.** Konkrétne kliknutia z GoatCounteru (issue #84) sú
  najsilnejší argument — pošlite ich, až keď ich máte, nie odhad.
- **Žiadny nátlak.** Web je neutrálny nástroj; jedna zdvorilá ponuka, žiadne
  urgencie.
- **Jeden kód na pražiareň.** UI zobrazuje jeden čip na riadok — držte sa
  jedného aktívneho kódu.
