# -*- coding: utf-8 -*-
"""
МОДУЛЬ АНАЛИЗА: basket_analyzer.py
Полная логика Market Basket Analysis (Support, Confidence, Lift)
"""
import csv
import json
import itertools
from collections import Counter
from datetime import datetime


def read_receipts_from_csv(filepath):
    """Чтение чеков из CSV файла"""
    receipts = {}
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        if 'id_чека' not in reader.fieldnames or 'товар' not in reader.fieldnames:
            raise ValueError("CSV должен содержать колонки: 'id_чека' и 'товар'")

        for row in reader:
            rid = row['id_чека'].strip()
            prod = row['товар'].strip()
            if rid and prod:
                receipts.setdefault(rid, []).append(prod)
    return receipts


def count_product_pairs(receipts):
    """Подсчет частоты встречаемости пар товаров и отдельных товаров"""
    pair_counter = Counter()
    single_counter = Counter()  # Для расчета Support отдельных товаров
    total_receipts = len(receipts)

    for receipt_id, items in receipts.items():
        for item in items:
            single_counter[item] += 1

        unique_items = sorted(set(items))
        if len(unique_items) >= 2:
            pairs = itertools.combinations(unique_items, 2)
            for pair in pairs:
                pair_counter[pair] += 1

    return pair_counter, single_counter, total_receipts


def get_top_pairs_with_metrics(pair_counter, single_counter, total_receipts, top_n=10):
    """Получение топ-N пар с расчетом всех метрик"""
    if not pair_counter:
        return []

    sorted_pairs = pair_counter.most_common(top_n)
    results = []

    for rank, (pair, count) in enumerate(sorted_pairs, 1):
        product_a, product_b = pair

        # Support: доля чеков с обоими товарами
        support = (count / total_receipts) * 100 if total_receipts > 0 else 0

        # Confidence: вероятность купить B, если купили A
        count_a = single_counter[product_a]
        confidence = (count / count_a) * 100 if count_a > 0 else 0

        # Lift: коэффициент связи
        count_b = single_counter[product_b]
        support_b = count_b / total_receipts if total_receipts > 0 else 0
        lift = (confidence / 100) / support_b if support_b > 0 else 0

        if lift > 1:
            lift_interpretation = "Положительная связь"
        elif lift == 1:
            lift_interpretation = "Независимы"
        else:
            lift_interpretation = "Отрицательная связь"

        result = {
            'rank': rank,
            'product_a': product_a,
            'product_b': product_b,
            'count': count,
            'support': round(support, 2),
            'confidence': round(confidence, 2),
            'lift': round(lift, 3),
            'lift_interpretation': lift_interpretation,
            'recommendation': 'Положить рядом' if lift > 1.2 else ''
        }
        results.append(result)

    return results


def create_json_response(top_pairs, total_receipts, output_path=None):
    """Формирование JSON-ответа с полными метриками"""
    recommended_count = sum(1 for p in top_pairs if p['recommendation'])
    json_data = {
        'metadata': {
            'total_receipts': total_receipts,
            'total_pairs_analyzed': len(top_pairs),
            'recommended_pairs': recommended_count,
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'description': 'Анализ совместных покупок (Market Basket Analysis)',
            'metrics': {
                'support': 'Доля чеков с обоими товарами (%)',
                'confidence': 'Вероятность покупки B при покупке A (%)',
                'lift': 'Коэффициент связи товаров (>1 - положительная связь)'
            }
        },
        'top_pairs': top_pairs,
        'all_pairs': top_pairs  # <-- ВАЖНО: Добавлено для совместимости с HTML
    }

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)

    return json_data


def analyze_uploaded_csv(csv_filepath, output_json_path=None):
    """Главная функция для сайта - запускает полный цикл анализа"""
    try:
        receipts = read_receipts_from_csv(csv_filepath)
        if not receipts:
            return {'error': 'Не удалось прочитать CSV или файл пуст'}

        pair_counter, single_counter, total_receipts = count_product_pairs(receipts)

        # Увеличил лимит до 1000, чтобы кнопка "Показать все" работала
        top_pairs = get_top_pairs_with_metrics(pair_counter, single_counter, total_receipts, top_n=1000)

        if not top_pairs:
            return {'error': 'Недостаточно данных для анализа пар (в чеках < 2 товаров)'}

        json_data = create_json_response(top_pairs, total_receipts, output_json_path)
        return json_data

    except ValueError as e:
        return {'error': str(e)}
    except Exception as e:
        return {'error': f'Ошибка анализа: {str(e)}'}