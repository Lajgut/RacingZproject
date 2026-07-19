#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Анализ телеметрии AiM CSV для двух пилотов на МРВ.
Сравнение лучшего круга Кирилла vs Антона.
Чистый Python (без зависимостей), так что работает из коробки.
"""
import csv
import sys
import os

# Скрипт лежит в engineering/data/telemetry/, данные — рядом. Берём пути относительно скрипта.
HERE = os.path.dirname(os.path.abspath(__file__))
ME = os.path.join(HERE, "me/mrw/2026-07-11_mrw_dry_stage3_Bitkov.csv")
ANTON = os.path.join(HERE, "anton/mrw/2026-07-11_mrw_dry_1-40-03_Fedorov.csv")


def parse_segments(path):
    """Достаём Beacon Markers и Segment Times из шапки AiM CSV."""
    beacons = []
    seg_times = []
    meta = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if line.startswith('"Beacon Markers"'):
                beacons = [float(x.strip('"')) for x in line.split(",")[1:] if x.strip()]
            elif line.startswith('"Segment Times"'):
                vals = line.split(",")[1:]
                seg_times = []
                for v in vals:
                    v = v.strip().strip('"')
                    if not v:
                        continue
                    # формат "1:40.03" или "0:30.442"
                    if ":" in v:
                        m, s = v.split(":")
                        seg_times.append(int(m) * 60 + float(s))
                    else:
                        try:
                            seg_times.append(float(v))
                        except ValueError:
                            pass
            elif line.startswith('"Racer"'):
                meta["racer"] = line.split(",")[1].strip().strip('"')
            elif line.startswith('"Date"'):
                meta["date"] = line.split(",")[1].strip().strip('"')
            elif line.startswith('"Comment"'):
                # может содержать запятые — берём всё после первого
                meta["comment"] = ",".join(line.split(",")[1:]).strip().strip('"')
            if line.startswith('"Time"') and "s" in line:
                break
    meta["beacons"] = beacons
    meta["seg_times"] = seg_times
    return meta


def fmt_lap(t):
    """1:40.03 формат."""
    if t is None:
        return "-"
    m = int(t // 60)
    s = t - m * 60
    return f"{m}:{s:06.3f}"


def print_laps(meta, label):
    print(f"\n{'='*60}")
    print(f"  {label}: {meta.get('racer','?')}")
    print(f"  Дата: {meta.get('date','?')}")
    print(f"  Комментарий: {meta.get('comment','?')}")
    print(f"{'='*60}")
    st = meta["seg_times"]
    # сегмент 0 — обычно out-lap (из паддока), последний — in-lap
    print(f"  Всего сегментов: {len(st)}")
    print(f"\n  Круг |  Время   | Дельта к лучшему")
    print(f"  -----+----------+------------------")
    if len(st) < 2:
        print("  (недостаточно кругов)")
        return None
    # считаем, что летающие круги — все кроме первого и последнего
    flying = st[1:-1] if len(st) > 2 else st
    best = min(flying) if flying else None
    for i, t in enumerate(st):
        tag = ""
        if i == 0:
            tag = " (out)"
        elif i == len(st) - 1:
            tag = " (in)"
        else:
            tag = ""
        delta = (t - best) if best else 0
        dstr = f"+{delta:.3f}" if delta >= 0 else f"{delta:.3f}"
        if best and abs(t - best) < 1e-6 and i != 0 and i != len(st) - 1:
            dstr = "  BEST"
        print(f"  {i:<4} | {fmt_lap(t)} | {dstr}{tag}")
    print(f"\n  Лучший летающий круг: {fmt_lap(best)}")
    return best


def load_channel(path, t_start, t_end, want_cols):
    """Грузим строки с t в [t_start, t_end], достаём нужные колонки."""
    rows = []
    headers = None
    with open(path, encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            first = row[0].strip().strip('"')
            # Заголовок каналов: строка, где первый элемент "Time" И есть "GPS Speed"
            # (есть ещё метадата "Time","3:59 AM" — её пропускаем)
            if first == "Time" and headers is None and any("GPS Speed" in c.strip().strip('"') for c in row):
                headers = [c.strip().strip('"') for c in row]
                continue
            if headers is None:
                continue
            # строка единиц измерения (s, km/h, ...) — пропускаем
            if first in ("s",):
                continue
            try:
                t = float(first)
            except ValueError:
                continue
            if t < t_start or t > t_end:
                continue
            rec = {}
            for col in want_cols:
                if col in headers:
                    idx = headers.index(col)
                    try:
                        rec[col] = float(row[idx].strip('"'))
                    except (ValueError, IndexError):
                        rec[col] = None
            rec["t"] = t
            rows.append(rec)
    return rows


def lap_stats(rows, speed_col="GPS Speed"):
    """Мини-статистика по каналу скорости на круге."""
    speeds = [r[speed_col] for r in rows if r.get(speed_col) is not None]
    if not speeds:
        return None
    return {
        "v_max": max(speeds),
        "v_mean": sum(speeds) / len(speeds),
        "v_min": min(speeds),
        "n": len(speeds),
    }


def best_lap_window(meta, idx):
    """Возвращает (t_start, t_end) для лучшего летающего круга по индексу."""
    b = meta["beacons"]
    if idx + 1 >= len(b):
        return None, None
    return b[idx], b[idx + 1]


def best_flying_idx(meta):
    """Индекс лучшего летающего круга (исключая out/in)."""
    st = meta["seg_times"]
    if len(st) < 3:
        return None
    flying = st[1:-1]
    rel_idx = flying.index(min(flying))
    return rel_idx + 1  # +1 т.к. out-lap под индексом 0


def distance_based_compare(me_meta, an_meta, n_segments=4):
    """
    Сравнение speed trace по дистанции круга.
    Привязка: нормируем время круга в 0..1, делим на n_segments,
    в каждом считаем среднюю скорость и интегральную дельту времени.
    """
    me_idx = best_flying_idx(me_meta)
    an_idx = best_flying_idx(an_meta)
    me_s, me_e = best_lap_window(me_meta, me_idx)
    an_s, an_e = best_lap_window(an_meta, an_idx)
    me_dur = me_e - me_s
    an_dur = an_e - an_s

    me_rows = load_channel(ME, me_s, me_e, ["GPS Speed", "Fork", "GAS", "RPM", "SPEED FRONT", "SPEED REAR"])
    an_rows = load_channel(ANTON, an_s, an_e, ["GPS Speed", "Fork", "GAS", "RPM", "SPEED FRONT", "SPEED REAR"])

    print(f"\n{'='*70}")
    print("  СРАВНЕНИЕ ЛУЧШИХ КРУГОВ ПО СЕГМЕНТАМ КРУГА")
    print(f"{'='*70}")
    print(f"  Кирилл круг #{me_idx}: {fmt_lap(me_dur)}  ({len(me_rows)} сэмплов)")
    print(f"  Антон  круг #{an_idx}: {fmt_lap(an_dur)}  ({len(an_rows)} сэмплов)")
    print(f"  Дельта круга: {me_dur - an_dur:+.3f} сек")
    print()
    print(f"  Сегмент |   % круга  | V_ср Кир | V_ср Ант | ∆V_ср | ∆время | Vmax Кир | Vmax Ант")
    print(f"  --------+------------+----------+----------+-------+--------+----------+---------")

    total_delta = 0.0
    for seg in range(n_segments):
        p0 = seg / n_segments
        p1 = (seg + 1) / n_segments
        # фильтруем строки по нормированному времени
        def in_seg(rows, dur, p0, p1):
            out = []
            for r in rows:
                pn = (r["t"] - (me_s if rows is me_rows else an_s)) / dur
                if p0 <= pn < p1:
                    out.append(r)
            return out
        me_seg = in_seg(me_rows, me_dur, p0, p1)
        an_seg = in_seg(an_rows, an_dur, p0, p1)
        me_v = [r["GPS Speed"] for r in me_seg if r.get("GPS Speed") is not None]
        an_v = [r["GPS Speed"] for r in an_seg if r.get("GPS Speed") is not None]
        if not me_v or not an_v:
            continue
        me_vmean = sum(me_v) / len(me_v)
        an_vmean = sum(an_v) / len(an_v)
        dv = me_vmean - an_vmean
        # грубая оценка дельты времени в сегменте:
        # если Кирилл медленнее на dv км/ч при средней ~ (me_vmean),
        # время ~ доля_круга * dur_an, поправка через отношение скоростей
        seg_frac = (p1 - p0)
        # приближённо: ∆t ≈ seg_frac * (me_dur - an_dur) если скорости близки —
        # лучше оценить через: ∆t_seg = seg_frac*an_dur * (v_an/v_me - 1)
        dt = seg_frac * an_dur * (an_vmean / me_vmean - 1) if me_vmean > 0 else 0
        total_delta += dt
        me_vmax = max(me_v)
        an_vmax = max(an_v)
        print(f"    S{seg+1}    | {p0*100:4.0f}-{p1*100:3.0f}%  | "
              f"{me_vmean:7.1f}  | {an_vmean:7.1f}  | {dv:+5.1f} | {dt:+6.3f} | "
              f"{me_vmax:7.1f}  | {an_vmax:6.1f}")

    print(f"  --------+------------+----------+----------+-------+--------+----------+---------")
    print(f"  ИТОГО по сегментам (приближённо): {total_delta:+.3f} сек")
    print(f"  Фактическая дельта круга:         {me_dur - an_dur:+.3f} сек")
    print()
    print("  Интерпретация: ∆V_ср < 0 = Кирилл медленнее (теряет).")
    print("  ∆время > 0 = Кирилл теряет время в этом сегменте.")
    print("  Сегменты по длине круга (0%=старт/финиш, 100%=снова С/Ф).")

    # Топ-скорости и характеристики
    print(f"\n{'='*70}")
    print("  ОБЩИЕ ХАРАКТЕРИСТИКИ ЛУЧШИХ КРУГОВ")
    print(f"{'='*70}")
    me_all = [r["GPS Speed"] for r in me_rows if r.get("GPS Speed") is not None]
    an_all = [r["GPS Speed"] for r in an_rows if r.get("GPS Speed") is not None]
    print(f"  Vmax:       Кирилл {max(me_all):.1f} км/ч | Антон {max(an_all):.1f} км/ч")
    print(f"  V средняя:  Кирилл {sum(me_all)/len(me_all):.1f} км/ч | Антон {sum(an_all)/len(an_all):.1f} км/ч")
    print(f"  Vmin:       Кирилл {min(me_all):.1f} км/ч | Антон {min(an_all):.1f} км/ч")

    # Газ: % времени на полном газу. ВНИМАНИЕ: у Кирилла GAS в абсолютных единицах (0..~1012),
    # у Антона — в процентах (0..100). Нормируем Кирилла к 0..100 по его максимуму на круге.
    me_g_raw = [r["GAS"] for r in me_rows if r.get("GAS") is not None]
    an_g = [r["GAS"] for r in an_rows if r.get("GAS") is not None]
    if me_g_raw and an_g:
        # Определяем шкалу Кирилла: если max > 110 — это абсолютные единицы, нормируем
        me_gmax = max(me_g_raw)
        if me_gmax > 110:
            me_g = [min(g / 10.0, 100.0) for g in me_g_raw]  # ~1012 -> 100
            note = f"(GAS Кирилла нормирован: {me_gmax:.0f}→100)"
        else:
            me_g = me_g_raw
            note = ""
        me_wot = sum(1 for g in me_g if g >= 90) / len(me_g) * 100
        an_wot = sum(1 for g in an_g if g >= 90) / len(an_g) * 100
        print(f"  %% на WOT (GAS>=90): Кирилл {me_wot:.1f}%% | Антон {an_wot:.1f}%% {note}")

    # RPM
    me_r = [r["RPM"] for r in me_rows if r.get("RPM") is not None]
    an_r = [r["RPM"] for r in an_rows if r.get("RPM") is not None]
    if me_r and an_r:
        print(f"  RPM макс:   Кирилл {max(me_r):.0f} | Антон {max(an_r):.0f}")

    return me_rows, an_rows, (me_s, me_e), (an_s, an_e)


def fork_analysis(me_rows, an_rows):
    """Анализ хода вилки. Шкалы у пилотов откалиброваны по-разному,
    поэтому абсолютные значения НЕ сравниваем — только относительное использование
    своего хода (в % от личного размаха)."""
    print(f"\n{'='*70}")
    print("  ХОД ВИЛКИ (Fork) — работа передней подвески")
    print(f"{'='*70}")
    print("  ⚠️ Абсолютные шкалы Fork у пилотов НЕ совпадают (разная калибровка датчика).")
    print("     Сравниваем только ОТНОСИТЕЛЬНОЕ использование своего хода.")
    me_f = [r["Fork"] for r in me_rows if r.get("Fork") is not None]
    an_f = [r["Fork"] for r in an_rows if r.get("Fork") is not None]
    if not me_f or not an_f:
        print("  (нет данных Fork)")
        return
    print(f"  Кирилл: raw min={min(me_f):.1f} max={max(me_f):.1f} размах={max(me_f)-min(me_f):.1f}")
    print(f"  Антон:  raw min={min(an_f):.1f} max={max(an_f):.1f} размах={max(an_f)-min(an_f):.1f}")

    def deep_pct(vals):
        """Доля времени в верхней четверти личного хода."""
        lo, hi = min(vals), max(vals)
        thr = lo + 0.75 * (hi - lo)
        return sum(1 for v in vals if v >= thr) / len(vals) * 100

    def mid_pct(vals):
        """Доля времени в нижней половине личного хода (вилка распущена)."""
        lo, hi = min(vals), max(vals)
        thr = lo + 0.5 * (hi - lo)
        return sum(1 for v in vals if v < thr) / len(vals) * 100

    print(f"  %% времени в верхней ¼ своего хода (глубокое сжатие / под тормозом):")
    print(f"    Кирилл: {deep_pct(me_f):.1f}%% | Антон: {deep_pct(an_f):.1f}%%")
    print(f"  %% времени в нижней половине своего хода (вилка распущена / на газу):")
    print(f"    Кирилл: {mid_pct(me_f):.1f}%% | Антон: {mid_pct(an_f):.1f}%%")


def wheelspin_check(me_rows, an_rows):
    """Проверка wheelspin: SPEED REAR > SPEED FRONT (или VEHICLE)."""
    print(f"\n{'='*70}")
    print("  ПРОБУКСОВКА (SPEED REAR vs FRONT)")
    print(f"{'='*70}")
    def spin_events(rows):
        events = 0
        max_diff = 0
        for r in rows:
            sf = r.get("SPEED FRONT")
            sr = r.get("SPEED REAR")
            if sf is None or sr is None:
                continue
            diff = sr - sf
            if diff > max_diff:
                max_diff = diff
            if diff > 3.0:  # >3 км/ч разница = букс
                events += 1
        return events, max_diff
    me_e, me_m = spin_events(me_rows)
    an_e, an_m = spin_events(an_rows)
    print(f"  Кирилл: {me_e} сэмплов букса | макс.разница {me_m:.1f} км/ч")
    print(f"  Антон:  {an_e} сэмплов букса | макс.разница {an_m:.1f} км/ч")
    print(f"  (букс = SPEED REAR > SPEED FRONT более чем на 3 км/ч)")


def main():
    me = parse_segments(ME)
    an = parse_segments(ANTON)

    me_best = print_laps(me, "КИРИЛЛ (я)")
    an_best = print_laps(an, "АНТОН (референс)")

    if me_best and an_best:
        gap = me_best - an_best
        print(f"\n{'='*60}")
        print(f"  ДЕЛЬТА: Кирилл {fmt_lap(me_best)} - Антон {fmt_lap(an_best)}")
        print(f"  Разница: {gap:+.3f} сек (Кирилл {'медленнее' if gap>0 else 'быстрее'})")
        print(f"{'='*60}")

    me_rows, an_rows, _, _ = distance_based_compare(me, an, n_segments=4)
    fork_analysis(me_rows, an_rows)
    wheelspin_check(me_rows, an_rows)


if __name__ == "__main__":
    main()
