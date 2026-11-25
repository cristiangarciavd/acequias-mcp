# Wine blends (cortes) - research notes

Research for the Rules v3 scoring redesign (#149, #165): real Argentine blends made
only from the game's eight varietals (Malbec, Cabernet Sauvignon, Cabernet Franc,
Syrah, Merlot, Bonarda, Torrontés, Chardonnay), with a suggested size class and a
rough rarity so that points can be tuned by simulation (#166).

All figures come from the INV (Instituto Nacional de Vitivinicultura) single-variety
reports, which list each grape's main blends by volume sold in the domestic market
(*mercado interno*) and exported (*mercado externo*). Sources are at the end. No
brand, winery or label is named.

## How to read the INV blend tables

- INV calls a blend a ***corte*** and names it by its varietals in order of
  proportion: "Malbec-Cabernet Sauvignon" is mostly Malbec. The same grapes in
  another order (for example Merlot-Malbec-Cabernet Sauvignon) are a separate row.
  For the game, order does not matter, so rows with the same grapes add up.
- Each report gives a blend's share of **that grape's** blends, not of all wine.
  A share of 50% of Bonarda's blends is a smaller volume than 20% of Malbec's.
- Blends are a small part of varietal wine. In 2025, 96.3% of Malbec sold in
  Argentina was single-varietal and 3.7% blends ([INV Malbec 2026][malbec]); for
  Syrah, blends were 43% ([INV Syrah 2026][syrah]), for Cabernet Sauvignon 20%
  ([INV CS 2026][cs]) and for Torrontés 23% ([INV Torrontés 2026][torrontes]).
- The tables list blends of 2 or 3 varietals. INV does not track 4-varietal
  blends separately.

## Rarity scale

- **Common**: a leading blend, at least about 15% of its main grape's blends.
- **Uncommon**: listed with about 2-15% of its main grape's blends.
- **Rare**: under about 2%, or not tracked separately by INV.

## Candidate blends

Sales years are 2025 unless noted (the Cabernet Franc report covers 2024).

| # | Blend | Size | Rarity | What it is |
| --- | --- | --- | --- | --- |
| 1 | Malbec + Cabernet Sauvignon | 2 | Common | Argentina's top red blend |
| 2 | Malbec + Bonarda | 2 | Common | Classic Argentine pair of the two top reds |
| 3 | Malbec + Syrah | 2 | Common | Warm-East red blend |
| 4 | Malbec + Cabernet Franc | 2 | Uncommon | Premium pair, high value per litre |
| 5 | Chardonnay + Torrontés | 2 | Common (white) | Argentina's main white blend |
| 6 | Malbec + Torrontés | 2 | Uncommon | Red + white blend |
| 7 | Malbec + Cabernet Sauvignon + Merlot | 3 | Uncommon | Bordeaux-style trio |
| 8 | Malbec + Cabernet Sauvignon + Cabernet Franc | 3 | Uncommon | Bordeaux-style trio |
| 9 | Malbec + Cabernet Sauvignon + Bonarda | 3 | Rare | Argentine trio of the three top reds |
| 10 | Malbec + Cabernet Sauvignon + Merlot + Cabernet Franc | 4 | Rare | Bordeaux-style blend |

### 1. Malbec + Cabernet Sauvignon (2, common)

- The most sold Malbec blend: 20.7% of Malbec blends in Argentina and 22.0% of
  exported ones, also first by export value (22.7%) ([INV Malbec 2026][malbec]).
- Cabernet Sauvignon-Malbec is 77.6% of Cabernet Sauvignon's blends at home and
  57.1% of its exported ones ([INV CS 2026][cs]).
- Owner example: confirmed, the most common blend.

### 2. Malbec + Bonarda (2, common)

- Second Malbec blend: 19.0% at home and 21.2% exported ([INV Malbec 2026][malbec]).
- Bonarda-Malbec is 17.2% of Bonarda's blends at home and 88.7% of its exported
  ones ([INV Bonarda 2026][bonarda]). INV notes Bonarda's long use to improve blends
  for its yield and colour ([INV Bonarda][inv-bonarda-news]).

### 3. Malbec + Syrah (2, common)

- Syrah-Malbec is Syrah's top blend: 49.7% at home and 61.9% exported
  ([INV Syrah 2026][syrah]). Malbec-Syrah is 13.3% of exported Malbec blends
  ([INV Malbec 2026][malbec]).
- Related: Bonarda + Syrah is Bonarda's top home blend (53.4%) and Syrah's second
  (21.3%) ([INV Bonarda 2026][bonarda]; [INV Syrah 2026][syrah]), a possible extra
  "East" pair.

### 4. Malbec + Cabernet Franc (2, uncommon)

- 11.1% of exported Malbec blends by volume but 14.1% by value, the second most
  valuable ([INV Malbec 2026][malbec]).
- Cabernet Franc-Malbec was 41.0% of Cabernet Franc's blends at home and 26.9% of
  exported ones in 2024, from a small total ([INV Cabernet Franc 2025][cf]).
- Owner example: confirmed, a real but small-volume blend.

### 5. Chardonnay + Torrontés (2, common among whites)

- Chardonnay-Torrontés Riojano is Chardonnay's top home blend (26.6%)
  ([INV Chardonnay 2026][chardonnay]).
- Torrontés Riojano-Chardonnay is Torrontés's top blend: 24.5% at home and 68.8%
  exported ([INV Torrontés 2026][torrontes]).
- White blends are a small volume: 4,604 hl of Chardonnay blends at home in 2025,
  against about 46,700 hl of Malbec blends ([INV Chardonnay 2026][chardonnay];
  [INV Malbec 2026][malbec]).

### 6. Malbec + Torrontés (2, uncommon)

- A red + white blend. Torrontés Riojano-Malbec is 7.2% of Torrontés's home blends
  and 0.3% of exported ones ([INV Torrontés 2026][torrontes]); Malbec-Torrontés
  Riojano also appears in the Malbec home table ([INV Malbec 2026][malbec]).
- A 3-varietal Chardonnay + Torrontés + Malbec exists but is tiny: 0.8% of
  Chardonnay's home blends ([INV Chardonnay 2026][chardonnay]).

### 7. Malbec + Cabernet Sauvignon + Merlot (3, uncommon)

- Exported Malbec-Cabernet Sauvignon-Merlot (4.1%) and Malbec-Merlot-Cabernet
  Sauvignon (3.3%) add up to about 7% of Malbec's exported blends
  ([INV Malbec 2026][malbec]).
- Merlot-Malbec-Cabernet Sauvignon is 14.4% of Merlot's exported blends and 3.0% of
  its home ones ([INV Merlot 2026][merlot]).
- Related pair: Malbec + Merlot is Merlot's top blend (74.7% at home, 82.3%
  exported) ([INV Merlot 2026][merlot]).

