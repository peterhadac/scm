#!/usr/bin/env python3
"""
Fix drinks.yaml with correct brewing methods, temperatures, and milk content.
Based on Biodynamic Coffee's 86 Types of Coffee Drinks article.
"""

import yaml
from pathlib import Path

# Read the current data
drinks_file = Path('data/drinks.yaml')
with open(drinks_file, 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f)

# Method mapping based on drink name and the Biodynamic article
method_mapping = {
    # Straight Espresso & Black Shots
    'Espresso': 'espresso',
    'Ristretto': 'espresso',
    'Lungo': 'espresso',
    'Doppio': 'espresso',
    'Caffè Americano': 'drip machine',
    'Long Black': 'drip machine',
    'Red Eye': 'drip machine',
    'Caffè Crema': 'espresso',
    'Espresso Romano': 'espresso',
    
    # Espresso + Milk
    'Caffè Latte': 'steamed milk',
    'Cappuccino': 'steamed milk',
    'Flat White': 'steamed milk',
    'Cortado': 'steamed milk',
    'Espresso Macchiato': 'steamed milk',
    'Latte Macchiato': 'steamed milk',
    'Caffè Mocha': 'steamed milk',
    'Caffè Breve': 'steamed milk',
    'Piccolo Latte': 'steamed milk',
    'Magic': 'steamed milk',
    'Café con Leche': 'steamed milk',
    'Café au Lait': 'drip machine',
    'Galão': 'steamed milk',
    'Café Bombón': 'steamed milk',
    'Wiener Melange': 'steamed milk',
    'Spanish Latte': 'steamed milk',
    'Dirty Chai': 'steamed milk',
    
    # Brewed, Filter & Functional
    'Drip Coffee': 'drip machine',
    'Pour-Over': 'pour-over',
    'French Press': 'french press',
    'AeroPress': 'aeropress',
    'Moka Pot Coffee': 'stovetop moka pot',
    'Percolator Coffee': 'percolator',
    'Siphon Coffee': 'vacuum pot',
    'Cowboy Coffee': 'boiled',
    'Instant Coffee': 'instant',
    'Butter Coffee': 'blended',
    
    # Iced & Cold Coffee Drinks
    'Iced Coffee': 'drip machine',  # cold brew technique
    'Cold Brew': 'cold extraction',
    'Nitro Cold Brew': 'infused with nitrogen',
    'Kyoto-Style Slow Drip': 'slow drip',
    'Iced Latte': 'steamed milk',
    'Iced Americano': 'drip machine',
    'Greek Frappé': 'shaken',
    'Freddo Espresso & Freddo Cappuccino': 'shaken with ice',
    'Espresso Tonic': 'shaken with ice',
    'Coffee Soda': 'shaken with ice',
    'Mazagran': 'shaken',
    'Eiskaffee': 'brewed with egg',
    
    # Traditional & Regional Specialties
    'Turkish Coffee': 'turkish coffee pot',
    'Arabic Coffee (Qahwa)': 'filtration sock',
    'Vietnamese Coffee (Cà Phê Sữa Đá)': 'filtration sock',
    'Egg Coffee (Cà Phê Trứng)': 'brewed with egg',
    'Café de Olla': 'boiled',
    'Cafezinho': 'filtration sock',
    'Tinto': 'filtration sock',
    'Cuban Coffee (Cafecito, Colada, Cortadito)': 'stovetop moka pot',
    'South Indian Filter Coffee (Kaapi)': 'filtration sock',
    'Kopi (Nanyang Coffee)': 'filtration sock',
    'Oliang (Thai Iced Coffee)': 'filtration sock',
    'Yuanyang': 'blended',
    'Café Touba': 'filtration sock',
    'Ethiopian Coffee Ceremony (Buna)': 'filtration sock',
    'Scandinavian Egg Coffee': 'brewed with egg',
    'Kaffeost': 'steeped',
    'Kopi Joss': 'charcoal',
    'Kopi Tubruk': 'filtration sock',
    'Café Lágrima': 'steamed milk',
    'Café Chorreado': 'filtration sock',
    'Chicory Coffee (New Orleans Style)': 'drip machine',
    'Double-Double': 'drip machine',
    
    # Dessert Coffees
    'Affogato': 'blended',
    'Espresso con Panna': 'espresso',
    'Einspänner (Vienna Coffee)': 'espresso',
    'Dalgona Coffee': 'shaken',
    'Marocchino': 'espresso',
    'Bicerin': 'blended',
    'Babyccino': 'steamed milk',
    
    # Spirited Coffee Drinks
    'Irish Coffee': 'steeped',
    'Espresso Martini': 'shaken with ice',
    'Carajillo': 'shaken with ice',
    'Caffè Corretto': 'espresso',
    'Rüdesheimer Kaffee': 'flamed',
    'Pharisäer': 'steeped',
    'Karsk': 'steeped',
    'Café Royale': 'flamed',
    'Liqueur Coffees (The Family)': 'steeped',
}

