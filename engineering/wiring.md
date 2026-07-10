# Электрика / Wiring — Ducati Panigale V2

> Схемы подключения доп. оборудования к AIM MXL2. Порядок пинов сверять с официальными PDF AiM.

## AIM LCU One (лямбда-контроллер) → MXL2

### Версия устройства
- **LCU One Analog** (4-pin Binder 712, металлический резьбовой разъём)
- Зонд: Bosch LSU 4.9
- Данные: аналоговый сигнал 0–5V (не CAN)

### Принцип подключения (3 линии)
| Линия | LCU One (Binder 712) | MXL2 |
|---|---|---|
| Питание + (+Vb, 9–15V) | pin питания | switched +12V |
| Масса (GND) | pin GND | GND (общая с MXL2) |
| Сигнал (Lambda OUT 0–5V) | pin сигнала | свободный аналоговый вход |

### ⚠️ Порядок пинов Binder 712 — сверить с PDF
Точные номера пинов не по памяти. Источники:
- AiM LCU-One Analog Pinout: https://www.aimtechnologies.com/aim-support/docs/Pinout_LCU-OneAnalog_100_eng.pdf
- me-mo-tec (CAN + Analog): https://www.me-mo-tec.de/content/media/2003_Pinout_LCU-one_100_eng.pdf

### Аналоговые входы MXL2
- Выбрать свободный аналоговый канал на 22-pin разъёме
- Распиновка: MXL2 Tech Sheet / Standard Harness PDF
  - https://www.aimsportsystems.com.au/download/technical-sheets/aim_mxl2_107.pdf
  - https://support.aimshop.com/product-documentation/pdf/MXL2/Harness.pdf

### Настройка в Race Studio 2 (аналоговый канал)
1. Configure MXL2 → Channels → выбрать аналоговый вход
2. Масштабирование: 0–5V → λ 0.7–1.2 (или AFR)
3. Имя канала: Lambda / AFR, вывести на экран
4. **Аларм:** λ > 0.93 при WOT (бедно, опасно)

### Целевые значения (Panigale V2, Supersport, стоковая карта)
- WOT: λ ≈ 0.85–0.90 (AFR ≈ 12.5–13.1)
- Беднее λ 0.92 на полном газу → риск детонации

### Нюансы установки
- Питание LCU One: **только switched +12V** (от замка зажигания), НЕ постоянный +
  - иначе зонд греется при парковке → сажает АКБ, сокращает ресурс
- Положение зонда: в коллектор **до катализатора** (upstream)
- Калибровка LSU 4.9: free-air при первом включении (зонд вне выхлопа)
