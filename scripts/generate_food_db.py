"""One-off generator for data/foods/foods.it.json.

Not run automatically — it exists so the per-100g macro estimates below
(hand-curated from typical CREA/USDA composition tables, not scraped) are
reviewable as plain numbers, with kcal always DERIVED from them via the
Atwater identity (4P + 4C + 9F) rather than copy-pasted from a label. That
guarantees every row satisfies app.domain.references.FOOD_DB_ATWATER_TOLERANCE_PCT
by construction, and it's the same convention the domain engine itself uses
(carbs already include fiber; fiber is not separately weighted at ~2 kcal/g).

Run again only to regenerate the file from scratch after editing the list
below — it overwrites data/foods/foods.it.json.
"""

from __future__ import annotations

import json
from pathlib import Path

KCAL_P = 4.0
KCAL_C = 4.0
KCAL_F = 9.0

# (key, name_it, name_en, protein_g, carb_g, fat_g, fiber_g, tags)
# All values per 100g of the food as typically consumed (cooked where
# applicable). tags: subset of {vegan, vegetarian, gluten_free,
# lactose_free, fish, nuts, egg, pork} — the diet tags (vegan..lactose_free)
# mean the food IS suitable for that diet; fish/nuts/egg/pork mean the food
# CONTAINS that allergen.
FOODS = [
    # --- Cereali e farinacei ---
    ("riso_bianco_cotto", "Riso bianco (cotto)", "White rice (cooked)", 2.7, 28.0, 0.3, 0.4,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
    ("riso_integrale_cotto", "Riso integrale (cotto)", "Brown rice (cooked)", 2.6, 23.0, 0.9, 1.8,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
    ("pasta_cotta", "Pasta di semola (cotta)", "Pasta (cooked)", 5.8, 25.0, 0.9, 1.8,
     ["vegan", "vegetarian", "lactose_free"]),
    ("pasta_integrale_cotta", "Pasta integrale (cotta)", "Whole wheat pasta (cooked)", 5.3, 23.0, 1.1, 3.5,
     ["vegan", "vegetarian", "lactose_free"]),
    ("pane_bianco", "Pane bianco", "White bread", 9.0, 49.0, 3.2, 2.7,
     ["vegetarian", "lactose_free"]),
    ("pane_integrale", "Pane integrale", "Whole wheat bread", 8.8, 41.0, 3.4, 7.0,
     ["vegetarian", "lactose_free"]),
    ("pane_di_segale", "Pane di segale", "Rye bread", 8.5, 48.0, 1.1, 6.0,
     ["vegetarian", "lactose_free"]),
    ("patate_cotte", "Patate (cotte)", "Potatoes (cooked)", 2.0, 17.0, 0.1, 2.2,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
    ("avena_fiocchi", "Fiocchi d'avena", "Oats", 13.5, 58.0, 7.0, 10.0,
     ["vegan", "vegetarian", "lactose_free"]),
    ("quinoa_cotta", "Quinoa (cotta)", "Quinoa (cooked)", 4.4, 21.0, 1.9, 2.8,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
    ("couscous_cotto", "Couscous (cotto)", "Couscous (cooked)", 3.8, 23.0, 0.2, 1.4,
     ["vegan", "vegetarian", "lactose_free"]),
    ("farro_cotto", "Farro (cotto)", "Farro (cooked)", 5.0, 34.0, 0.9, 4.6,
     ["vegan", "vegetarian", "lactose_free"]),
    ("orzo_cotto", "Orzo perlato (cotto)", "Pearl barley (cooked)", 2.3, 28.0, 0.4, 3.8,
     ["vegan", "vegetarian", "lactose_free"]),

    # --- Proteine animali ---
    ("petto_di_pollo_cotto", "Petto di pollo (cotto)", "Chicken breast (cooked)", 31.0, 0.0, 3.6, 0.0,
     ["gluten_free", "lactose_free"]),
    ("petto_di_tacchino_cotto", "Petto di tacchino (cotto)", "Turkey breast (cooked)", 29.0, 0.0, 1.0, 0.0,
     ["gluten_free", "lactose_free"]),
    ("manzo_magro_cotto", "Manzo magro (cotto)", "Lean beef (cooked)", 28.0, 0.0, 8.0, 0.0,
     ["gluten_free", "lactose_free"]),
    ("vitello_cotto", "Vitello (cotto)", "Veal (cooked)", 30.0, 0.0, 4.0, 0.0,
     ["gluten_free", "lactose_free"]),
    ("maiale_lonza_cotta", "Lonza di maiale (cotta)", "Pork loin (cooked)", 27.0, 0.0, 5.0, 0.0,
     ["gluten_free", "lactose_free", "pork"]),
    ("salmone_cotto", "Salmone (cotto)", "Salmon (cooked)", 22.0, 0.0, 13.0, 0.0,
     ["gluten_free", "lactose_free", "fish"]),
    ("tonno_al_naturale", "Tonno al naturale", "Canned tuna (in water)", 25.0, 0.0, 1.0, 0.0,
     ["gluten_free", "lactose_free", "fish"]),
    ("merluzzo_cotto", "Merluzzo (cotto)", "Cod (cooked)", 23.0, 0.0, 0.7, 0.0,
     ["gluten_free", "lactose_free", "fish"]),
    ("orata_cotta", "Orata (cotta)", "Sea bream (cooked)", 20.0, 0.0, 3.0, 0.0,
     ["gluten_free", "lactose_free", "fish"]),
    ("gamberi_cotti", "Gamberi (cotti)", "Shrimp (cooked)", 24.0, 0.9, 0.8, 0.0,
     ["gluten_free", "lactose_free", "fish"]),
    ("uovo_intero", "Uovo intero", "Whole egg", 12.6, 0.7, 9.5, 0.0,
     ["vegetarian", "gluten_free", "lactose_free", "egg"]),
    ("albume_uovo", "Albume d'uovo", "Egg white", 10.9, 0.7, 0.2, 0.0,
     ["vegetarian", "gluten_free", "lactose_free", "egg"]),

    # --- Legumi e sostituti ---
    ("lenticchie_cotte", "Lenticchie (cotte)", "Lentils (cooked)", 9.0, 20.0, 0.4, 8.0,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
    ("ceci_cotti", "Ceci (cotti)", "Chickpeas (cooked)", 8.9, 27.0, 2.6, 7.6,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
    ("fagioli_borlotti_cotti", "Fagioli borlotti (cotti)", "Borlotti beans (cooked)", 8.7, 23.0, 0.5, 6.4,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
    ("fagioli_neri_cotti", "Fagioli neri (cotti)", "Black beans (cooked)", 8.9, 24.0, 0.5, 8.7,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
    ("piselli_cotti", "Piselli (cotti)", "Peas (cooked)", 5.4, 14.0, 0.4, 5.1,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
    ("tofu", "Tofu", "Tofu", 8.0, 1.9, 4.8, 0.3,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
    ("tempeh", "Tempeh", "Tempeh", 19.0, 9.0, 11.0, 9.0,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
    ("edamame_cotti", "Edamame (cotti)", "Edamame (cooked)", 11.0, 10.0, 5.0, 5.0,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),

    # --- Latticini ---
    ("yogurt_greco_intero", "Yogurt greco intero", "Greek yogurt (full-fat)", 9.0, 4.0, 5.0, 0.0,
     ["vegetarian", "gluten_free"]),
    ("yogurt_greco_0", "Yogurt greco 0%", "Greek yogurt (fat-free)", 10.0, 3.6, 0.4, 0.0,
     ["vegetarian", "gluten_free"]),
    ("latte_intero", "Latte intero", "Whole milk", 3.2, 4.8, 3.6, 0.0,
     ["vegetarian", "gluten_free"]),
    ("latte_scremato", "Latte scremato", "Skimmed milk", 3.4, 5.0, 0.2, 0.0,
     ["vegetarian", "gluten_free"]),
    ("mozzarella", "Mozzarella", "Mozzarella", 18.0, 1.0, 16.0, 0.0,
     ["vegetarian", "gluten_free"]),
    ("ricotta", "Ricotta", "Ricotta", 8.0, 3.0, 10.0, 0.0,
     ["vegetarian", "gluten_free"]),
    ("parmigiano", "Parmigiano Reggiano", "Parmesan", 33.0, 0.0, 28.0, 0.0,
     ["vegetarian", "gluten_free"]),
    ("skyr", "Skyr", "Skyr", 11.0, 4.0, 0.2, 0.0,
     ["vegetarian", "gluten_free"]),

    # --- Grassi e oli ---
    ("olio_oliva", "Olio d'oliva", "Olive oil", 0.0, 0.0, 100.0, 0.0,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
    ("burro", "Burro", "Butter", 0.8, 0.1, 81.0, 0.0,
     ["vegetarian", "gluten_free"]),
    ("avocado", "Avocado", "Avocado", 2.0, 8.5, 15.0, 6.7,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),

    # --- Frutta secca e semi ---
    ("mandorle", "Mandorle", "Almonds", 21.0, 22.0, 49.0, 12.5,
     ["vegan", "vegetarian", "gluten_free", "lactose_free", "nuts"]),
    ("noci", "Noci", "Walnuts", 15.0, 14.0, 65.0, 6.7,
     ["vegan", "vegetarian", "gluten_free", "lactose_free", "nuts"]),
    ("arachidi", "Arachidi", "Peanuts", 26.0, 16.0, 49.0, 8.5,
     ["vegan", "vegetarian", "gluten_free", "lactose_free", "nuts"]),
    ("anacardi", "Anacardi", "Cashews", 18.0, 30.0, 44.0, 3.3,
     ["vegan", "vegetarian", "gluten_free", "lactose_free", "nuts"]),
    ("semi_di_chia", "Semi di chia", "Chia seeds", 17.0, 42.0, 31.0, 34.0,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
    ("semi_di_lino", "Semi di lino", "Flax seeds", 18.0, 29.0, 42.0, 27.0,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),

    # --- Verdure ---
    ("broccoli_cotti", "Broccoli (cotti)", "Broccoli (cooked)", 2.8, 7.0, 0.4, 3.3,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
    ("spinaci_cotti", "Spinaci (cotti)", "Spinach (cooked)", 3.0, 3.8, 0.4, 2.4,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
    ("zucchine_cotte", "Zucchine (cotte)", "Zucchini (cooked)", 1.2, 3.0, 0.3, 1.1,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
    ("carote_cotte", "Carote (cotte)", "Carrots (cooked)", 0.8, 8.0, 0.3, 2.8,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
    ("pomodori", "Pomodori", "Tomatoes", 0.9, 3.9, 0.2, 1.2,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
    ("insalata_verde", "Insalata verde", "Green salad", 1.4, 2.0, 0.2, 1.3,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
    ("melanzane_cotte", "Melanzane (cotte)", "Eggplant (cooked)", 0.8, 6.0, 0.2, 2.5,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
    ("peperoni", "Peperoni", "Bell peppers", 1.0, 6.0, 0.3, 2.1,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
    ("cavolfiore_cotto", "Cavolfiore (cotto)", "Cauliflower (cooked)", 1.8, 4.0, 0.3, 2.3,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
    ("funghi_champignon", "Funghi champignon", "Button mushrooms", 3.1, 3.3, 0.3, 1.0,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),

    # --- Frutta ---
    ("banana", "Banana", "Banana", 1.1, 23.0, 0.3, 2.6,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
    ("mela", "Mela", "Apple", 0.3, 14.0, 0.2, 2.4,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
    ("arancia", "Arancia", "Orange", 0.9, 12.0, 0.1, 2.4,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
    ("fragole", "Fragole", "Strawberries", 0.7, 8.0, 0.3, 2.0,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
    ("mirtilli", "Mirtilli", "Blueberries", 0.7, 14.0, 0.3, 2.4,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
    ("kiwi", "Kiwi", "Kiwi", 1.1, 15.0, 0.5, 3.0,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
    ("uva", "Uva", "Grapes", 0.6, 18.0, 0.2, 0.9,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
    ("ananas", "Ananas", "Pineapple", 0.5, 13.0, 0.1, 1.4,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
    ("pera", "Pera", "Pear", 0.4, 15.0, 0.1, 3.1,
     ["vegan", "vegetarian", "gluten_free", "lactose_free"]),
]


def build_entries():
    entries = []
    for key, name_it, name_en, protein_g, carb_g, fat_g, fiber_g, tags in FOODS:
        kcal = round(KCAL_P * protein_g + KCAL_C * carb_g + KCAL_F * fat_g, 1)
        entries.append(
            {
                "key": key,
                "name_it": name_it,
                "name_en": name_en,
                "per_100g": {
                    "kcal": kcal,
                    "protein_g": protein_g,
                    "carb_g": carb_g,
                    "fat_g": fat_g,
                    "fiber_g": fiber_g,
                },
                "tags": tags,
            }
        )
    return entries


if __name__ == "__main__":
    entries = build_entries()
    out_path = Path(__file__).parent.parent / "data" / "foods" / "foods.it.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"wrote {len(entries)} foods to {out_path}")
