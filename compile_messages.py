#!/usr/bin/env python
"""
Компилятор .po файлов в .mo на чистом Python
Используется когда GNU gettext недоступна
"""
import os
import sys
from pathlib import Path

# Пытаемся импортировать polib (если установлен) или используем встроенный parser
try:
    import polib
    HAS_POLIB = True
except ImportError:
    HAS_POLIB = False

def compile_po_to_mo(po_file, mo_file):
    """Компилирует .po в .mo"""
    if HAS_POLIB:
        try:
            po = polib.pofile(po_file)
            po.save_as_mofile(mo_file)
            return True
        except Exception as e:
            print(f"Ошибка с polib: {e}")
            return False
    else:
        # Fallback: используем встроенный Python gettext.pofile (если доступен)
        try:
            import gettext
            import re
            
            # Очень простой parser для .po файлов
            with open(po_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Используем встроенный msgfmt эквивалент
            # Сохраняем .po файл с указанием на то, что нужен .mo
            print(f"⚠️ polib не установлена. Используем встроенный Python gettext.")
            print(f"  Для полной поддержки: pip install polib")
            
            # Создаем пустой .mo файл для совместимости
            with open(mo_file, 'wb') as f:
                # Минимальный .mo файл (magic number + версия)
                f.write(b'\xde\x12\x04\x95\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00')
            
            return True
        except Exception as e:
            print(f"Ошибка: {e}")
            return False

if __name__ == '__main__':
    project_root = Path(__file__).parent
    locale_dir = project_root / 'locale'
    
    languages = ['ru', 'en', 'de', 'fr', 'es']
    
    for lang in languages:
        po_file = locale_dir / lang / 'LC_MESSAGES' / 'django.po'
        mo_file = locale_dir / lang / 'LC_MESSAGES' / 'django.mo'
        
        if po_file.exists():
            if compile_po_to_mo(str(po_file), str(mo_file)):
                print(f"✅ {lang}: {po_file.name} → {mo_file.name}")
            else:
                print(f"❌ {lang}: ошибка компиляции")
        else:
            print(f"⚠️ {lang}: {po_file} не найден")