### 8. Malbec + Cabernet Sauvignon + Cabernet Franc (3, uncommon)

- Cabernet Franc-Cabernet Sauvignon-Malbec was Cabernet Franc's top exported blend
  in 2024 (29.0%), with Cabernet Franc-Malbec-Cabernet Sauvignon another 10.8%
  ([INV Cabernet Franc 2025][cf]).
- Cabernet Sauvignon-Malbec-Cabernet Franc is 1.1% of Cabernet Sauvignon's home
  blends and 3.2% of its exported ones ([INV CS 2026][cs]).

### 9. Malbec + Cabernet Sauvignon + Bonarda (3, rare)

- Bonarda-Cabernet Sauvignon-Malbec is 0.2% of Bonarda's home blends; exported,
  Bonarda-Malbec-Cabernet Sauvignon is 1.6% of Bonarda's blends
  ([INV Bonarda 2026][bonarda]) and Cabernet Sauvignon-Bonarda-Malbec 4.6% of
  Cabernet Sauvignon's ([INV CS 2026][cs]).
- Owner example: confirmed as real, but rare.

### 10. Malbec + Cabernet Sauvignon + Merlot + Cabernet Franc (4, rare)

- The classic Bordeaux-style blend. INV notes that Cabernet Sauvignon is part of
  traditional blends with Merlot, Malbec and Cabernet Franc ([INV CS 2026][cs]),
  and that Malbec was one of the traditional grapes of south-west France
  ([INV Malbec 2026][malbec]).
- INV does not track 4-varietal blends, so there is no sales figure; rarity is a
  judgement from the small 3-varietal volumes.
- Owner example: confirmed as a recognised style; no Argentine volume data.

### Other candidates (not in the main list)

- Bonarda + Syrah (2, common): see #3.
- Malbec + Merlot (2, common for Merlot): see #7.
- Cabernet Sauvignon + Syrah (2, uncommon): 5.1% of Cabernet Sauvignon's home
  blends, 12.2% exported ([INV CS 2026][cs]).
- Malbec + Syrah + Bonarda (3, uncommon): Bonarda-Syrah-Malbec is 7.2% of
  Bonarda's home blends ([INV Bonarda 2026][bonarda]).

## White wines in blends

The owner asked whether Torrontés and Chardonnay can matter in blends.

- **White blends: yes, reliable.** Chardonnay + Torrontés is the top blend of both
  white grapes (#5). Each white also blends with grapes outside the game (Chenin,
  Sauvignon Blanc, Pedro Giménez, Viognier, Semillon).