# Temperature mapping - some drinks need cold
cold_drinks = {
    'Iced Coffee',
    'Cold Brew',
    'Nitro Cold Brew',
    'Kyoto-Style Slow Drip',
    'Iced Latte',
    'Iced Americano',
    'Greek Frappé',
    'Freddo Espresso & Freddo Cappuccino',
    'Espresso Tonic',
    'Coffee Soda',
    'Mazagran',
    'Eiskaffee',
    'Oliang (Thai Iced Coffee)',
}

# Milk content corrections - drinks that don't have milk
no_milk_drinks = {
    'Espresso',
    'Ristretto',
    'Lungo',
    'Doppio',
    'Caffè Americano',
    'Long Black',
    'Red Eye',
    'Caffè Crema',
    'Espresso Romano',
    'Cowboy Coffee',
    'Instant Coffee',
    'Butter Coffee',
    'Turkish Coffee',
    'Arabic Coffee (Qahwa)',
    'Vietnamese Coffee (Cà Phê Sữa Đá)',
    'Egg Coffee (Cà Phê Trứng)',
    'Café de Olla',
    'Cafezinho',
    'Tinto',
    'Cuban Coffee (Cafecito, Colada, Cortadito)',
    'South Indian Filter Coffee (Kaapi)',
    'Kopi (Nanyang Coffee)',
    'Oliang (Thai Iced Coffee)',
    'Yuanyang',
    'Café Touba',
    'Ethiopian Coffee Ceremony (Buna)',
    'Scandinavian Egg Coffee',
    'Kaffeost',
    'Kopi Joss',
    'Kopi Tubruk',
    'Café Lágrima',
    'Café Chorreado',
    'Chicory Coffee (New Orleans Style)',
    'Double-Double',
    'Espresso con Panna',
    'Einspänner (Vienna Coffee)',
    'Dalgona Coffee',
    'Marocchino',
    'Bicerin',
    'Irish Coffee',
    'Espresso Martini',
    'Carajillo',
    'Caffè Corretto',
    'Rüdesheimer Kaffee',
    'Pharisäer',
    'Karsk',
    'Café Royale',
    'Liqueur Coffees (The Family)',
    'Babyccino',  # No coffee at all, just foam
}

# Update each drink
for drink in data['drinks']:
    title = drink['title']
    
    # Update method based on the mapping
    if title in method_mapping:
        drink['method'] = [method_mapping[title]]
    
    # Update temperature for cold drinks
    if title in cold_drinks:
        drink['temperature'] = 'cold'
    
    # Update milk_content
    if title in no_milk_drinks:
        drink['milk_content'] = 'no milk'

# Write the fixed data
with open(drinks_file, 'w', encoding='utf-8') as f:
    yaml.dump(data, f, allow_unicode=True, sort_keys=False)

print(f"Fixed {len(data['drinks'])} drinks in {drinks_file}")

# Verify the changes
espresso_count = sum(1 for d in data['drinks'] if d['method'] == ['espresso'])
drip_count = sum(1 for d in data['drinks'] if d['method'] == ['drip machine'])
cold_count = sum(1 for d in data['drinks'] if d['temperature'] == 'cold')
milk_count = sum(1 for d in data['drinks'] if d['milk_content'] == 'milk')

print(f"\nVerification:")
print(f"Espresso method: {espresso_count}")
print(f"Drip machine method: {drip_count}")
print(f"Cold drinks: {cold_count}")
print(f"Milk drinks: {milk_count}")
print(f"Total drinks: {len(data['drinks'])}")
