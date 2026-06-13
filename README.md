# OverLex

**Ctrl + Middle Click** на любом слове — мгновенный перевод EN→RU прямо на экране.

Работает поверх игр, браузеров, любых приложений.

## Скачать

| Платформа | Ссылка |
|---|---|
| Windows 10/11 | [OverLex-Windows.zip](../../releases/latest) |
| macOS 12+ | [OverLex.dmg](../../releases/latest) |

## Использование

| Действие | Результат |
|---|---|
| `Ctrl` + Middle Click | Перевести слово под курсором |
| Клик по оверлею | Закрыть |
| 5 секунд | Авто-скрытие |
| Иконка в трее | Пауза / Автозапуск / Выйти |

## Установка из исходников

```bash
pip install -r requirements.txt
python overlex.py
```

**Windows:** PowerShell встроен, ничего дополнительно не нужно.  
**macOS:** нужен Xcode Command Line Tools (`xcode-select --install`) для компиляции Swift OCR-хелпера.  
**macOS:** в System Settings → Privacy → Accessibility добавь OverLex.

## Сборка

**Windows:**
```bat
build_win.bat
```

**macOS:**
```bash
bash build_mac.sh
```