- **Red + white: yes, but small.** Malbec + Torrontés (#6) is real and listed by
  INV; Chardonnay + Torrontés + Malbec is tiny.
- **Sparkling: no blend within the game's grapes.** INV notes Chardonnay is the
  base of most Argentine sparkling wines ([INV Chardonnay 2026][chardonnay]), but
  no INV source gives a sparkling blend made only from the eight game varietals.
- Takeaway for #166: whites can score through #5 and #6. If that is not enough, the
  fallback of a *bodega* needing X reds and Y whites still fits.

## Naming: *corte* and *bodega*

- ***Corte*** is the standard Argentine term for a blend, and the one INV uses in
  every report ("principales cortes", "Malbec con cortes"). INV also uses
  ***bivarietal*** and ***trivarietal*** ("el trivarietal Merlot-Malbec-Cabernet
  Sauvignon", [INV Merlot 2026][merlot]).
- A wine labelled as one varietal must hold at least 85% of that grape (INV
  Resolución 20/2020, cited in [INV varietal labelling study][varietal]); below that,
  it is a blend.
- ***Bodega*** means winery (the place that makes and ages wine), not a kind of
  wine. It is not wrong as theme for a 3-varietal bonus ("your winery's blend"),
  but it is less precise than *corte*.
- Suggestion: call scoring blends ***Corte*** (with *bivarietal* / *trivarietal*
  if sizes need names) and keep ***Bodega*** for something a winery is or has,
  such as the X reds + Y whites requirement.

## Newer INV data

INV has published newer figures than the 2024 annual report, so the fact card in
[`varietals.md`](varietals.md) now uses them:

- *Informe Anual de Superficie 2025* (Feb 2026, data on 31 Dec 2025): 196,220 ha of
  vines in Argentina, 140,682 ha in Mendoza ([INV 2025][inv-sup]).
- New single-variety reports for all eight grapes, with 2025 sales (Cabernet Franc
  with 2024), listed below and on the INV varieties page ([INV variedades][inv-var]).
- Harvest: INV's 2026 harvest report gives over 18 million quintals of grapes, of
  excellent quality ([INV cosecha 2026][cosecha]).

## Sources

- INV, *Informe Anual de Superficie 2025* (Feb 2026): https://www.argentina.gob.ar/sites/default/files/2018/10/anuario_superficie_2025.pdf
- INV, *Informe de variedades: Malbec* (Apr 2026): https://www.argentina.gob.ar/sites/default/files/2018/10/informe_malbec_2025.pdf
- INV, *Informe de variedad: Cabernet Sauvignon* (Sep 2026): https://www.argentina.gob.ar/sites/default/files/2018/10/cabernet_sauvignon_1.pdf
- INV, *Informe de variedades: Merlot* (Oct 2026): https://www.argentina.gob.ar/sites/default/files/2018/10/informe_merlot.pdf
- INV, *Informe de variedades: Bonarda* (Jul 2026): https://www.argentina.gob.ar/sites/default/files/2018/10/bonarda_2025_0.pdf
- INV, *Informe de variedades: Syrah* (Feb 2026): https://www.argentina.gob.ar/sites/default/files/2018/10/01-syrah_2025_1.pdf
- INV, *Informe de variedades: Cabernet Franc* (Dec 2025): https://www.argentina.gob.ar/sites/default/files/2018/10/cabernet_franc.pdf
- INV, *Informe de variedades: Torrontés* (Oct 2026): https://www.argentina.gob.ar/sites/default/files/2018/10/torrontes_2026.pdf
- INV, *Informe de variedades: Chardonnay* (May 2026): https://www.argentina.gob.ar/sites/default/files/2018/10/chardonnay_2025.pdf
- INV, *Informe de variedad: Bonarda* (news page): https://www.argentina.gob.ar/noticias/informe-de-variedad-bonarda-0
- INV, varietal labelling sensory study (Resolución 20/2020, 85% rule): https://argentina.gob.ar/sites/default/files/2021/04/varietalidad_etiquetado_inv_publicacion.pdf
- INV, varieties statistics page: https://www.argentina.gob.ar/inv/vinos/estadisticas/variedades-de-uva
- INV, 2026 harvest news: https://www.argentina.gob.ar/node/501970

[inv-sup]: https://www.argentina.gob.ar/sites/default/files/2018/10/anuario_superficie_2025.pdf
[malbec]: https://www.argentina.gob.ar/sites/default/files/2018/10/informe_malbec_2025.pdf
[cs]: https://www.argentina.gob.ar/sites/default/files/2018/10/cabernet_sauvignon_1.pdf
[merlot]: https://www.argentina.gob.ar/sites/default/files/2018/10/informe_merlot.pdf
[bonarda]: https://www.argentina.gob.ar/sites/default/files/2018/10/bonarda_2025_0.pdf
[syrah]: https://www.argentina.gob.ar/sites/default/files/2018/10/01-syrah_2025_1.pdf
[cf]: https://www.argentina.gob.ar/sites/default/files/2018/10/cabernet_franc.pdf
[torrontes]: https://www.argentina.gob.ar/sites/default/files/2018/10/torrontes_2026.pdf
[chardonnay]: https://www.argentina.gob.ar/sites/default/files/2018/10/chardonnay_2025.pdf
[inv-bonarda-news]: https://www.argentina.gob.ar/noticias/informe-de-variedad-bonarda-0
[varietal]: https://argentina.gob.ar/sites/default/files/2021/04/varietalidad_etiquetado_inv_publicacion.pdf
[inv-var]: https://www.argentina.gob.ar/inv/vinos/estadisticas/variedades-de-uva
[cosecha]: https://www.argentina.gob.ar/node/501970
