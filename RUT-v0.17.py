#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sugarcube_translate — машинный перевод игр через Google Translate: SugarCube 2 (Twine), Ren'Py, Godot 4,
а на лету — любых игр на HTML/JavaScript.

Ren'Py и Godot 4: сценарий и код игры не меняются — в игру кладётся словарь и маленький модуль,
который подменяет текст при показе (Alt+T в игре — оригинал/перевод, --remove — убрать перевод).
Понимает папку игры, .exe, .pck, архивы .rpa, игры только с .rpyc и распакованные APK.
Ren'Py ещё и на лету (-l / -c): игра переводит то, что появляется на экране, — и текст, который
она собирает сама во время игры (кнопка с глобусом «RU» в углу — язык, «Обновить», исправление
перевода, инструменты Ren'Py: рендерер, консоль — и всё это без клавиатуры, на телефоне тоже).

SugarCube 2:

Понимает:  собранную игру .html (Twine 2 и Twine 1), файл .twee/.tw и папку с исходниками
           (проект Tweego: .tw/.twee + .js + .css). Результат — в том же формате: из .html сразу
           получается готовая переведённая .html, Tweego не нужен.

За один запуск получаются ДВЕ версии, а каждая фраза отправляется в переводчик только один раз:
  <игра>_ru_safe  — безопасная: строки-данные в JavaScript, похожие на ключи, не трогаются;
  <игра>_ru_full  — полная: то же самое + короткие строки-данные (описания, названия ...).
                    Перевод полнее, но возможны баги. В отчёте такие строки помечены «ТОЛЬКО FULL».
Только одна версия: --mode safe или --mode full (потом можно доделать вторую — всё возьмётся из кэша).

Что переводится:
  * текст пассажей (код, переменные, HTML, цели ссылок не трогаются);
  * подписи ссылок и кнопок: [[Текст|Пассаж]], <<link "Текст">>, <<button>>, <<option>> ...;
  * строки внутри JavaScript (Story JavaScript, <<script>>, <<set>>, <<print>>, аргументы виджетов),
    кроме строк-ключей: сравнения, case, имена пассажей, CSS-классы, селекторы, имена свойств и т.п.;
  * склейки "You have " + $gold + " coins" и шаблоны `${He} smiles` — целой фразой;
  * интерфейс SugarCube (Сохранения, Настройки, Начать заново ...) — при переводе на русский.

Грамматика рода: если во фразе есть переменная-местоимение ($He, $his, ${He}, $pronoun ... и любые
переменные, в которые игра кладёт "he"/"she" — они находятся сами), переводятся варианты «она»/«он»,
а игра выбирает нужный во время прохождения (функция ruGender() добавляется автоматически).

Защита: каждый пассаж после перевода проверяется (макросы, ссылки, синтаксис JS). Не прошёл —
остаётся на английском и попадает в отчёт <выход>.report.tsv.

Установка:  pip install requests
Запуск:     python sugarcube_translate.py "Моя игра.html"
Подробнее:  python sugarcube_translate.py -h
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

HELP_INTRO = """
Машинный перевод игр через Google Translate (по умолчанию — на русский): SugarCube 2 (Twine), Ren'Py,
Godot 4 и (на лету) любые игры на HTML/JavaScript. Движок скрипт определяет сам.

КАКИЕ ФАЙЛЫ МОЖНО ДАВАТЬ
  • SugarCube: игра .html (Twine 2 и старый Twine 1), исходник .twee/.tw, папка с готовой игрой
    (главный .html скрипт найдёт сам; если их несколько — например, разные версии игры, — спросит,
    какой переводить) или папка с исходниками Tweego. Результат — переведённый .html рядом.
  • Ren'Py (любая версия; годится и игра только с .rpyc/.rpa): папка игры, её .exe или .py/.sh,
    или папка распакованного APK (apktool d игра.apk).
  • Godot 4 (Godot 3 и старше — нет): папка игры, .exe/.x86_64 (пак .pck рядом или внутри программы),
    сам .pck или папка распакованного APK.
  • Прочие игры на HTML/JavaScript (Lilith's Throne CE, Harlowe…): только перевод на лету (-l / -c).

REN'PY И GODOT: КАК ЭТО РАБОТАЕТ
  Сценарий и код игры не меняются: в игру кладётся словарь перевода и маленький модуль, который
  подменяет текст в момент показа (реплики, меню, интерфейс). Сохранения остаются совместимыми.
    Ren'Py:  game/zz_rut_translate.rpy (в APK — .rpyc) + game/rut_translation.json
    Godot:   папка rut_translate и override.cfg внутри пака; оригинал пака — рядом, *.rut-orig
  В игре Alt+T — показать оригинал / перевод. Убрать перевод: тот же запуск с --remove (-R).
  Распакованный APK после перевода соберите и подпишите заново (apktool b, uber-apk-signer).
  Ren'Py — ещё и перевод на лету (-l / -c): модуль в игре переводит текст в момент показа, в том числе
  тот, что игра склеивает сама («У вас » + 5 + « монет»). Заранее переводить игру не нужно.

ЧТО ПОЛУЧИТСЯ ДЛЯ SUGARCUBE (рядом с игрой)
  <игра>_ru_safe.html        безопасная версия — не трогает строки-ключи в коде игры
  <игра>_ru_full.html        полная версия — переводит больше, но возможны баги
  <игра>_ru_*.report.tsv     отчёт: какие строки кода переведены (открывается в Excel);
                             строки только из full помечены «ТОЛЬКО FULL (риск)»
  <игра>.ru.cache.json       уже переведённое — не удаляйте: благодаря ему перевод
                             продолжается с места остановки и не тратит лимиты повторно
""".strip("\n")

HELP_EXAMPLES = r"""
ПРИМЕРЫ
  Проверить, работает ли переводчик:
      python sugarcube_translate.py --check
  Ren'Py или Godot 4 — папка игры (или её .exe / распакованный APK):
      python sugarcube_translate.py "C:\Games\MyVisualNovel"
      python sugarcube_translate.py "C:\Games\MyGodotGame\game.exe" -f
      python sugarcube_translate.py "D:\apk\mygame" -uk             (папка после apktool d)
  Ren'Py — перевод на лету: игра переводит сама через Google (работает и на ПК, и в APK):
      python sugarcube_translate.py "C:\Games\MyVisualNovel" -l
  Ren'Py — перевод на лету через окно скрипта (быстрее, скрипт сам запустит игру):
      python sugarcube_translate.py "C:\Games\MyVisualNovel" -c
  Ren'Py — добавить в игру переводы, выученные на телефоне (файл rut_live.json из папки сохранений):
      python sugarcube_translate.py "D:\apk\mygame" -i rut_live.json
  Убрать перевод из игры Ren'Py/Godot (вернуть оригинал):
      python sugarcube_translate.py "C:\Games\MyVisualNovel" -R      (то же: --remove)
  Сохранить структуру кода игры (без текста) для настройки скрипта:
      python sugarcube_translate.py "Моя игра.html" --analyze
  Перевод НА ЛЕТУ — файл игры с переводом внутри (ПК двойным щелчком, Android), окно скрипта не нужно:
      python sugarcube_translate.py "Моя игра.html" -l              (то же: --live)
  Перевод на лету через окно скрипта (консоль) — ПК, переводы копятся на диске:
      python sugarcube_translate.py "Моя игра.html" -c              (то же: --console-live)
  Игра не на SugarCube (например, Lilith's Throne CE, Harlowe) — только перевод на лету:
      python sugarcube_translate.py "C:\Games\Liliths_Throne_CE" -l
  Добавить в файл переводы, сохранённые в игре на телефоне («Сохранить переводы в файл»):
      python sugarcube_translate.py "Моя игра.html" -i "Моя игра - переводы.json"
  Узнать объём перевода, ничего не переводя:
      python sugarcube_translate.py "Моя игра.html" -d              (то же: --dry-run)
  Обычный перевод (обе версии):
      python sugarcube_translate.py "Моя игра.html"
  Медленнее, но реже блокируют:
      python sugarcube_translate.py "Моя игра.html" --delay 3
  Быстрее (одновременно на все рабочие адреса Google):
      python sugarcube_translate.py "Моя игра.html" -f              (то же: --fast)
  Только безопасная версия:
      python sugarcube_translate.py "Моя игра.html" -m safe         (то же: --mode safe)
  Исходник .twee или папка с исходниками:
      python sugarcube_translate.py "game.twee"
      python sugarcube_translate.py "C:\Games\src"
  Свои имена результата (получится FC_ru_safe.html и FC_ru_full.html):
      python sugarcube_translate.py "Free Cities.html" FC_ru
  Переводчик по ключу (больше лимиты, стабильнее):
      python sugarcube_translate.py "Моя игра.html" -e deepl -k КЛЮЧ
      python sugarcube_translate.py "Моя игра.html" --engine microsoft --key КЛЮЧ --region westeurope
  Не больше 450 000 символов за запуск (под бесплатный лимит ключа):
      python sugarcube_translate.py "Моя игра.html" --engine deepl --key КЛЮЧ --max-chars 450000
  Если в full-версии что-то сломалось: найдите строку в отчёте .report.tsv,
  впишите её (колонка «было», без кавычек) в keep.txt и запустите снова:
      python sugarcube_translate.py "Моя игра.html" --keep keep.txt

КОРОТКИЕ ФЛАГИ (каждый пишите отдельно: -l -f, а не -lf)
  -l --live        -c --console-live   -i --import      -m --mode        -d --dry-run
  -a --analyze     -C --check          -f --fast        -F --fresh       -D --delay
  -e --engine      -k --key            -p --port        -B --no-browser  -w --live-wait
  -M --max-chars   -W --max-wait       -s --skip        -K --keep        -t --translate-list
  -g --glossary    -R --remove      -ru, -uk, -de …  — язык перевода (то же: --to ru)

ПОЛЕЗНО ЗНАТЬ
  • -c / --console-live (перевод на лету через окно скрипта): скрипт запускает игру в браузере сам и переводит текст, когда он
    появляется на экране, — целыми фразами, как их собрала игра. Код и переменные игры не меняются,
    поэтому логика не ломается. Переводится только то, что вы видите (лимиты тратятся понемногу),
    и всё запоминается: второй раз — мгновенно. Нужен интернет; окно скрипта не закрывать.
    Сохранения в этом режиме свои: перенести — «Сохранения → на диск / с диска».
    Язык указывать не нужно: игра открывается на языке браузера / телефона (если это язык оригинала —
    в оригинале), язык выбирается в боковой панели игры, блок «Перевод» (там все языки Google и «Свой
    код языка…»; выбор запоминается). Флаг -ru и т.п. здесь только задаёт язык по умолчанию. Там же «⟳ Обновить перевод» — если из-за обрыва связи
    часть текста осталась английской (сам скрипт тоже повторяет такие места раз в минуту), и
    строка «Google: N из M серверов отвечают». Части пассажа переводятся сразу на разные адреса.
  • -l / --live: файл <игра>_live.html, который работает сам — на ПК двойным щелчком, на Android
    в браузере или JoiPlay. Внутри лежат переводы всего, что вы видели в -c, на всех языках;
    новый текст браузер переводит через Google сам и запоминает. Этот же файл обновляется и после
    каждой игры через -c (при выходе: exit и Enter или Ctrl+C). Переведённое в браузере (например, на телефоне):
    «Перевод» → «Сохранить переводы в файл», затем на ПК: -i <этот файл> — и всё окажется
    в <игра>_live.html. Если Google не пустит браузер, в панели будет «нет связи с Google».
  • Точность перевода на лету: числа переводчик видит в «своей» грамматической форме («1 монета»,
    «2 монеты», «5 монет»), короткие значения — вместе с подписью рядом («Грудь: Упругая»), фразы со
    ссылками при сбое переводятся ещё раз целиком. Если Google всё же ошибся: в панели «Перевод» —
    «✍ Исправить фразу», затем нажать на фразу в игре и вписать свой вариант. Исправление запоминается,
    «Перевести страницу заново» его не трогает, и оно попадает в «Сохранить переводы в файл» / --import.
  • Игры не на SugarCube (свой движок на HTML/JavaScript — Lilith's Throne CE и т.п., а также Twine
    Harlowe/Snowman): заранее их не перевести, но -l и -c работают — переводится то, что
    на экране. Язык и кнопки — значок 🌐 в правом верхнем углу игры. Укажите папку игры или её
    index.html; рядом появится index_live.html (открывать его, картинки и скрипты игры — те же).
  • Шепелявость (Free Cities и похожие игры): в переводе шепелявит только то, что шепелявил персонаж
    в оригинале — слово («'Master' звучит как 'Маштер'») или его реплика целиком, и по правилам языка
    перевода: кириллица — с/ц → ш, з → ж; английский и прочие латинские — th; испанский — z;
    греческий — θ; арабский, персидский — ث; иврит — ת; хинди — थ; японский — しゃ/しゅ. В языках без
    таких букв (китайский, корейский, тайский…) текст остаётся обычным.
  • Строки со ссылками через «|» («Тонкие | Нормальные | Огромные») проверяются: если переводчик
    разбил, потерял или оставил по-английски одну из ссылок, фраза переводится ещё раз.
  • Короткие обрывки («devoted», «Perky», «Wide-set») переводятся с подсказкой — соседним текстом
    строки, поэтому выходит «предана», «Упругая», «Широко посаженная», а не «преданный», «Весёлый»,
    «Широкий набор». Если подсказка не сработала, берётся обычный перевод. Выключить: --no-context
  • Перевод можно прервать: введите exit и нажмите Enter (на телефоне так проще, чем Ctrl+C), или Ctrl+C,
    или закройте окно — повторный запуск той же команды продолжит с того же места. На вопросы скрипта
    (язык и т.п.) тоже можно ответить exit — выйти.
  • Если переводчик блокирует, скрипт ждёт сам. Если блок слишком долгий — соберёт игру
    из уже переведённого (остальное на английском) и остановится; запустите позже снова.
  • Имя файла с пробелами берите в кавычки: "Free Cities v 0.10.7.1.html".
  • Ren'Py и Godot: переводятся реплики, выборы в меню, интерфейс и подписи из кода; текст,
    который игра склеивает из кусков во время игры («У вас » + 5 + « монет»), остаётся как есть —
    кроме перевода на лету в Ren'Py (-l / -c): там переводится и он.
  • Ren'Py, перевод на лету (-l / -c; Ren'Py 6.99 и новее, ПК и APK): в игру кладётся модуль, который
    переводит текст, когда он появляется на экране. Пока вы читаете реплику, следующие строки сценария уже переводятся; если
    перевод не успел, реплика ждёт до 3 секунд (-w СЕК), потом показывается как есть и меняется сама,
    когда перевод придёт (реплика с паузами {w}/{p} тогда показывается целиком, без пауз, — иначе её
    нельзя было бы заменить). Меню, настройки и HUD игры переводятся заранее, пока Ren'Py их готовит.
    В углу экрана — кнопка с глобусом (код языка) и рядом «⟳» (обновить: повторить то, что не перевелось из-за
    связи; оранжевая, если были сбои). Глобус (на ПК ещё Alt+L) открывает панель: язык (первый в списке —
    оригинал игры) и «Обновить», «Показать оригинал» (Alt+T), «Перевести заново» и «Исправить фразу»
    (список того, что сейчас на экране, и последних реплик). Панель говорит на языке, который на экране:
    при оригинале — на языке игры. Язык при первом запуске — как у телефона / Windows (если это язык
    оригинала или его не узнать — игра начинается в оригинале), выбранный в игре запоминается. В «Ещё…»: сохранить переводы в файл, угол кнопки, скрывать ли её во
    время игры (в меню игры она есть всегда — так её можно вернуть без клавиатуры) и инструменты Ren'Py,
    которые обычно открываются только с клавиатуры: выбор рендерера (GL / ANGLE / GLES), меню
    доступности (шрифт, размер текста) и консоль (закрыть — кнопкой в углу).
    Если шрифт игры без кириллицы, такой текст показывается шрифтом Ren'Py (DejaVuSans).
    Имена персонажей переводятся как имена (Mum → Мама, Violet → Вайолет); имя игрока ([name]) не трогается.
    «Обновить» сразу меняет то, что на экране, остальное — понемногу в фоне (игра не замирает).
    Выученное в игре хранится в папке сохранений игры (rut_live.json) — его можно встроить в игру на ПК
    через -i. Готовый обычный перевод (если игру уже переводили без -l) тоже встраивается, переводится
    только остальное. -c: окно скрипта не закрывать, выход — exit и Enter (или Ctrl+C): всё переведённое
    встроится в игру.
    Повторный запуск берёт готовое из кэша (rut_cache.<язык>.json в папке игры) и доводит остальное.
  • Godot 4.3+ хранит скрипты сжатыми (zstd): чтобы брать строки и из них — pip install zstandard
  • Нужна только библиотека requests:  pip install requests
"""

# ===========================================================================
# Настройки по умолчанию
# ===========================================================================

# Имя переменной -> (мужская форма, женская форма). Регистр первой буквы учитывается сам,
# цифры в конце (He2, his3) означают другого персонажа.
GENDER_BASE = {
    "he": ("he", "she"), "she": ("he", "she"),
    "him": ("him", "her"), "his": ("his", "her"), "hers": ("his", "hers"),
    "himself": ("himself", "herself"), "herself": ("himself", "herself"),
    "boy": ("boy", "girl"), "girl": ("boy", "girl"),
    "boys": ("boys", "girls"), "girls": ("boys", "girls"),
    "man": ("man", "woman"), "woman": ("man", "woman"),
    "men": ("men", "women"), "women": ("men", "women"),
    "husband": ("husband", "wife"), "wife": ("husband", "wife"),
    "son": ("son", "daughter"), "daughter": ("son", "daughter"),
    "brother": ("brother", "sister"), "sister": ("brother", "sister"),
    "father": ("father", "mother"), "mother": ("father", "mother"),
    "lord": ("lord", "lady"), "lady": ("lord", "lady"),
    "king": ("king", "queen"), "queen": ("king", "queen"),
    "pronoun": ("he", "she"), "possessive": ("his", "her"),
    "possessivePronoun": ("his", "hers"), "object": ("him", "her"),
    "objectReflexive": ("himself", "herself"), "noun": ("boy", "girl"),
}

# Функции, строковые аргументы которых — ключи/селекторы/имена (не переводить).
# Значение: "all" или множество номеров аргументов (с нуля).
KEY_FUNCS = {
    **{f: "all" for f in (
        "includes indexOf lastIndexOf startsWith endsWith match matchAll search test "
        "localeCompare hasOwnProperty hasOwn propertyIsEnumerable split "
        "getElementById getElementsByClassName getElementsByTagName getElementsByName "
        "querySelector querySelectorAll closest find is filter not children parents "
        "contains add remove toggle replaceWith addClass removeClass toggleClass hasClass "
        "createElement getAttribute removeAttribute hasAttribute toggleAttribute "
        "require import RegExp eval Function evalJavaScript evalTwineScript "
        "toLocaleString toLocaleDateString toLocaleTimeString toLocaleUpperCase toLocaleLowerCase "
        "DateTimeFormat NumberFormat PluralRules RelativeTimeFormat Collator ListFormat "
        "get has delete getItem removeItem recall forget getVar visited visitedTags "
        "lastVisited tags passage hasVisited play goTo show $ jQuery Story "
        "dispatchEvent removeEventListener off clone".split())},
    **{f: {0} for f in (
        "replace replaceAll setAttribute attr prop css data on one trigger "
        "addEventListener setItem setVar memorize addToggle addList addRange "
        "insertAdjacentHTML insertAdjacentElement insertAdjacentText".split())},
    "setup": {1},
}
# Функции, строки в которых — точно текст для игрока.
OUT_FUNCS = {
    **{f: "all" for f in (
        "push append prepend after before wiki print text html alert confirm prompt "
        "createTextNode notify toast addParagraph addHeader".split())},
    **{f: {0} for f in "link passageLink button setup Wikifier".split()},
    "insertAdjacentHTML": {1}, "Wikifier": {1},
}
ATTR_PROPS = set(("className id type name href src tagName display cursor color background "
                  "backgroundColor width height position float visibility overflow fontFamily "
                  "fontWeight textAlign passage tag key selector target rel role dataset").split())
OUT_PROPS = set("textContent innerText innerHTML outerHTML title placeholder alt ariaLabel label "
                "caption nodeValue".split())
KEY_KEYS = set(("id class className classes cls type tag tagName passage href src key selector "
                "weekday month day year hour minute second era timeZone timeZoneName hour12 hourCycle dateStyle "
                "timeStyle dayPeriod localeMatcher numberingSystem calendar currency currencyDisplay unit "
                "unitDisplay notation compactDisplay signDisplay useGrouping "
                "style css event events sound audio image img icon font color colour mode kind "
                "variable var setting prop property attr attribute format align target group "
                "slot priority status state category tags locationTags location npc macro widget "
                "handler event trigger").split())
OUT_KEYS = set(("label title text desc description tooltip note notes caption message msg prompt "
                "placeholder header heading content hint summary intro flavor flavour "
                "details info").split())

# Макросы SugarCube
LABEL_MACROS = set("link button linkreplace linkappend linkprepend click option back return".split())
JS_MACROS = set("set run print = - if elseif for switch".split())
OUTPUT_MACROS = set("print = -".split())
KEY_MACROS = set(("goto include display widget audio cacheaudio createaudiogroup createplaylist "
                  "playlist masteraudio waitforaudio removeaudiogroup removeplaylist track "
                  "addclass removeclass toggleclass copy remove replace append prepend timed "
                  "repeat type textbox textarea numberbox checkbox radiobutton listbox cycle "
                  "optionsfrom case unset forget remember memorize actions choice do redo "
                  "capture stop next break continue done").split())

SKIP_TAGS = {"stylesheet", "Twine.image", "Twine.audio", "Twine.video", "Twine.vtt"}
SKIP_NAMES = {"StoryData", "StoryTitle", "StoryIncludes"}

# ===========================================================================
# Общие структуры
# ===========================================================================

M_OPEN, M_CLOSE = "\uE000", "\uE001"
MARK = re.compile(M_OPEN + r"(\d+)" + M_CLOSE)
MARK_SPLIT = re.compile("(" + M_OPEN + r"\d+" + M_CLOSE + ")")
LATIN = re.compile(r"[A-Za-z]")
PH_OUT = "⟦{}⟧"
PH_IN = re.compile(r"[⟦\[]\s*(\d+)\s*[⟧\]]")

OPTS = argparse.Namespace(js=True, gender=True, aggressive=False)
GENDER = {}
ITEMS, TEXTS, JSUNITS, CHAINS = [], [], [], []
KEYS, PASSAGES, CSS, KEEP, IDENTS = set(), set(), set(), set(), set()
CUR = {"passage": ""}


class TStr(str):
    """Кусок переведённого текста (в отличие от кусков кода)."""


def reg(item):
    ITEMS.append(item)
    item.marker = f"{M_OPEN}{len(ITEMS) - 1}{M_CLOSE}"
    return item.marker


def expand(s):
    """Метки -> текст (кроме выражений JS: их забирают шаблоны и склейки)."""
    def rep(m):
        it = ITEMS[int(m.group(1))]
        return m.group(0) if isinstance(it, Expr) else it.render()
    prev = None
    while prev != s and M_OPEN in s:
        prev, s = s, MARK.sub(rep, s)
    return s


def expand_parts(s):
    out = []
    for p in MARK_SPLIT.split(s):
        m = MARK.fullmatch(p)
        if m:
            out.extend(ITEMS[int(m.group(1))].parts())
        elif p:
            out.append(p)
    return out


def flatten(parts):
    out = []
    for p in parts:
        if isinstance(p, str) and M_OPEN in p:
            sub = expand_parts(p)
            out.extend(TStr(x) if isinstance(p, TStr) and isinstance(x, str) else x for x in sub)
        else:
            out.append(p)
    return out


class Raw:
    def __init__(self, s, kind):
        self.s, self.kind = s, kind
        self.wrapv = False

    def render(self):
        if self.wrapv and VALUES["on"] and value_var_ok(self):
            return naked_print(self.s)  # "white" на экране — «белый», в игре — "white"
        return expand(self.s)

    def parts(self):
        if self.wrapv and VALUES["on"] and value_var_ok(self):
            return [self.render()]
        return expand_parts(self.s)


class Seq:
    kind = "macro"

    def __init__(self, parts, kind="macro"):
        self.p, self.kind = parts, kind

    def render(self):
        return "".join(x if isinstance(x, str) else x.render() for x in self.p)

    def parts(self):
        return expand_parts(self.render())


class Expr:
    kind = "expr"

    def __init__(self, seq, src):
        self.seq, self.src = seq, src.strip()

    def render(self):
        return self.seq.render()

    def parts(self):
        return [self]


# ===========================================================================
# Разметка SugarCube
# ===========================================================================

PROTECT = re.compile(
    r"(?P<comment><!--[\s\S]*?-->|/\*[\s\S]*?\*/|/%[\s\S]*?%/)"
    r"|(?P<verbatim>\"\"\"[\s\S]*?\"\"\"|<nowiki>[\s\S]*?</nowiki>|\{\{\{[\s\S]*?\}\}\})"
    r"|(?P<code><<script\b[^>]*>>[\s\S]*?<</script>>|<script\b[^>]*>[\s\S]*?</script>|<style\b[\s\S]*?</style>)"
    r"|(?P<macro><<(?=\s*/?\s*(?:[A-Za-z]|=|-)))"
    r"|(?P<image>\[(?:img|image)\[[^\]]*\](?:\[[^\]]*\])*\])"
    r"|(?P<linkopen>\[\[)"
    r"|(?P<url>https?://[^\s<>\"'`]+)"
    r"|(?P<tag></?[A-Za-z!][^<>]*>)"
    r"|(?P<style>@@(?:[^;@\n<>]{0,80};)*)"
    r"|(?P<var>(?<![\w$])(?:\$[A-Za-z_$][\w$]*|_[A-Za-z$][\w$]*)(?:\.[A-Za-z_$][\w$]*|\[[^\]\n]*\])*)"
    r"|(?P<fmt>''|//|__|==|\^\^|~~)"
    r"|(?P<entity>&(?:#\d+|#x[0-9A-Fa-f]+|[A-Za-z]+);)"
    r"|(?P<linestart>^(?:!{1,6}|[*#]+(?=\s)|>+))"
    r"|(?P<brk>\]\])",
    re.M,
)
MACRO_RE = re.compile(r"^<<\s*(/?)\s*([A-Za-z][\w-]*|=|-)([\s\S]*?)>>$")
def scan_link(s, i):
    """[[текст|пассаж][сеттер]] начиная с позиции i. Сеттер может содержать скобки и строки:
    [$x[$i].type = "a]b"]. Возвращает (конец, тело, сеттер|None) или None."""
    n, j, depth = len(s), i + 2, 0
    while j < n:  # конец текста ссылки; внутри могут быть скобки: [[$ev[_i]|P]]
        c = s[j]
        if c == "\n":
            return None
        if c == "[":
            if s.startswith("[[", j) and depth == 0:
                return None
            depth += 1
        elif c == "]":
            if depth == 0:
                break
            depth -= 1
        j += 1
    if j >= n:
        return None
    body, k = s[i + 2:j], j + 1
    if k < n and s[k] == "]":
        return k + 1, body, None
    if k < n and s[k] == "[":
        depth, q, t = 1, None, k + 1
        while t < n:
            c = s[t]
            if q:
                if c == "\\":
                    t += 2
                    continue
                if c == q:
                    q = None
            elif c in "\"'`":
                q = c
            elif c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    break
            elif c == "\n":
                return None
            t += 1
        else:
            return None
        if t + 1 < n and s[t + 1] == "]":
            return t + 2, body, s[k + 1:t]
    return None


def ok_label(s):
    return bool(LATIN.search(s)) and "\n" not in s and not re.search(r"[$<>]|(?<![\w$])_[A-Za-z]", s)


class Label:
    """Подпись ссылки/кнопки: before + перевод + after."""
    kind = "label"

    def __init__(self, before, text, after, quote=None):
        self.before, self.after, self.quote = before, after, quote
        lead, core, trail = split_ws(text)
        self.lead, self.trail = lead, trail
        self.text = Text(core)

    def _text(self):
        out = []
        for p in self.text.parts():
            out.append(fix_label(p, self.quote) if isinstance(p, TStr) else p)
        return out

    def parts(self):
        after = self.after.parts() if isinstance(self.after, Seq) else [self.after]
        return flatten([self.before, self.lead] + self._text() + [self.trail] + after)

    def render(self):
        return "".join(p if isinstance(p, str) else p.marker for p in self.parts())


def link_label(body, setter, prefix="", suffix=""):
    if setter is None:
        tail = "]]"
    else:
        tail = Seq(["][", process_js(setter, "data"), "]]"]) if OPTS.js else "][" + setter + "]]"
    if "|" in body:
        text, target = body.split("|", 1)
        before, mid = "[[", "|" + target
    elif "->" in body:
        text, target = body.rsplit("->", 1)
        before, mid = "[[", "->" + target
    elif "<-" in body:
        target, text = body.split("<-", 1)
        before, mid = "[[" + target + "<-", ""
    else:
        text, before, mid = body, "[[", "|" + body
    after = Seq([mid, tail, suffix]) if isinstance(tail, Seq) else mid + tail + suffix
    if VAR_PATH.fullmatch(text.strip()) and value_var_ok(Raw(text.strip(), "var")):
        return VarLink(prefix + before, text, after)  # [[$event[_i]|P]] → текст ссылки через ruT()
    if not ok_label(text):
        return None
    return Label(prefix + before, text, after)


VAR_PATH = re.compile(r"[$_][A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*|\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\])*")


class VarLink:
    """Ссылка, у которой текст — переменная: SugarCube вычисляет текст ссылки, поэтому
    [[ruT($x)|P]] покажет значение переведённым, а сама переменная не меняется."""
    kind = "label"

    def __init__(self, before, text, after):
        self.before, self.text, self.after = before, text, after

    def render(self):
        after = self.after.render() if isinstance(self.after, Seq) else self.after
        t = f"ruT({self.text.strip()})" if VALUES["on"] else self.text
        return self.before + t + after

    def parts(self):
        return expand_parts(self.render())


def macro_item(s):
    it = _macro_item(s)
    m = MACRO_RE.match(s)
    it.mname = m.group(2) if m else ""
    if it.mname:
        IDENTS.add(it.mname)
    if isinstance(it, (Raw, Seq)):
        it.kind = "macro"
    return it


def _macro_item(s):
    m = MACRO_RE.match(s)
    prev = CUR.get("macro")
    CUR["macro"] = m.group(2) if m else ""
    try:
        return __macro_item(s, m)
    finally:
        CUR["macro"] = prev


def __macro_item(s, m):
    if not m or m.group(1):
        return Raw(s, "macro")
    name, args = m.group(2), m.group(3)
    head = s[: m.start(3)]
    if not args.strip():
        return Raw(s, "macro")
    if name in LABEL_MACROS:
        ws = args[:len(args) - len(args.lstrip())]
        if args.lstrip().startswith("[["):
            r = scan_link(args, len(ws))
            if r:
                end, body, setter = r
                it = link_label(body, setter, head + ws, args[end:] + ">>")
                return it or Raw(s, "macro")
            return Raw(s, "macro")
        lv = re.match(r"^(\s*)([$_][A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*|\[[^\]]+\])*)(\s[\s\S]*|)$", args)
        if lv and name in ("link", "button", "linkreplace", "linkappend", "linkprepend", "click"):
            return LabelVar(head + lv.group(1), lv.group(2), lv.group(3), s)
        vm = re.match(r"(\s*)(" + VAR_PATH.pattern + r")(?=\s|$)([\s\S]*)$", args)
        if vm and STYLE["sc2"] and value_var_ok(Raw(vm.group(2), "var")):
            return VarArg(head + vm.group(1), vm.group(2), vm.group(3) + ">>", s)
        if name == "option" and len([t for t in tokenize(args)[0] if t.type not in ("ws", "comment")]) < 2:
            remember_keys(args)  # <<option "white">> — подпись и есть значение
            return Raw(s, "macro")
        return Seq([head, process_js(args, "data", mode="label"), ">>"])
    if name == "switch":
        CUR["switch"] = last_ident(args)
    if name in KEY_MACROS or not OPTS.js:
        # <<case "white">>, <<goto "X">> ... — это ключи, запомним их (и для <<case>> — что сравнивают)
        remember_keys(args, CUR.get("switch") if name == "case" else None)
        return Raw(s, "macro")
    if name in OUTPUT_MACROS and re.fullmatch(r"\s*[$_][A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*|\[[^\]]+\])*\s*", args):
        it = Raw(args.strip(), "var")
        if value_var_ok(it):
            return PrintValue(head, args, s)
    if name in JS_MACROS:
        ctx = "output" if name in OUTPUT_MACROS else "data"
        if name in OUTPUT_MACROS:
            return PrintWrap([head, process_js(args, ctx), ">>"])
        return Seq([head, process_js(args, ctx), ">>"])
    roles = MACRO_ROLES.get(name)
    if roles:  # макрос игры: какие аргументы — ключи (классы, имена), а какие видит игрок
        return Seq([head, process_js(args, "data", mode=("roles", roles)), ">>"])
    return Seq([head, process_js(args, "data", mode="args"), ">>"])


MACRO_ROLES = {}  # имя макроса → {номер аргумента: "key" | "label"} (из кода Macro.add в игре)


def scan_macro_roles(passages):
    """Смотрим в JavaScript игры, как макрос использует this.args[N]: в class="..."/id/src/ключ — не переводить,
    в видимый текст (между тегами, .text(), .wiki()) — переводить. Например:
        Macro.add('Dialogue', ... '<div class="speech ' + id + '">' ... '<span class="name">' + name ...)
    → у <<Dialogue "player" "You">> первый аргумент — ключ, второй — подпись."""
    code = "\n".join(p["body"] for p in passages if "script" in p["tags"])
    starts = [m for m in re.finditer(r"Macro\.add\(\s*(\[[^\]]*\]|(['\"])([\w-]+)\2)\s*,", code)]
    for k, m in enumerate(starts):
        names = re.findall(r"['\"]([\w-]+)['\"]", m.group(1))
        block = code[m.end():starts[k + 1].start() if k + 1 < len(starts) else m.end() + 4000][:4000]
        exprs = {}  # выражение → номер аргумента
        for am in re.finditer(r"this\.args\[(\d+)\]", block):
            exprs.setdefault(am.group(0), set()).add(int(am.group(1)))
        # var name = this.args[1] (но не passage = this.args[0].link — это уже свойство объекта-ссылки)
        for vm in re.finditer(r"\b([A-Za-z_$][\w$]*)\s*=\s*this\.args\[(\d+)\](?![\w$.\[])", block):
            exprs.setdefault(vm.group(1), set()).add(int(vm.group(2)))
        for vm in re.finditer(r"\b([A-Za-z_$][\w$]*)\s*=\s*([A-Za-z_$][\w$]*)\s*[,;\n]", block):  # name = id
            if vm.group(2) in exprs:
                exprs.setdefault(vm.group(1), set()).update(exprs[vm.group(2)])
        roles = {}
        for e, idxs in exprs.items():
            pat = (re.escape(e) if e.startswith("this.") else r"(?<![\w$.])" + re.escape(e)) + r"(?![\w$.\[])"
            kinds = set()
            for um in re.finditer(pat, block):
                before = block[max(0, um.start() - 200):um.start()]
                after = block[um.end():um.end() + 40]
                lit = re.search(r"(['\"])((?:\\.|(?!\1).)*)\1\s*\+\s*$", before)
                if lit:
                    frag = lit.group(2)
                    if re.search(r"""(?:class|id|src|href|style|data-[\w-]+|for|name)\s*=\s*["'][^"']*$""", frag):
                        kinds.add("key")
                    elif re.search(r">[^<]*$", frag):
                        kinds.add("label")
                elif re.search(r"(?:addClass|removeClass|toggleClass|attr|Engine\.play|Story\.get|Story\.has|"
                               r"variables|getVariable|setVariable)\s*\(\s*$|\[\s*$", before) or after.lstrip().startswith("]"):
                    kinds.add("key")
                else:  # $link.wikiWithOptions({...}, this.args[0]), createTextNode(x), .text(x) — видимый текст
                    cm = None
                    for cm in re.finditer(r"(?:\.wiki\w*|createTextNode|\.text|\.append|\.prepend|\.html|wikify)\s*\(", before):
                        pass
                    if cm and ";" not in before[cm.end():]:
                        tail = before[cm.end():]
                        if tail.count("(") - tail.count(")") >= 0 and tail.count("{") == tail.count("}"):
                            kinds.add("label")
            for i in idxs:
                if not kinds:
                    continue
                kind = "key" if "key" in kinds or len(idxs) > 1 and "key" in kinds else "label"
                if roles.get(i) == "key":
                    continue
                roles[i] = kind
        # одна переменная на два аргумента (name = id; если аргумент один — он и класс, и подпись): ключ важнее
        for e, idxs in exprs.items():
            if len(idxs) > 1:
                for i in sorted(idxs)[:-1]:
                    if roles.get(i) == "label":
                        roles[i] = "key"
        if roles:
            for nm in names:
                MACRO_ROLES[nm] = roles
    scan_widget_roles(passages)


WARG = r"[$_]args\[(\d+)\]"
WIDGET_KEY_RES = [re.compile(x) for x in (
    r"(?:\bis\b|\bisnot\b|\beq\b|\bneq\b|[!=]==?|\bgte?\b|\blte?\b)\s*" + WARG,
    WARG + r"\s*(?:\bis\b|\bisnot\b|\beq\b|\bneq\b|[!=]==?|\bgte?\b|\blte?\b)",
    r"\[\s*" + WARG + r"\s*\]",
    r"(?:includes|indexOf|hasOwnProperty|has|get|play|addClass|removeClass)\(\s*" + WARG,
    r"<<(?:goto|include|display|addclass|removeclass|toggleclass|case|switch)\s+" + WARG,
    r"\|\s*" + WARG + r"\s*\]\]",
    r"<<(?:link|button)\s+(?:\"[^\"]*\"|'[^']*'|\S+)\s+" + WARG,
)]
WIDGET_LABEL_RES = [re.compile(x) for x in (
    r"<<(?:print|=|-)\s+" + WARG + r"\s*>>",
    r"<<(?:link|button|linkreplace|linkappend|linkprepend)\s+" + WARG,
)]


def scan_widget_roles(passages):
    """<<widget "name">>: аргумент, который сравнивают ($args[0] is "gym") или используют как ключ, — не переводить;
    аргумент, который только показывают (<<print $args[0]>> или просто $args[0] в тексте), — переводить."""
    for p in passages:
        if "widget" not in p["tags"]:
            continue
        for m in re.finditer(r'<<widget\s+["\']([\w-]+)["\'][^>]*>>([\s\S]*?)<</widget>>', p["body"]):
            name, body = m.group(1), m.group(2)
            keys, labels = set(), set()
            for rx in WIDGET_KEY_RES:
                keys.update(int(x) for x in rx.findall(body))
            for rx in WIDGET_LABEL_RES:
                labels.update(int(x) for x in rx.findall(body))
            spans = [(mm.start(), mm.end()) for mm in re.finditer(r"<<[\s\S]*?>>", body)]
            for am in re.finditer(WARG, body):  # просто $args[0] в тексте — его видит игрок
                if not any(a <= am.start() < b for a, b in spans):
                    labels.add(int(am.group(1)))
            roles = {i: "key" for i in keys}
            for i in labels - keys:
                roles[i] = "label"
            if roles and name not in MACRO_ROLES:
                MACRO_ROLES[name] = roles


class PrintWrap:
    """<<print выражение>> → <<print ruT((выражение))>>: если результат — известное значение ("white"),
    на экране будет перевод; всё остальное печатается как было."""
    kind = "macro"

    def __init__(self, p):
        self.p = p

    def render(self):
        head, inner, tail = self.p[0], self.p[1].render(), self.p[2]
        if VALUES["on"] and inner.strip():
            return f"{head} ruT(({inner.strip()})){tail}"
        return head + inner + tail

    def parts(self):
        return expand_parts(self.render())


class LabelVar:
    """<<link $nextButton $nextLink>> → <<link `ruT($nextButton)` $nextLink>> (только показ)."""
    kind = "macro"

    def __init__(self, head, var, rest, raw):
        self.head, self.var, self.rest, self.raw, self.s = head, var, rest, raw, raw

    def render(self):
        if VALUES["on"] and STYLE["sc2"]:
            return f"{self.head}`ruT({self.var})`{self.rest}>>"
        return self.raw

    def parts(self):
        return [self.render()]


class VarArg:
    """<<link $nextButton $nextLink>> → <<link `ruT($nextButton)` $nextLink>> (только показ)."""
    kind = "macro"

    def __init__(self, head, var, rest, raw):
        self.head, self.var, self.rest, self.raw, self.s = head, var, rest, raw, raw

    def render(self):
        return f"{self.head}`ruT({self.var})`{self.rest}" if VALUES["on"] else self.raw

    def parts(self):
        return [self.render()]


class PrintValue:
    """<<print $x.y>> → <<print ruT($x.y)>> (показ переведённого значения, логика не меняется)."""
    kind = "macro"

    def __init__(self, head, args, raw):
        self.head, self.args, self.raw, self.s = head, args, raw, raw

    def render(self):
        return f"{self.head} ruT({self.args.strip()})>>" if VALUES["on"] else self.raw

    def parts(self):
        return [self.render()]


VALUE_PROPS = {}  # значение → {имя свойства: сколько раз}, напр. "sub" → {"fetish": 12}


def note_prop(value, prop):
    if not value or not prop:
        return
    prop = prop.lstrip("$_")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{2,}", prop):
        return
    d = VALUE_PROPS.setdefault(value, {})
    d[prop] = d.get(prop, 0) + 1


def last_ident(src):
    ids = re.findall(r"[A-Za-z_$][\w$]*", src or "")
    ids = [i for i in ids if i not in ("State", "variables", "temporary", "setup", "args", "_args")]
    return ids[-1] if ids else None


def remember_keys(src, prop=None):
    """Все строки из src — ключи: такие же строки в других местах тоже не переводим."""
    try:
        toks, _ = tokenize(src)
    except Exception:  # noqa: BLE001
        return
    for t in toks:
        if t.type == "str" and not t.broken:
            try:
                v = js_unescape(t.text[1:-1])
            except (ValueError, OverflowError):
                continue
            KEYS.add(v.strip().lower())
            VALUE_CANDS.add(v)
            count_gender(v)
            note_prop(v, prop)


def code_item(s):
    if not OPTS.js:
        return Raw(s, "code")
    m = re.match(r"^(<<script\b[^>]*>>|<script\b[^>]*>)([\s\S]*?)(<</script>>|</script>)$", s)
    if not m or (m.group(1).startswith("<script") and re.search(r"\bsrc\s*=", m.group(1))):
        return Raw(s, "code")
    prev, prev_js = CUR.get("macro"), CUR.get("pure_js")
    CUR["macro"], CUR["pure_js"] = "", True
    try:
        return Seq([m.group(1), process_js(m.group(2), "data"), m.group(3)], kind="code")
    finally:
        CUR["macro"], CUR["pure_js"] = prev, prev_js


def macro_end(s, start):
    """Конец макроса <<...>> как его видит SugarCube: '>>' внутри кавычек не закрывает макрос."""
    i, n = start + 2, len(s)
    while i < n:
        if s.startswith(">>", i):
            return i + 2
        c = s[i]
        if c in "\"'`":
            j = i + 1
            while j < n and s[j] != c:
                j += 2 if s[j] == "\\" else 1
            if j >= n:
                break  # незакрытая кавычка — считаем по-простому
            i = j + 1
            continue
        if s.startswith("[[", i):
            r = scan_link(s, i)
            if not r:
                break
            i = r[0]
            continue
        i += 1
    k = s.find(">>", start + 2)
    return k + 2 if k >= 0 else -1


def protect(s, newlines=False, values=False):
    def rep(m):
        kind = m.lastgroup
        g = m.group(0)
        if kind == "code" and not g.startswith("<style"):
            it = code_item(g)
            it.mname = "script"
            return reg(it)
        if kind == "var":
            IDENTS.update(re.findall(r"[A-Za-z][\w]*", g))
            it = Raw(g, kind)
            it.wrapv = values
            return reg(it)
        return reg(Raw(g, kind))

    out, pos = [], 0
    while True:
        m = PROTECT.search(s, pos)
        if not m:
            out.append(s[pos:])
            break
        out.append(s[pos:m.start()])
        if m.group("linkopen") is not None:
            r = scan_link(s, m.start())
            if r:
                end, body, setter = r
                it = link_label(body, setter)
                out.append(reg(it or Raw(s[m.start():end], "link")))
                pos = end
            else:  # непарные скобки — тоже код, переводчику не отдаём
                out.append(reg(Raw("[[", "brk")))
                pos = m.end()
            continue
        if m.group("macro") is not None:
            end = macro_end(s, m.start())
            if end < 0:
                out.append("<<")
                pos = m.start() + 2
                continue
            out.append(reg(macro_item(s[m.start():end])))
            pos = end
        else:
            out.append(rep(m))
            pos = m.end()
    out = "".join(out)
    if newlines and ("\n" in out or "\r" in out):
        out = re.sub(r"\r?\n", lambda m: reg(Raw(m.group(0), "nl")), out)
    return out


def split_ws(s):
    a = len(s) - len(s.lstrip())
    b = len(s.rstrip())
    if b < a:
        return s, "", ""
    return s[:a], s[a:b], s[b:]


EDGE_KEEP = {"var", "entity", "fmt", "expr"}


def split_line(line):
    """Строка разметки -> (край, суть, край). По краям уходят пробелы и код (кроме переменных)."""
    toks = [t for t in MARK_SPLIT.split(line) if t]

    def is_edge(t):
        m = MARK.fullmatch(t)
        if m:
            it = ITEMS[int(m.group(1))]
            if letter_macro(it):  # <<s>>he, ye<<s>> — буква слова, не край фразы
                return False
            return getattr(it, "kind", "") not in EDGE_KEEP
        return not t.strip()

    i, j = 0, len(toks)
    while i < j and is_edge(toks[i]):
        i += 1
    while j > i and is_edge(toks[j - 1]):
        j -= 1
    # пробелы внутри крайних кусков текста
    lead, core, trail = "".join(toks[:i]), "".join(toks[i:j]), "".join(toks[j:])
    a, c, b = split_ws(core)
    return lead + a, c, b + trail


def needs_translation(core):
    return bool(core) and bool(LATIN.search(MARK.sub("", core)))


SANITIZE = [("<<", "«"), (">>", "»"), ("[[", "["), ("]]", "]"), ("@@", "@"), ("''", "'"),
            ("//", "/"), ("__", "_"), ("/*", "/ *"), ("*/", "* /"), ("/%", "/ %"), ("%/", "% /"),
            ('"""', '"'), ("{{{", "{"), ("}}}", "}"), ("<!--", "<!"), ("⟦", ""), ("⟧", ""),
            (M_OPEN, ""), (M_CLOSE, ""), ("\r", " "), ("\n", " ")]


def sanitize(t):
    for a, b in SANITIZE:
        t = t.replace(a, b)
    t = re.sub(r"[$](?=[A-Za-z_])", "＄", t)
    t = re.sub(r"<(?=[A-Za-z/!])", "‹", t)
    return t


def fix_label(t, quote):
    t = t.replace("\\", "")
    if quote == '"':
        t = t.replace('"', "'")
    elif quote == "'":
        t = t.replace("'", "\u2019")
    else:
        t = (t.replace("|", "/").replace("[", "(").replace("]", ")")
              .replace("->", "\u2192").replace("<-", "\u2190"))
    return TStr(t)


# ===========================================================================
# Переводимый текст (с метками вместо кода и вариантами по роду)
# ===========================================================================

# Заикание: H-hello, I-I, w-what. Но не размеры и составные слова: C-cup, S-shaped, D-day, T-type ...
STUTTER_EN = re.compile(r"(?<![A-Za-z])([A-Za-z])-(?=\1)(?!(?:cups?|shaped?|day|days|type|types|size|sized|"
                        r"cell|cells|class|list|line|lines|zone|rank|ring|grade|rated|rating|section|series|"
                        r"spot|star|stars|bomb|bombs|team|test|track|word|words|bar|bars|box|car|cars)\b)", re.I)
STUTTER_TR = re.compile(r"(?<![^\W\d_])((?:[^\W\d_]-){1,4})([^\W\d_])")  # Н-привет


LOOKALIKE = {"А": "A", "В": "B", "С": "C", "Е": "E", "Н": "H", "К": "K", "М": "M", "О": "O", "Р": "P", "Т": "T",
             "Х": "X", "У": "Y"}


def plain_hyphens(src):
    """Буквы перед дефисом, которые в оригинале не заикание: «C» в «C-cup», «T» в «T-shaped»."""
    out = set()
    for m in re.finditer(r"(?<![A-Za-z])([A-Za-z])-([A-Za-z]+)", src or ""):
        if m.group(1).lower() != m.group(2)[0].lower() or not STUTTER_EN.search(m.group(0)):
            out.add(m.group(1).upper())
    return out


def fix_stutter(t, src=None):
    """Заикание: переводчик оставляет первую букву английского слова (H-hello → Н-привет).
    Делаем по первой букве переведённого слова: П-привет, Ч-что. «C-cup» и подобное не трогаем."""
    keep = plain_hyphens(src)

    def rep(m):
        first = m.group(2)
        l0 = m.group(1)[0].upper()
        if l0 in keep or LOOKALIKE.get(l0) in keep:
            return m.group(0)
        if not re.match(r"[А-Яа-яЁёІіЇїЄєЎў]", first):
            return m.group(0)
        parts = m.group(1).split("-")[:-1]
        return "".join((first.upper() if p.isupper() else first.lower()) + "-" for p in parts) + first
    return STUTTER_TR.sub(rep, t)


NO_COPULA_LANGS = {"ru", "uk", "be"}   # языки, где «is/are» в настоящем времени не переводится
COPULA_DROP = {"is", "are", "am", "was", "were", "the", "an"}
WORD_TOK = re.compile(r"⟦\s*\d+\s*⟧|[^\W\d_]+(?:['’][^\W\d_]+)?|\d+")


def no_copula_lang():
    return CONF.get("dst", "ru").split("-")[0].lower() in NO_COPULA_LANGS


def is_latin_word(w):
    return bool(w) and bool(re.fullmatch(r"[A-Za-z]+(?:['’][A-Za-z]+)?", w))


def clean_copula(t):
    """Переводчик оставил английское «is» («Сара is преданная»). Если слева и справа от него не
    английские слова — убираем (в русском связки нет). Английские фразы целиком не трогаем."""
    if not t or not no_copula_lang() or not re.search(r"(?<![^\W\d_])(?:is|are|am|was|were|the|an)(?![^\W\d_])", t):
        return t
    toks = list(WORD_TOK.finditer(t))
    cut = []
    for i, m in enumerate(toks):
        if m.group(0) not in COPULA_DROP:
            continue
        prev = toks[i - 1].group(0) if i else ""
        nxt = toks[i + 1].group(0) if i + 1 < len(toks) else ""
        if is_latin_word(prev) or is_latin_word(nxt):
            continue
        cut.append(m.span())
    for a, b in reversed(cut):
        t = t[:a] + t[b:]
    t = re.sub(r"[ \t]{2,}", " ", t)
    return re.sub(r"(?<=\S) +([,.;:!?…])", r"\1", t)


GVAR = re.compile(r"^([$_]?(?:[A-Za-z_$][\w$]*\.)*)([A-Za-z][A-Za-z_$]*?)(\d*)$")
VOID_TAGS = {"br", "img", "hr", "input", "wbr", "meta", "link", "source", "col", "area"}


def gender_info(item):
    if isinstance(item, Raw) and item.kind == "var":
        s = item.s
    elif isinstance(item, Expr):
        s = item.src
    else:
        return None
    m = GVAR.match(s)
    if not m or m.group(2) not in GENDER:
        return None
    return (m.group(1), m.group(3)), GENDER[m.group(2)]


CONF = {"context": False, "gdefault": None}
DUMMIES = {"f": ["Lyudmila", "Svetlana", "Agata"], "m": ["Bogdan", "Zakhar", "Rostislav"]}
DUMMY_STEMS = {"Lyudmila": ["Людмил", "Lyudmil", "Ludmil", "Ljudmil", "Людміл"],
               "Svetlana": ["Светлан", "Svetlan", "Swetlan"], "Agata": ["Агат", "Agat", "Agath"],
               "Bogdan": ["Богдан", "Bogdan"], "Zakhar": ["Захар", "Zakhar", "Zachar", "Sachar"],
               "Rostislav": ["Ростислав", "Rostislav", "Rostyslav", "Rostisław", "Ростислав"]}
SEP_L, SEP_R = 98, 99
SEP_RE = {k: re.compile(r"[⟦\[]\s*" + str(k) + r"\s*[⟧\]]") for k in (SEP_L, SEP_R)}
NAMEVAR_RE = re.compile(r"(?i)name$")


def is_name_var(item):
    if not isinstance(item, Raw) or item.kind != "var":
        return False
    last = re.split(r"[.\[\]]+", item.s.rstrip("]"))[-1].strip("\"'$_")
    return bool(NAMEVAR_RE.search(last))


def restore_dummies(res, dummies):
    """Подставное имя (Людмила/Людмилы/Людмиле...) обратно → метка переменной с именем."""
    for name, k in dummies:
        pat = re.compile(r"(?<![^\W\d_])(?:" + "|".join(map(re.escape, DUMMY_STEMS[name])) + r")[^\W\d_]*", re.I)
        if len(pat.findall(res)) != 1:  # имя пропало или появилось дважды — не рискуем
            return None
        res = pat.sub(PH_OUT.format(k), res)
    return res


def text_plain(t):
    """Английский текст фразы без кода — только как подсказка переводчику
    (имя → подставное имя, местоимение → слово, подписи ссылок → их текст, остальной код убираем)."""
    sex = CONF["gdefault"]

    def rep(m):
        it = ITEMS[int(m.group(1))]
        if is_name_var(it):
            return DUMMIES[sex][0] if sex else " "
        gi = gender_info(it)
        if gi:
            return gi[1][0 if sex == "m" else 1] if sex else " "
        lm = letter_macro(it)
        if lm:
            return lm
        if isinstance(it, Label) and not MARK.search(it.text.core):
            return " " + it.text.core + " "
        return " "
    return MARK.sub(rep, t.core)


def tidy_hint(s, tail, limit=70):
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+([,.;:!?…])", r"\1", s)
    s = re.sub(r"([:;,])[.,;:]+", r"\1", s).strip(" ")
    if not re.search(r"[A-Za-z]{2}", s):
        return ""
    if len(s) > limit:
        if tail:
            s = s[-limit:]
            s = s[s.find(" ") + 1:] if " " in s else s
        else:
            s = s[:limit]
            s = s[:s.rfind(" ")] if " " in s else s
    return s if re.search(r"[A-Za-z]{2}", s) else ""


def ctx_string(lst, tail):
    return tidy_hint(" ".join(text_plain(t) for t in lst), tail)


def ctx_extract(res, side):
    """Из перевода «подсказка ⟦98⟧ фраза» (или «фраза ⟦99⟧ подсказка») берём только фразу."""
    if res is None:
        return None
    k, other = (SEP_L, SEP_R) if side == "left" else (SEP_R, SEP_L)
    m = list(SEP_RE[k].finditer(res))
    if len(m) != 1 or SEP_RE[other].search(res):
        return None
    return (res[m[0].end():] if side == "left" else res[:m[0].start()]).strip()


DUMMY_ANY = re.compile(r"(?<![^\W\d_])(?:" + "|".join(re.escape(x) for v in DUMMY_STEMS.values() for x in v) + r")",
                       re.I)


def letters_count(s):
    return len(re.findall(r"[^\W\d_]", PH_IN.sub("", s or "")))


def ctx_valid(alt, plain, n_ids, src):
    """Перевод с подсказкой можно брать, только если он похож на правду (иначе — обычный перевод)."""
    if alt is None or plain is None:
        return False
    if SEP_RE[SEP_L].search(alt) or SEP_RE[SEP_R].search(alt):
        return False
    if sorted(int(x) for x in PH_IN.findall(alt)) != list(range(n_ids)):
        return False
    if "|" in alt and "|" not in src:
        return False
    if DUMMY_ANY.search(alt):  # в результат «утекло» подставное имя из подсказки
        return False
    la, lp = letters_count(alt), letters_count(plain)
    if la == 0 or lp == 0:
        return la == lp
    if la > 1.8 * lp + 6 or la < 0.35 * lp - 3:  # прихватил кусок подсказки или потерял слова
        return False
    if ":" in alt and ":" not in src and ":" not in plain:  # «форма груди: Нормальная» — утекла подсказка
        return False
    if CONF.get("dst", "ru").split("-")[0] in CYRILLIC_LANGS:
        eng_alt = set(re.findall(r"[A-Za-z]{3,}", PH_IN.sub(" ", alt)))
        if eng_alt - set(re.findall(r"[A-Za-z]{3,}", PH_IN.sub(" ", plain))):
            return False
    return True


PROP_WORD_MAP = {"h": "hair", "boob": "breast", "boobs": "breasts"}


def prop_words(prop):
    """boobShape → "breast shape", hColor → "hair color" (подсказка для коротких значений)."""
    if not prop:
        return None
    words = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", prop.lstrip("$_")).lower().split()
    words = [PROP_WORD_MAP.get(w, w) for w in words if not w.isdigit()]
    words = [w for w in words if len(w) > 1]
    joined = " ".join(words)
    if not words or joined in HINT_SKIP or len("".join(words)) < 3:
        return None
    return joined


CTX_REQS = set()  # запросы с подсказкой контекста (для подсчёта в --dry-run)


class LabelGroup:
    """Подписи ссылок одной строки («Normal | Perky | Saggy») — переводим вместе с началом строки,
    чтобы переводчик понял, о чём речь: «Естественная форма груди: Нормальная | Упругая | Обвисшая»."""

    def __init__(self, texts, hint):
        self.texts, self.hint = texts, hint

    def request(self):
        body = " | ".join(t.core for t in self.texts)
        return f"{self.hint} {PH_OUT.format(SEP_L)} {body}" if self.hint else body

    def part(self, tr, i):
        r = tr.peek(self.request())
        if r is None:
            return None
        if self.hint:
            r = ctx_extract(r, "left")
            if r is None:
                return None
        parts = [x.strip() for x in re.split(r"[|｜¦]", r)]
        return parts[i] if len(parts) == len(self.texts) else None


class Text:
    def __init__(self, core, markup=False):
        self.core, self.markup = core, markup
        self.active = True
        self.out = {}
        self.ctx_left_list, self.ctx_right_list = [], []
        self.prop_hint = self.label_hint = self.lgroup = None
        self.broken = False
        self.last_dummies = []
        self.group = self.cond = None
        self.ids = [int(x) for x in MARK.findall(core)]
        self.lisp = None
        if markup:
            pieces = MARK_SPLIT.split(core)
            for n, p in enumerate(pieces):
                m = MARK.fullmatch(p)
                if m and letter_macro(ITEMS[int(m.group(1))]) and (
                        (n and pieces[n - 1][-1:].isalpha())
                        or (n + 1 < len(pieces) and pieces[n + 1][:1].isalpha())):
                    self.lisp = letter_macro(ITEMS[int(m.group(1))])
                    break
        if OPTS.gender:
            self._gender()
        TEXTS.append(self)

    def _gender(self):
        groups, first = set(), None
        for i in self.ids:
            gi = gender_info(ITEMS[i])
            if gi:
                groups.add(gi[0])
                first = first or ITEMS[i]
        if len(groups) != 1:
            return
        if self.markup:  # обёртка <<if>> не должна разорвать макросы/теги
            kinds = [getattr(ITEMS[i], "kind", "?") for i in self.ids if not letter_macro(ITEMS[i])]
            macros = [ITEMS[i] for i in self.ids
                      if getattr(ITEMS[i], "kind", "") == "macro" and not letter_macro(ITEMS[i])]
            closers = {getattr(it, "mname", "") for it in macros if getattr(it, "s", "").startswith("<</")}
            bal = {}
            for it in macros:  # свои виджеты внутри фразы можно повторить в каждой ветке «она/он»
                name = getattr(it, "mname", "")
                if not name or name in BLOCK_MACROS or name.startswith("end"):
                    return
                if name in closers:
                    bal[name] = bal.get(name, 0) + (-1 if getattr(it, "s", "").startswith("<</") else 1)
            if any(bal.values()):
                return
            if any(k not in ("var", "entity", "url", "image", "label", "fmt", "tag", "macro", "valuevar")
                   for k in kinds):
                return
            fmts = [ITEMS[i].s for i in self.ids if getattr(ITEMS[i], "kind", "") == "fmt"]
            if any(fmts.count(f) % 2 for f in set(fmts)):
                return
            bal = {}
            for i in self.ids:
                if getattr(ITEMS[i], "kind", "") == "tag":
                    tm = re.match(r"<(/?)([A-Za-z][\w-]*)", ITEMS[i].s)
                    if tm and tm.group(2).lower() not in VOID_TAGS and not ITEMS[i].s.endswith("/>"):
                        k = tm.group(2).lower()
                        bal[k] = bal.get(k, 0) + (-1 if tm.group(1) else 1)
            if any(bal.values()):
                return
        self.group, self.cond = groups.pop(), first

    def variants(self):
        return ("n", "m", "f") if self.group else ("n",)

    def localize(self, v, dummies=True):
        key = (v, dummies, self.group)
        memo = self.__dict__.setdefault("_loc", {})
        if key not in memo:
            src, ids = self._localize(v, dummies)
            memo[key] = (src, tuple(ids), tuple(self.last_dummies))
        src, ids, dm = memo[key]
        self.last_dummies = list(dm)
        return src, list(ids)

    def _localize(self, v, dummies=True):
        out, ids, nd = [], [], 0
        self.last_dummies = []
        pieces = MARK_SPLIT.split(self.core)
        for n, p in enumerate(pieces):
            m = MARK.fullmatch(p)
            if not m:
                out.append(p)
                continue
            idx = int(m.group(1))
            letters = letter_macro(ITEMS[idx])
            if letters and ((n and pieces[n - 1][-1:].isalpha()) or (n + 1 < len(pieces) and pieces[n + 1][:1].isalpha())):
                out.append(letters)  # plea<<s>>e → please (шепелявость в переводе не сохранить)
                continue
            gi = gender_info(ITEMS[idx]) if v != "n" else None
            if gi and gi[0] == self.group:
                out.append(gi[1][0 if v == "m" else 1])
                continue
            ids.append(idx)
            sex = v if v in ("m", "f") else CONF["gdefault"]
            if dummies and sex and self.markup and is_name_var(ITEMS[idx]) and nd < 3:
                name = DUMMIES[sex][nd]  # «Sarah is devoted» → «Lyudmila is devoted»: переводчик видит род
                nd += 1
                self.last_dummies.append((name, len(ids) - 1))
                out.append(name)
                continue
            out.append(PH_OUT.format(len(ids) - 1))
        return "".join(out), ids

    def short(self):
        """Короткий обрывок (до 4 слов, не целое предложение) — ему нужна подсказка контекста."""
        if "_short" not in self.__dict__:
            self._short = self._is_short()
        return self._short

    def _is_short(self):
        plain = re.sub(r"\s+", " ", MARK.sub(" ", self.core)).strip()
        words = re.findall(r"[A-Za-z]+(?:['’-][A-Za-z]+)*", plain)
        if not words or len(words) > 4:
            return False
        return not (len(words) >= 3 and re.match(r"[A-Z\"“«].*[.!?…][\"”»]?$", plain))

    def copula_only(self):
        """«$name is» — в русском переводить нечего: связка просто пропадает («Сара предана»)."""
        if "_cop" not in self.__dict__:
            self._cop = self._is_copula_only()
        return self._cop

    def _is_copula_only(self):
        if not no_copula_lang():
            return False
        words = re.findall(r"[A-Za-z']+", MARK.sub(" ", self.core))
        return bool(words) and all(w.lower() in ("is", "are", "am") for w in words)

    def copula_parts(self):
        out = []
        for p in MARK_SPLIT.split(self.core):
            m = MARK.fullmatch(p)
            if m:
                it = ITEMS[int(m.group(1))]
                if self.markup and value_var_ok(it):
                    out.append(ValueVar(it))
                else:
                    out.extend(it.parts())
            elif p:
                t = re.sub(r"[ \t]*(?<![A-Za-z'’])(?:is|are|am)(?![A-Za-z'’])", "", p, flags=re.I)
                t = re.sub(r" {2,}", " ", t)
                if t:
                    out.append(TStr(t))
        return flatten(out)

    def hint(self):
        """Подсказка для короткой фразы: ("left"|"right", английский текст рядом) или None."""
        if "_hint" not in self.__dict__:
            self._hint = self._make_hint()
        return self._hint

    def _make_hint(self):
        if not CONF["context"] or not self.short():
            return None
        if self.prop_hint:
            w = prop_words(self.prop_hint)
            return ("left", w + ":") if w else None
        if self.label_hint:
            return ("left", self.label_hint)
        if self.markup:
            left = ctx_string(self.ctx_left_list, True)
            if left:
                return ("left", left)
            right = ctx_string(self.ctx_right_list, False)
            if right:
                return ("right", right)
        return None

    def ctx_request(self, v):
        """(запрос с подсказкой, сторона, подставные имена) или None."""
        h = self.hint()
        if h is None:
            return None
        src, _ = self.localize(v)
        side, text = h
        req = (f"{text} {PH_OUT.format(SEP_L)} {src}" if side == "left"
               else f"{src} {PH_OUT.format(SEP_R)} {text}")
        CTX_REQS.add(req)
        return req, side, list(self.last_dummies)

    def requests(self):
        if not self.active or not needs_translation(self.core) or self.copula_only():
            return []
        out = []
        for v in self.variants():
            out.append(self.localize(v)[0])
            c = self.ctx_request(v)
            if c:
                out.append(c[0])
        if self.lgroup and CONF["context"]:
            g = self.lgroup[0].request()
            CTX_REQS.add(g)
            out.append(g)
        return out

    def _plain(self, tr, v, missing):
        """Обычный перевод варианта v: (запрос, перевод, ids) или None (ещё не переведено)."""
        src, ids = self.localize(v)
        dummies = list(self.last_dummies)
        res = tr.peek(src)
        if res is None:
            missing.append(src)
            return None
        if dummies:
            r2 = restore_dummies(res, dummies)
            if r2 is not None:
                return src, r2, ids
            src, ids = self.localize(v, dummies=False)  # имя-подсказка потерялось — без неё
            res = tr.peek(src)
            if res is None:
                missing.append(src)
                return None
        return src, res, ids

    def _alt(self, tr, v, plain, ids, src):
        """Перевод с подсказкой контекста, если он прошёл проверку."""
        cands = []
        if self.lgroup and CONF["context"]:
            cands.append(self.lgroup[0].part(tr, self.lgroup[1]))
        c = self.ctx_request(v)
        if c:
            req, side, dummies = c
            x = ctx_extract(tr.peek(req), side)
            if x is not None and dummies:
                x = restore_dummies(x, dummies)
            cands.append(x)
        for x in cands:
            if x is not None and ctx_valid(x, plain, len(ids), src):
                return x
        return None

    def _assemble(self, src, res, ids):
        if sorted(int(x) for x in PH_IN.findall(res)) != list(range(len(ids))):
            return None
        if STUTTER_EN.search(src):
            res = fix_stutter(res, src)
        res = clean_copula(res)
        out = []
        for k, p in enumerate(PH_IN.split(res)):
            if k % 2:
                it = ITEMS[ids[int(p)]]
                if self.markup and value_var_ok(it):
                    out.append(ValueVar(it))
                else:
                    out.extend(it.parts())
            elif p:
                out.append(TStr(sanitize(p)))
        return flatten(out)

    def _drop_gender(self):
        self.group = None
        self.out.pop("m", None)
        self.out.pop("f", None)

    def apply(self, tr):
        """Собирает перевод из кэша. Возвращает запросы, которых не хватило (их переведут и вызовут снова)."""
        if not self.active or not needs_translation(self.core):
            return []
        if self.copula_only():
            self.out = {"n": self.copula_parts()}
            self.group = None
            return []
        missing = []
        for v in self.variants():
            got = self._plain(tr, v, missing)
            if got is None:
                if v == "n":
                    self.out.pop("n", None)
                else:
                    self._drop_gender()
                continue
            src, res, ids = got
            alt = self._alt(tr, v, res, ids, src)
            parts = self._assemble(src, alt if alt is not None else res, ids)
            if parts is None and alt is not None:
                parts = self._assemble(src, res, ids)
            if parts is None:  # переводчик испортил метки кода
                if v == "n":
                    self.out.pop("n", None)
                    self.broken = True
                    missing.extend(x for x in self.pieces() if not tr.has(x))
                else:
                    self._drop_gender()
                continue
            self.out[v] = parts
        return missing

    def pieces(self):
        return [p.strip() for p in MARK_SPLIT.split(self.core)
                if not MARK.fullmatch(p) and LATIN.search(p)]

    def apply_fallback(self, tr):
        """Метки испорчены — переводим куски текста между кодом по отдельности."""
        if not self.active or not self.broken or self.out.get("n") is not None:
            return
        out = []
        for p in MARK_SPLIT.split(self.core):
            m = MARK.fullmatch(p)
            if m:
                out.extend(ITEMS[int(m.group(1))].parts())
            elif LATIN.search(p):
                a, c, b = split_ws(p)
                t = tr.peek(c)
                out += [a, TStr(sanitize(clean_copula(t))) if t is not None else c, b]
            elif p:
                out.append(p)
        self.out["n"] = flatten(out)
        self.group = None

    def parts(self, v="n"):
        res = self.out.get(v)
        if res is None:
            return expand_parts(self.core)
        return res

    def gendered(self):
        return bool(self.group) and "m" in self.out and "f" in self.out

    def render_markup(self):
        end = "<<endif>>" if STYLE["endif"] else "<</if>>"

        def j(v, lisp=False):
            parts = self.parts(v)
            if lisp:
                parts = lisp_parts(parts)
            return "".join(p if isinstance(p, str) else (p.render() if isinstance(p, ValueVar) else p.marker)
                           for p in parts)

        def g(lisp=False):
            if self.gendered() and not STYLE.get("neutral"):
                c = expand(self.cond.s)
                return (f"<<if ruGender({c}) is 1>>{j('f', lisp)}<<elseif ruGender({c}) is 0>>{j('m', lisp)}"
                        f"<<else>>{j('n', lisp)}{end}")
            return j("n", lisp)
        if self.lisp and self.out.get("n") and LISP["on"] and not STYLE.get("neutral"):
            # шепелявость: виджет игры (<<s>> и т.п.) во время игры подскажет, шепелявит ли персонаж
            return f'<<if ruIsLisp("{self.lisp}")>>{g(True)}<<else>>{g()}{end}'
        return g()


class ValueVar:
    """Переменная в переведённой строке: значение-ключ ("white") показывается переведённым,
    а в самой игре остаётся как было — логика не меняется."""
    kind = "valuevar"

    def __init__(self, item):
        self.item = item

    def render(self):
        return naked_print(self.item.s) if VALUES["on"] else self.item.s

    def parts(self):
        return [self.render()]


VALUES = {"on": False, "map": {}}


def naked_print(var):
    """$a.b в тексте → <<print ruV("$a.b")>>: значение показывается переведённым, а если переменной нет
    (не задана, пустой объект) — как и в самой игре, без ошибки: SugarCube тогда печатает «$a.b» как есть."""
    return "<<print ruV(" + json.dumps(var, ensure_ascii=False) + ")>>"
PRONOUNS_RU = {
    "he": "он", "she": "она", "him": "его", "her": "её", "his": "его", "hers": "её", "himself": "себя",
    "herself": "себя", "boy": "парень", "girl": "девушка", "boys": "парни", "girls": "девушки",
    "man": "мужчина", "woman": "женщина", "men": "мужчины", "women": "женщины", "husband": "муж",
    "wife": "жена", "son": "сын", "daughter": "дочь", "brother": "брат", "sister": "сестра",
    "father": "отец", "mother": "мать", "lord": "лорд", "lady": "леди", "king": "король", "queen": "королева",
    "it": "оно", "they": "они", "them": "их", "their": "их", "theirs": "их", "themselves": "себя",
}
VALUE_CANDS = set()
GENDER_LIT = {"f": 0, "m": 0}
FEM_WORDS = set("she her hers herself girl girls woman women wife daughter sister mother lady queen".split())
MASC_WORDS = set("he him his himself boy boys man men husband son brother father lord king".split())


def count_gender(v):
    w = v.strip().lower()
    if w in FEM_WORDS:
        GENDER_LIT["f"] += 1
    elif w in MASC_WORDS:
        GENDER_LIT["m"] += 1
STYLE = {"endif": False, "sc2": True}  # <<endif>> вместо <</if>> (старые игры Twine 1); SugarCube 2?


def expr_value_ok(ex):
    """${slave.hColor} в переведённом шаблоне можно показывать через ruT()."""
    if not isinstance(ex, Expr):
        return False
    if gender_info(ex):
        return True
    if not (re.fullmatch(r"[$_A-Za-z][\w$]*(?:\.[A-Za-z_$][\w$]*)+", ex.src) or VAR_PATH.fullmatch(ex.src)):
        return False
    last = re.split(r"[.\[\]]+", ex.src.rstrip("]"))[-1].strip("\"'$_")
    return bool(last) and not VALUE_NAME_RE.search(last)


LISP = {"on": True, "lang": "ru"}
QUOTE_OPEN, QUOTE_CLOSE = "\"«“„", "\"»”“"
LISP_JA = dict(zip("さすせそざずぜぞサスセソザズゼゾ", "しゃ しゅ しぇ しょ じゃ じゅ じぇ じょ シャ シュ シェ ショ ジャ ジュ ジェ ジョ".split()))
LISP_NONE = set("zh ko th lo km my ka hy am ti si ta te kn ml gu pa bn or as dv".split())


def lisp_text(t, lang=None):
    """Шепелявость на языке перевода — так же, как в переводе на лету (там, где у языка есть такие буквы)."""
    lang = (lang or LISP["lang"] or "ru").split("-")[0].lower()
    if lang in CYRILLIC_LANGS or lang == "tt":
        return re.sub("[СЦ]", "Ш", re.sub("З", "Ж", re.sub("[сц]", "ш", re.sub("з", "ж", t))))
    if lang == "en":
        t = re.sub("SS|SH", "TH", t)
        t = re.sub("Ss|Sh", "Th", t)
        t = re.sub("ss|sh", "th", t)
        t = re.sub("[SZ]", "Th", t)
        t = re.sub("[sz]", "th", t)
        return re.sub("c(?=[eiy])", "th", re.sub("C(?=[eiy])", "Th", t))
    if lang == "es":  # ceceo: «zí, zeñor»
        return t.replace("s", "z").replace("S", "Z")
    if lang == "el":
        return re.sub("[ΣΖ]", "Θ", re.sub("[σςζ]", "θ", t))
    if lang in ("ar", "fa", "ur", "ps", "sd", "ug", "ckb"):
        return re.sub("ز", "ذ", re.sub("[سص]", "ث", t))
    if lang in ("iw", "he", "yi"):
        return re.sub("ז", "ד", re.sub("[סש]", "ת", t))
    if lang in ("hi", "mr", "ne", "sa", "mai", "bho", "doi", "gom"):
        return re.sub("[सशष]", "थ", t)
    if lang == "ja":
        return re.sub("[さすせそざずぜぞサスセソザズゼゾ]", lambda m: LISP_JA[m.group(0)], t)
    if lang in LISP_NONE:
        return t
    # прочие языки на латинице: s, z → th (звук шепелявости), «sch» и «sz» — как одна буква
    t = t.replace("sch", "\x01").replace("Sch", "\x02")
    t = re.sub("S[sSzZ]", "Th", t)
    t = re.sub("ss|ß|sz|s|z", "th", t)
    t = re.sub("S|Z", "Th", t)
    return t.replace("\x01", "sch").replace("\x02", "Sch")


def lisp_parts(parts):
    """Шепелявим только прямую речь (текст в кавычках); если кавычек нет — всю фразу."""
    text_only = "".join(p for p in parts if isinstance(p, TStr))
    has_quotes = any(c in text_only for c in "\"«“„")
    out, inside = [], False
    for p in parts:
        if not isinstance(p, TStr):
            out.append(p)
            continue
        if not has_quotes:
            out.append(TStr(lisp_text(p)))
            continue
        buf, seg = [], ""
        for ch in p:
            if (not inside and ch in QUOTE_OPEN) or (inside and ch in QUOTE_CLOSE):
                buf.append(lisp_text(seg) if inside else seg)
                buf.append(ch)
                seg, inside = "", not inside
            else:
                seg += ch
        buf.append(lisp_text(seg) if inside else seg)
        out.append(TStr("".join(buf)))
    return out


ASSIGN_RE = re.compile(r"([$_A-Za-z][\w$]*(?:\.[A-Za-z_$][\w$]*|\[[^\]\n]{0,40}\])*)\s*(?:=(?![=>])|\bto\b|:)\s*"
                       r"([\"'])((?:\\.|(?!\2)[^\\\n]){2,60})\2")
LISP_SCAN = {"widgets": set(), "pairs": {}}


def en_lisp(w):
    """Английская шепелявость, как в играх: s/ss/z → th (Master → Mathter, Mistress → Mithtreth)."""
    a = re.sub(r"ss|s|z", "th", w)
    a = re.sub(r"S|Z", "Th", a)
    return {a, re.sub(r"c(?=[eiy])", "th", a)}


def scan_lisp(passages):
    """Виджеты-буквы шепелявости (<<s>>, <<ss>>, <<c>>, <<z>>) и пары слов «шепелявое → обычное»,
    которые игра присваивает одной и той же переменной: $titleEnunciate = "Mathter" / "Master"."""
    widgets, props = set(), {}
    for p in passages:
        if "stylesheet" in p["tags"]:
            continue
        body = p["body"]
        widgets.update(re.findall(r"<<widget\s+[\"']([A-Za-z]{1,2})[\"']", body))
        for m in ASSIGN_RE.finditer(body):
            prop = re.split(r"[.\[\]$]+", m.group(1).strip("]"))
            prop = [x for x in prop if x and not x.startswith(("'", '"'))]
            if prop:
                props.setdefault(prop[-1], set()).add(m.group(3))
    pairs = {}
    for vals in props.values():
        if len(vals) < 2:
            continue
        for w in vals:
            for v in en_lisp(w):
                if v != w and v in vals and len(v) >= 4:
                    pairs.setdefault(v, w)
    LISP_SCAN["widgets"], LISP_SCAN["pairs"] = widgets, pairs
    return widgets, pairs


def letter_macro(item):
    """Виджет-буква вроде <<s>>, <<ss>>, <<c>>, <<z>> (шепелявость в Free Cities): его буквы."""
    if getattr(item, "kind", "") != "macro" or not isinstance(item, Raw):
        return None
    m = re.fullmatch(r"<<([A-Za-z]{1,2})>>", item.s)
    return m.group(1) if m else None


VALUE_NAME_RE = re.compile(r"(?i)^(?:slave|birth|first|last|full|real|nick|sur|pc|my|player)?name\d*$|"
                           r"nickname\d*$|surname\d*$")


def value_var_ok(item):
    """Переменную можно показывать через ruT(): не род, не имя/титул."""
    if not isinstance(item, Raw) or item.kind != "var":
        return False
    if gender_info(item):
        return True  # $pronoun в запасной ветке: "she" покажется как «она»
    last = re.split(r"[.\[\]]+", item.s.rstrip("]"))[-1].strip("\"'$_")
    return bool(last) and not VALUE_NAME_RE.search(last)


class MarkupLine:
    def __init__(self, text):
        self.text = text

    def render(self):
        return self.text.render_markup()


# ===========================================================================
# JavaScript: токенизатор
# ===========================================================================

class Tok:
    __slots__ = ("type", "s", "e", "text", "tparts", "broken")

    def __init__(self, type_, s, e, text, tparts=None, broken=False):
        self.type, self.s, self.e, self.text = type_, s, e, text
        self.tparts, self.broken = tparts, broken


TOKEN_RE = re.compile(
    r"(?P<ws>\s+)"
    r"|(?P<comment>//[^\n]*|/\*[\s\S]*?(?:\*/|\Z)|<!--[^\n]*)"
    r"|(?P<ident>[A-Za-z_$\u0080-\uffff][\w$\u0080-\uffff]*)"
    r"|(?P<num>\d[\w.]*|\.\d\w*)"
    r"|(?P<punct>>>>=|\.\.\.|===|!==|\*\*=|<<=|>>=|>>>|&&=|\|\|=|\?\?=|=>|==|!=|<=|>=|&&|\|\||"
    r"\?\?|\?\.(?!\d)|\+\+|--|\+=|-=|\*=|/=|%=|&=|\|=|\^=|\*\*|<<|>>|[{}()\[\];,<>+\-*/%&|^!~?:=.@#\\])"
)
DQ = re.compile(r'"(?:[^"\\\n]|\\[\s\S])*"?')
SQ = re.compile(r"'(?:[^'\\\n]|\\[\s\S])*'?")
TPL_SPECIAL = re.compile(r"[\\`]|\$\{")
REGEX_KW = set(("return typeof instanceof in of new delete void throw case do else yield await "
                "to is isnot eq neq gt gte lt lte and or not").split())


def regex_ok(prev):
    if prev is None:
        return True
    if prev.type == "punct":
        return prev.text not in (")", "]")
    if prev.type == "ident":
        return prev.text in REGEX_KW
    return False


def scan_regex(src, pos):
    i, in_class, n = pos + 1, False, len(src)
    while i < n:
        c = src[i]
        if c == "\\":
            i += 2
            continue
        if c == "\n":
            return None
        if in_class:
            if c == "]":
                in_class = False
        elif c == "[":
            in_class = True
        elif c == "/":
            m = re.compile(r"[A-Za-z]*").match(src, i + 1)
            return m.end()
        i += 1
    return None


def scan_template(src, pos):
    i, seg, parts, n = pos + 1, pos + 1, [], len(src)
    while True:
        m = TPL_SPECIAL.search(src, i)
        if not m:
            parts.append(("text", src[seg:]))
            return parts, n, True
        i, g = m.start(), m.group()
        if g == "\\":
            i += 2
            continue
        if g == "`":
            parts.append(("text", src[seg:i]))
            return parts, i + 1, False
        parts.append(("text", src[seg:i]))
        sub, j = tokenize(src, i + 2, stop_brace=True)
        parts.append(("expr", sub, i + 2, j))
        if j >= n:
            return parts, n, True
        i = seg = j + 1


def tokenize(src, pos=0, stop_brace=False):
    toks, depth, n, prev = [], 0, len(src), None
    while pos < n:
        c = src[pos]
        if c == '"' or c == "'":
            m = (DQ if c == '"' else SQ).match(src, pos)
            e = m.end()
            t = Tok("str", pos, e, src[pos:e], broken=(e - pos < 2 or src[e - 1] != c))
        elif c == "`":
            parts, e, broken = scan_template(src, pos)
            t = Tok("tmpl", pos, e, src[pos:e], parts, broken)
        elif c == "/" and src[pos:pos + 2] not in ("//", "/*") and regex_ok(prev):
            e = scan_regex(src, pos)
            t = Tok("regex", pos, e, src[pos:e]) if e else Tok("punct", pos, pos + 1, "/")
        else:
            m = TOKEN_RE.match(src, pos)
            if m:
                t = Tok(m.lastgroup, pos, m.end(), m.group())
            else:
                t = Tok("punct", pos, pos + 1, c)
            if stop_brace and t.type == "punct":
                if t.text == "{":
                    depth += 1
                elif t.text == "}":
                    if depth == 0:
                        return toks, pos
                    depth -= 1
        toks.append(t)
        pos = t.e
        if t.type not in ("ws", "comment"):
            prev = t
    return toks, n


ESC = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v"}


def js_unescape(s):
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        nx = s[i + 1:i + 2]
        if nx in ESC:
            out.append(ESC[nx])
            i += 2
        elif nx == "0" and not s[i + 2:i + 3].isdigit():
            out.append("\0")
            i += 2
        elif nx == "x":
            h = s[i + 2:i + 4]
            if not re.fullmatch(r"[0-9a-fA-F]{2}", h):
                raise ValueError
            out.append(chr(int(h, 16)))
            i += 4
        elif nx == "u":
            if s[i + 2:i + 3] == "{":
                j = s.index("}", i)
                out.append(chr(int(s[i + 3:j], 16)))
                i = j + 1
            else:
                h = s[i + 2:i + 6]
                if not re.fullmatch(r"[0-9a-fA-F]{4}", h):
                    raise ValueError
                out.append(chr(int(h, 16)))
                i += 6
        elif nx == "\r":
            i += 3 if s[i + 2:i + 3] == "\n" else 2
        elif nx in ("\n", "\u2028", "\u2029"):
            i += 2
        elif nx == "" or nx.isdigit():
            raise ValueError
        else:
            out.append(nx)
            i += 2
    return "".join(out)


def js_escape(s, q):
    s = s.replace("\\", "\\\\")
    if q == "`":
        return s.replace("`", "\\`").replace("${", "\\${")
    return (s.replace(q, "\\" + q).replace("\n", "\\n").replace("\r", "\\r")
             .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


# ===========================================================================
# JavaScript: решение, что переводить
# ===========================================================================

CODEY = re.compile(r"=>|\bfunction\b|[;{}]\s*$|^\s*[\[{][\s\S]*[\]}]\s*$|\(\)|&&|\|\||===|!==|"
                   r"^[#.][\w-]+(?:[\s>+~,]+[#.]?[\w-]+)*$|^\w+\(|\b(?:State|setup)\.[A-Za-z_$]")
FILEY = re.compile(r"\.(png|jpe?g|gif|webp|svg|bmp|ico|mp3|ogg|wav|m4a|flac|webm|mp4|css|js|json|"
                   r"html?|ttf|otf|woff2?)(\?|#|$)", re.I)


GENDER_WORDS = set(("he she him her his hers himself herself boy girl boys girls man woman men women "
                    "husband wife son daughter brother sister father mother lord lady king queen").split())
HTML_TAGS = set(("div span a p br img input button ul ol li table tr td th thead tbody label select option "
                 "textarea h1 h2 h3 h4 h5 h6 strong em b i u s section article header footer nav form canvas "
                 "svg video audio source iframe hr pre code small sup sub mark details summary main aside "
                 "figure figcaption fieldset legend dl dt dd blockquote abbr kbd").split())
CSS_UNITS = set("px em rem vh vw vmin vmax pt pc cm mm in ex ch ms s deg rad turn fr dpi".split())


def looks_code(s):
    if CODEY.search(s) or FILEY.search(s) or DATEY.fullmatch(s):
        return True
    words = s.split()
    if words and all(w in CSS for w in words):
        return True
    if len(words) == 1:
        w = words[0]
        if w.lower() in CSS_UNITS:
            return True
        if "/" in w or "_" in w or "$" in w or "=" in w or re.search(r"[a-z][A-Z]", w) or ":" in w:
            return True
        if re.fullmatch(r"[\w]+(?:-[\w]+)+", w) and not re.fullmatch(r"[^\W\d_]+(?:-[^\W\d_]+)+", w):
            return True  # slave-12, x-2 — код; sky-blue, Min-Jun — слова
    return False


def is_prose(v):
    """Несколько слов (для строк, которые точно выводятся игроку)."""
    s = v.strip()
    if re.search(r"[A-Za-z]\S*\s+\S", s):
        return True
    if s != v and LATIN.search(s):
        return True
    return bool(re.fullmatch(r"[A-Z][\s\S]*[.!?…]", s))


def is_sentence(v):
    """Похоже на фразу, а не на название/ключ: знак препинания в конце, 4+ слова или пробел по краю."""
    s = v.strip()
    if s != v and LATIN.search(s):
        return True
    if len(re.findall(r"[A-Za-z]+", s)) >= 4:
        return True
    tail = re.sub(r"[\s/'_@=~^\"”»)\]>*]+$", "", s)
    return bool(re.search(r"[A-Za-z][^A-Za-z]*[.!?…:]$", tail)) and bool(re.search(r"\s", s))


def textual(v):
    """Литеральная часть шаблона похожа на текст: 2+ слова или слово + знак препинания."""
    words = re.findall(r"[A-Za-z]{2,}", v)
    if len(words) >= 2:
        return True
    return len(words) == 1 and bool(re.search(r"\s", v)) and bool(re.search(r"[.!?…:]\s*$", v))


_LONGKEYS = {"n": -1, "j": ""}


def key_part(v):
    """Длинная фраза — кусок строки-ключа. Игра склеивает "You got her at the Slave Shelter. " + случайная фраза
    из списка и потом сравнивает целиком: <<case "You got her at the Slave Shelter. She has never…">>.
    Переведённый кусок уже не совпадёт — поэтому такие куски не переводим (на экране их покажет ruT)."""
    low = v.strip().lower()
    if len(low) < 16 or low.count(" ") < 2 or "\n" in low:
        return False
    if _LONGKEYS["n"] != len(KEYS):
        _LONGKEYS["n"] = len(KEYS)
        _LONGKEYS["j"] = "\n".join(k for k in KEYS if len(k) > 20)
    return low in _LONGKEYS["j"]


def is_key(v):
    s = v.strip()
    return s.lower() in KEYS or s in PASSAGES or s in KEEP or v in KEEP or key_part(s)


AGG_RE = re.compile(r"[\"'‘“«]?[^\W\d_](?:[^\W\d_]|[ '’.,!?;:&-])*[\"'’”»]?")  # слова на любом алфавите
MUST = set()  # строки, которые пользователь велел переводить (--translate-list)
ABBR = re.compile(r"[A-Za-z][A-Za-z]{1,12}(?::[A-Za-z][A-Za-z-]*[+-]{0,4}|[+-]{1,4})")  # SP:vanilla, Ho:F+, Face++
DATEY = re.compile(r"\s*(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}"
                   r"|\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2})?|\d{1,2}[/.]\d{1,2}[/.]\d{2,4})(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?"
                   r"(?:\s*(?:GMT|UTC|Z|[+-]\d{2}:?\d{2}))?\s*", re.I)  # 'June 1, 2020 13:37:00' — для new Date()
NAMEISH = re.compile(r"[A-Z][^\W\d_]*(?:-[^\W\d_]+)+|(?:Mc|Mac|O'|D')[A-Z][a-z]+|[a-z]+(?:-[a-z]+)+")


def strip_macros(s):
    """Текст без макросов <<...>> (с учётом кавычек: <<if $a >= 1 || $b>> целиком)."""
    if "<<" not in s:
        return s
    out, i = [], 0
    while True:
        k = s.find("<<", i)
        if k < 0:
            out.append(s[i:])
            break
        e = macro_end(s, k)
        if e < 0:
            out.append(s[i:])
            break
        out += [s[i:k], " "]
        i = e
    return "".join(out)


def strip_markup(s):
    """Текст без разметки SugarCube: <<макросы>>, [[ссылки]] (остаётся подпись), @@.red;Text@@, ''жирный'',
    &nbsp;, теги."""
    s = re.sub(r"<<script\b[\s\S]*?<</script>>|<script\b[\s\S]*?</script>", " ", s, flags=re.I)
    s = strip_macros(s)
    s = re.sub(r"\[\[([^\]|]*?)(?:(?:\||->)[^\]]*)?\]\](?:\[[^\]]*\])?", r"\1", s)
    t = re.sub(r"@@(?:[^;@\n<>]{0,80};)*|''|//|__|<[^<>]+>|&(?:#\d+|[A-Za-z]+);", " ", s)
    return re.sub(r"\s+", " ", t).strip()
LAST = {"reason": ""}


def str_ok(v, ctx, check_keys=True, append=False, wrole=False):
    ok, reason = str_decide(v, ctx, check_keys, append, wrole)
    LAST["reason"] = reason
    return ok


APPEND_WORD = re.compile(r"[A-Z][a-z]+[.!?,;:]*")  # «Caucasian.», «Muscular» — слово, которое дописывают к тексту


def str_decide(v, ctx, check_keys=True, append=False, wrole=False):
    """(переводить?, причина отказа). append — строку дописывают к другой (summary += "Trim"): это кусок текста.
    wrole — подпись-аргумент макроса/виджета игры (<<FSChange "Paternalist" 2>>): если эту же строку игра где-то
    сравнивает (<<case "Paternalist">>), это ключ — не переводим."""
    s = v.strip()
    if not LATIN.search(v):
        return False, "нет букв"
    if s in KEEP or v in KEEP:
        return False, "в списке --keep"
    if ctx == "key":
        return False, "ключ: сравнение / селектор / имя"
    if ctx == "label":
        if wrole and check_keys and is_key(v):
            return False, "аргумент виджета: эту строку игра где-то сравнивает — ключ"
        return True, ""
    if check_keys and is_key(v):
        if s in PASSAGES:
            return False, "имя пассажа"
        if s.lower() in KEYS or s in KEEP or v in KEEP:
            return False, "ключ: где-то в игре с этой строкой сравнивают"
        return False, "кусок строки, с которой игра сравнивает (её склеивают из частей)"
    if s in MUST or v in MUST:
        return True, ""
    plain = strip_markup(s)
    if looks_code(s) and looks_code(plain or s) and not (OPTS.aggressive and (
            NAMEISH.fullmatch(plain or s) or ABBR.fullmatch(plain or s))):
        return False, "похоже на код / CSS / файл"  # в full имена через дефис (Kyung-Hee), McKenna — переводим
    single = not re.search(r"\s", s)
    if single and s in IDENTS and s == v:  # " and " с пробелами — кусок фразы, это текст
        return False, "совпадает с именем переменной/свойства"
    if single and s == v and (s.lower() in GENDER_WORDS or s in HTML_TAGS):
        return False, "местоимение или HTML-тег"
    if single and ctx != "output" and re.fullmatch(r"[A-Z0-9_-]{1,6}", s):
        return False, "похоже на код (XY, NPC...)"
    if ctx == "output":
        ok = is_prose(v) or s[:1].isupper() or s[-1:] in ".!?…:" or OPTS.aggressive
        return ok, "" if ok else "одно слово с маленькой буквы"
    if is_sentence(v):
        return True, ""
    if OPTS.aggressive and single and getattr(OPTS, "values", True) and ctx == "data" and s == v \
            and not (append and APPEND_WORD.fullmatch(plain or s)):
        # <<set $hairColor to "black">>: само значение не трогаем (по нему строятся картинки, сравнения),
        # а на экране его покажет перевод через ruT — так и переведено, и логика цела.
        # Но <<set $s.summary += "Muscular">> — это кусок текста описания: его переводим
        return False, "одно слово-данные: на экране переводится через ruT, значение не меняем"
    if OPTS.aggressive:
        plain = re.sub(r"@@[^;@\n]*;|@@|<[^<>]+>|''|//", "", s).strip()  # без разметки: @@.red;Text@@
        ok = bool(AGG_RE.fullmatch(plain)) or is_prose(v)
        return ok, "" if ok else "строка-данные необычного вида"
    return False, "короткая строка-данные (переводится только в full)"


BOUNDARY_TAGS = set("br p div hr li ul ol tr td th table thead tbody h1 h2 h3 h4 h5 h6 blockquote "
                    "section article header footer center".split())
INLINE_MACROS = {"print", "=", "-"}


def is_boundary(item):
    """Граница фраз: перевод строки, <br>/<p>/<div>..., блочные макросы (<<if>>, <<link>>, ...)."""
    k = getattr(item, "kind", "")
    if k == "nl":
        return True
    if k == "tag":
        m = re.match(r"</?([A-Za-z][\w-]*)", item.s)
        return bool(m) and m.group(1).lower() in BOUNDARY_TAGS
    if hasattr(item, "mname"):
        name = item.mname
        if name in INLINE_MACROS or letter_macro(item):
            return False
        if name in BLOCK_MACROS or (name.startswith("end") and name[3:] in BLOCK_MACROS):
            return True
        return False  # свои виджеты игры (<<Master>>, <<EventNameLink $x>>) обычно печатают текст внутри фразы
    return False


BLOCK_MACROS = set(("if elseif else for break continue switch case default link button linkreplace linkappend "
                    "linkprepend click actions choice back return replace append prepend remove copy addclass "
                    "removeclass toggleclass nobr silently widget script run set unset capture timed next repeat "
                    "stop type do redo include display goto audio cacheaudio createaudiogroup createplaylist "
                    "playlist masteraudio waitforaudio textbox textarea numberbox checkbox radiobutton listbox "
                    "cycle option optionsfrom remember forget done").split())


def build_units(marked, markup):
    """Режет текст с метками на фразы по границам; каждая фраза — отдельная единица перевода."""
    parts, buf = [], []

    def flush():
        seg = "".join(buf)
        buf.clear()
        if not seg:
            return
        lead, core, trail = split_line(seg)
        glued = (not lead or not lead[-1].isspace()) and (not trail or not trail[0].isspace())
        if glued and markup and re.fullmatch(r"[a-z]{1,2}", MARK.sub("", core)):
            parts.append(seg)  # >>th<< — буквы-кусочки внутри кода (шепелявость), не слова
            return
        if needs_translation(core):
            t = Text(core, markup=markup)
            seq.append(("t", t))
            parts.extend([lead, MarkupLine(t) if markup else t, trail])
        else:
            parts.append(seg)

    seq = []
    for tok in MARK_SPLIT.split(marked):
        m = MARK.fullmatch(tok)
        if m and is_boundary(ITEMS[int(m.group(1))]):
            flush()
            parts.append(tok)
            seq.append(("b", ITEMS[int(m.group(1))]))
        elif tok:
            buf.append(tok)
    flush()
    if markup:
        link_neighbors(seq)
    return parts


HARD_BREAK = BOUNDARY_TAGS | {"nl"}


CTX_ISOLATE = set(("link button linkreplace linkappend linkprepend click replace append prepend widget capture "
                   "timed repeat type do actions choice textbox textarea listbox cycle script").split())


def ctx_kind(it):
    name = getattr(it, "mname", "")
    src = getattr(it, "s", "") or ""
    closing = src.startswith("<</")
    if name in ("if", "switch"):
        return "close" if closing else "open"
    if name in ("elseif", "else", "case", "default"):
        return "branch"
    if name in ("endif", "endswitch"):
        return "close"
    if name in CTX_ISOLATE or (name.startswith("end") and name[3:] in CTX_ISOLATE):
        return "hard"
    k = getattr(it, "kind", "")
    if k == "nl":
        return "hard"
    if k == "tag":
        tm = re.match(r"</?([A-Za-z][\w-]*)", src)
        if tm and tm.group(1).lower() in HARD_BREAK:
            return "hard"
    return ""


def link_neighbors(seq):
    """Соседние фразы для подсказок с учётом <<if>>/<<switch>>: у фразы из ветки слева — текст до <<if>>,
    справа — текст после <</if>>; у текста после <</if>> слева — первая ветка (как пример)."""
    segments, root = [], []
    segments.append(root)
    stack, frames = [root], []
    for k, x in seq:
        if k == "t":
            stack[-1].append(x)
            continue
        kd = ctx_kind(x)
        if kd == "open":
            node = ["if", [[]]]
            stack[-1].append(node)
            frames.append(node)
            stack.append(node[1][-1])
        elif kd == "branch" and frames:
            frames[-1][1].append([])
            stack[-1] = frames[-1][1][-1]
        elif kd == "close" and frames:
            frames.pop()
            stack.pop()
        elif kd == "hard":
            root = []
            segments.append(root)
            stack, frames = [root], []

    def lin(node, depth=0):
        if isinstance(node, Text):
            return [node]
        if depth > 20:
            return []
        first = next((b for b in node[1] if b), [])
        out = []
        for x in first:
            out.extend(lin(x, depth + 1))
            if len(out) > 12:
                break
        return out

    def visit(lst, left, right, depth=0):
        if depth > 20:
            return
        n = len(lst)
        lins = [lin(x) for x in lst]
        suf = [None] * (n + 1)
        suf[n] = right[:6]
        for i in range(n - 1, -1, -1):
            suf[i] = (lins[i] + suf[i + 1])[:6]
        pre = left[-6:]
        for i, x in enumerate(lst):
            if isinstance(x, Text):
                x.ctx_left_list, x.ctx_right_list = pre, suf[i + 1]
            else:
                for br in x[1]:
                    visit(br, pre, suf[i + 1], depth + 1)
            pre = (pre + lins[i])[-6:]

    for seg in segments:
        visit(seg, [], [])


class MultiText:
    """Строка JS, разбитая на фразы. Ведёт себя как Text для владельца (Str/Tmpl/Chain)."""

    def __init__(self, parts):
        self.p = parts
        self.texts = [x for x in parts if isinstance(x, Text)]
        self.core = "".join(x.core if isinstance(x, Text) else x for x in parts)
        self.single = len(self.texts) == 1

    @property
    def active(self):
        return any(t.active for t in self.texts)

    @active.setter
    def active(self, v):
        for t in self.texts:
            t.active = v

    @property
    def cond(self):
        return self.texts[0].cond

    def gendered(self):
        return self.single and self.texts[0].gendered()

    def parts(self, v="n"):
        out = []
        for x in self.p:
            if isinstance(x, Text):
                out.extend(x.parts(v if self.single else "n"))
            elif x:
                out.extend(expand_parts(x))
        return flatten(out)


ATTR_RE = re.compile(r"(?<![\w-])[\w:-]+\s*=\s*(?:\"[^\"]*\"|'[^']*')")


def protect_fragments(s):
    """Куски кода внутри строк JS, которые не закрыты в этой же строке (их продолжение — в соседней
    строке склейки): '<img src="', '" class="x">', '[[Текст|Пассаж][$x = "a", ', 'style="..." width="1"/>'.
    Без этого переводчик портит HTML/SVG и цели ссылок."""
    def keep(frag):
        return reg(Raw(frag, "frag"))

    # [[ без закрытия — всё до конца строки
    i = s.find("[[")
    while i >= 0:
        if scan_link(s, i) is None:
            s = s[:i] + keep(s[i:])
            break
        i = s.find("[[", scan_link(s, i)[0])
    # хвост ссылки в начале строки: ...]] без [[ перед ним
    j = s.find("]]")
    if j >= 0 and ("[[" not in s[:j]):
        s = keep(s[:j + 2]) + s[j + 2:]
    # << без >> — до конца; >> без << — с начала
    i = s.rfind("<<")
    if i >= 0 and ">>" not in s[i:]:
        s = s[:i] + keep(s[i:])
    j = s.find(">>")
    if j >= 0 and "<<" not in s[:j]:
        s = keep(s[:j + 2]) + s[j + 2:]
    # атрибуты HTML: style='...', class="..."
    s = ATTR_RE.sub(lambda m: keep(m.group(0)), s)
    # незакрытый тег в конце: '<img src=' / '<g transform="'
    m = re.search(r"<[A-Za-z!/][^<>]*$", s)
    if m:
        s = s[:m.start()] + keep(m.group(0))
    # хвост тега в начале: '">' / '" class="x">' / '/>'
    m = re.match(r"^(?:\s|[\"'/]|[\w:-]+\s*=\s*\S*?|" + M_OPEN + r"\d+" + M_CLOSE + r")*>", s)
    if m and m.group(0).strip(" >"):
        s = keep(m.group(0)) + s[m.end():]
    # начало атрибута в конце: ' width="'
    m = re.search(r"[\w:-]+\s*=\s*[\"']$", s)
    if m:
        s = s[:m.start()] + keep(m.group(0))
    return s


def make_text(val):
    marked = protect(protect_fragments(val), newlines=True)
    lead, core, trail = split_ws(marked)
    return lead, MultiText(build_units(core, markup=False)), trail


class Str:
    """Строковый литерал JS: "..." или '...'."""

    def __init__(self, tok, ctx, sc=False):
        self.raw, self.q, self.ctx, self.sc = tok.text, tok.text[0], ctx, sc
        self.active = self.claimed = False
        self.modes = {}
        self.text = None
        self.passage = CUR["passage"]
        self.pure = bool(CUR.get("pure_js"))  # строка в чистом JavaScript (Story JavaScript, <<script>>)
        self.append = False  # дописывается к тексту: r += "Trim", "Caucasian" + ...
        self.wrole = False  # подпись — по разбору макроса/виджета игры (не <<link>>)
        try:
            self.val = None if tok.broken else js_unescape(tok.text[1:-1])
        except (ValueError, OverflowError):
            self.val = None
        if self.val in ("use strict", "use asm"):
            ctx = self.ctx = "key"  # директива JavaScript, не текст
        if self.val is not None and LATIN.search(self.val):
            count_gender(self.val)
            if ctx != "label":
                VALUE_CANDS.add(self.val)
            if ctx == "key":
                KEYS.add(self.val.strip().lower())
            else:
                self.lead, self.text, self.trail = make_text(self.val)
                self.text.active = False
        JSUNITS.append(self)

    def finalize(self):
        LAST["reason"] = ""
        self.active = (self.text is not None and not self.claimed
                       and needs_translation(self.text.core) and str_ok(self.val, self.ctx, append=self.append,
                                                                          wrole=self.wrole))
        if self.active and self.pure and self.ctx == "data" and not re.search(r"\s", self.val.strip()) \
                and not (self.append and APPEND_WORD.fullmatch(strip_markup(self.val.strip()))):
            self.active = False  # FindKeywordValue(this.args, "minexhaustion") — одно слово в коде почти всегда ключ
            LAST["reason"] = "одно слово в JavaScript — вероятно, ключ"
        self.reason = "" if self.active else LAST["reason"]
        if self.text is not None:
            self.text.active = self.active

    def pieces(self, v="n"):
        return flatten([self.lead] + self.text.parts(v) + [self.trail])

    def render(self):
        if not self.active:
            return self.raw
        out = []
        for p in self.pieces():
            if isinstance(p, Expr):
                out.append(p.marker)
            else:
                out.append(js_escape(p, self.q))
        return self.q + "".join(out) + self.q


def wrap(e):
    e = e.strip()
    if re.fullmatch(r"[\w$]+(?:\.[\w$]+)*", e):
        return e
    if e.startswith("(") and e.endswith(")"):
        toks, _ = tokenize(e)
        depth = 0
        for t in toks:
            if t.type == "punct" and t.text in "([{":
                depth += 1
            elif t.type == "punct" and t.text in ")]}":
                depth -= 1
                if depth == 0 and t.e != len(e):
                    break
        else:
            return e
    return "(" + e + ")"


def gender_cond(text):
    return "ruGender(" + text.cond.render().strip() + ")"


class Tmpl:
    """Шаблонная строка `...${expr}...`."""

    def __init__(self, src, tok, ctx, tagged):
        self.ctx, self.tagged = ctx, tagged
        self.active = False
        self.modes = {}
        self.text = None
        self.passage = CUR["passage"]
        self.broken = tok.broken
        self.raw = tok.text
        self.items = []  # ('text', raw) | ('expr', Expr)
        for part in tok.tparts:
            if part[0] == "text":
                self.items.append(("text", part[1]))
            else:
                _, sub, a, b = part
                seq = js_build(src, sub, "data")
                ex = Expr(seq, src[a:b])
                reg(ex)
                self.items.append(("expr", ex))
        self.check = None
        if not self.broken and not tagged:
            try:
                core = "".join(js_unescape(x) if k == "text" else x.marker for k, x in self.items)
                self.check = "".join(js_unescape(x) if k == "text" else "" for k, x in self.items)
            except (ValueError, OverflowError):
                core = None
            if core is not None and LATIN.search(self.check):
                if ctx == "key":
                    if not any(k == "expr" for k, _ in self.items):
                        KEYS.add(self.check.strip().lower())
                else:
                    self.lead, self.text, self.trail = make_text(core)
                    self.text.active = False
        JSUNITS.append(self)

    def finalize(self):
        has_expr = any(k == "expr" for k, _ in self.items)
        LAST["reason"] = ""
        ok = self.text is not None and needs_translation(self.text.core)
        if ok and has_expr and self.ctx == "data" and not looks_code(self.check.strip()):
            ok = textual(self.check) or (OPTS.aggressive and bool(re.search(r"[A-Za-z]{2}", self.check))
                                         and bool(re.search(r"\s", self.check)))
        elif ok:
            ok = str_ok(self.check, self.ctx, check_keys=not has_expr)
        if ok and has_expr:
            try:
                part = any(k == "text" and key_part(js_unescape(x)) for k, x in self.items)
            except (ValueError, OverflowError):
                part = False
            if part:
                ok = False
                LAST["reason"] = "кусок строки, с которой игра сравнивает (её склеивают из частей)"
        self.reason = "" if ok else (LAST["reason"] or "шаблон без текста")
        self.active = ok
        if self.text is not None:
            self.text.active = self.active

    def render(self):
        if not self.active:
            if self.broken:
                return self.raw
            return "`" + "".join(x if k == "text" else "${" + x.render() + "}"
                                 for k, x in self.items) + "`"

        def j(v):
            ps = flatten([self.lead] + self.text.parts(v) + [self.trail])
            return "`" + "".join(("${ruT(" + p.render() + ")}" if VALUES["on"] and expr_value_ok(p)
                                  else "${" + p.render() + "}") if isinstance(p, Expr)
                                 else js_escape(p, "`") for p in ps) + "`"
        if self.text.gendered():
            c = gender_cond(self.text)
            return f"({c} === 1 ? {j('f')} : {c} === 0 ? {j('m')} : {j('n')})"
        return j("n")


class Chain:
    """Склейка строк: "You have " + $gold + " coins"."""

    def __init__(self, src, ops, seps, ctx):
        self.ops, self.seps, self.ctx = ops, seps, ctx  # ops: Str | Expr
        self.merged = self.active = False
        self.modes = {}
        self.passage = CUR["passage"]
        self.raw = None
        strs = [o for o in ops if isinstance(o, Str)]
        self.text = None
        if all(s.val is not None for s in strs):
            core = "".join(o.val if isinstance(o, Str) else o.marker for o in ops)
            self.check = "".join(o.val if isinstance(o, Str) else "" for o in ops)
            self.q = strs[0].q if strs else '"'
            if strs[0].q == "`":
                self.q = '"'
            self.lead, self.text, self.trail = make_text(core)
            self.text.active = False
        CHAINS.append(self)
        JSUNITS.append(self)

    def finalize(self):
        strs = [o for o in self.ops if isinstance(o, Str)]
        ok = (self.text is not None and self.ctx != "key" and needs_translation(self.text.core)
              and not any(is_key(s.val) for s in strs)
              and str_ok(self.check, self.ctx, check_keys=False))
        if ok and strs and all(re.fullmatch(r"[\w$.-]+", s.val or "") for s in strs):
            ok = False  # name + "UsedTriggers" — так собирают имена переменных/ключей, это не текст
        self.merged = self.active = ok
        if self.text is not None:
            self.text.active = ok
        if ok:
            for s in strs:
                s.claimed = True

    def render(self):
        if not self.merged:
            out = []
            for sep, op in zip(self.seps, self.ops):
                out.append(sep)
                out.append(op.render())
            return "".join(out)

        def j(v):
            segs = []
            for p in flatten([self.lead] + self.text.parts(v) + [self.trail]):
                if isinstance(p, str) and not p:
                    continue
                if isinstance(p, Expr):
                    segs.append(["e", p])
                elif segs and segs[-1][0] == "s":
                    segs[-1][1] += p
                else:
                    segs.append(["s", str(p)])
            out = []
            if not segs or (segs[0][0] == "e" and (len(segs) < 2 or segs[1][0] == "e")):
                out.append(self.q + self.q)
            for k, val in segs:
                if k == "s":
                    out.append(self.q + js_escape(val, self.q) + self.q)
                elif VALUES["on"] and expr_value_ok(val):
                    out.append("ruT(" + val.render() + ")")
                else:
                    out.append(wrap(val.render()))
            return " + ".join(out)
        if self.text.gendered():
            c = gender_cond(self.text)
            return f"({c} === 1 ? ({j('f')}) : {c} === 0 ? ({j('m')}) : ({j('n')}))"
        return j("n")


CMP = set("=== !== == != < > <= >= is isnot eq neq gt gte lt lte".split())
NOT_CALLEES = set("if for while switch catch function return typeof with".split())
BOUND_KW = set(("return case var let const if else while for do switch throw yield in of "
                "instanceof to is isnot eq neq gt gte lt lte and or function class export "
                "import default break continue").split())
PREFIX_KW = set("typeof void delete new await not def ndef".split())
TIGHT = {"*", "/", "%", "**", ".", "?."}
START_AFTER = set((", ; ( [ { } ? : = += -= *= /= %= **= <<= >>= >>>= &= |= ^= &&= ||= ??= => "
                   "=== !== == != < > <= >= && || ?? << >> >>> & | ^ - ...").split())


def js_build(src, toks, ctx0="data", mode="js"):
    """Строит Seq для токенов JS. mode: js | label (аргументы <<link>>) | args (прочие макросы) |
    ("roles", {номер аргумента: "key"/"label"}) — макрос игры, для которого известно, какой аргумент что значит."""
    roles = None
    if isinstance(mode, tuple):
        roles, mode = mode[1], "args"
    sig = [i for i, t in enumerate(toks) if t.type not in ("ws", "comment")]
    argn = {}  # номер аргумента макроса (они разделены пробелами) для каждого значимого токена верхнего уровня
    if roles:
        depth, cur, seen = 0, -1, False
        for i, t in enumerate(toks):
            if t.type in ("ws", "comment"):
                if depth == 0 and seen:
                    seen = False
                continue
            if depth == 0 and not seen:
                cur, seen = cur + 1, True
            if depth == 0:
                argn[i] = cur
            if t.type == "punct" and t.text in "([{":
                depth += 1
            elif t.type == "punct" and t.text in ")]}":
                depth = max(0, depth - 1)
    S = [toks[i] for i in sig]
    n = len(S)
    pos_of = {ti: k for k, ti in enumerate(sig)}
    match, info, stack = {}, [None] * n, []
    for k, t in enumerate(S):
        if t.type == "ident":  # имена свойств и переменных: строки с такими значениями — вероятно ключи
            if t.text[:1] in "$_":
                IDENTS.add(t.text.lstrip("$_"))
            elif k and S[k - 1].text in (".", "?."):
                IDENTS.add(t.text)
            elif k + 1 < n and S[k + 1].text == ":" and k and S[k - 1].text in ("{", ","):
                IDENTS.add(t.text)
        top = stack[-1] if stack else None
        info[k] = (top[1], top[2], top[3], top[0]) if top else (None, 0, None, None)
        if t.type != "punct":
            continue
        if t.text in ("(", "[", "{"):
            callee = None
            if t.text == "(" and k and S[k - 1].type == "ident" and S[k - 1].text not in NOT_CALLEES:
                callee = S[k - 1].text
            kind = t.text
            if t.text == "[" and k and (S[k - 1].type in ("ident", "str", "tmpl", "num")
                                        or S[k - 1].text in (")", "]")):
                kind = "index"
            elif t.text == "[" and top and top[3] == "(" and top[1]:
                r = KEY_FUNCS.get(top[1])  # массив прямо в аргументах add([...]), includes([...]) ...
                if r is not None and (r == "all" or top[2] in r):
                    kind = "keyarray"
            stack.append([k, callee, 0, kind])
        elif t.text in (")", "]", "}"):
            if stack:
                o = stack.pop()
                match[o[0]], match[k] = k, o[0]
        elif t.text == "," and stack:
            stack[-1][2] += 1

    def ctx_at(a, b):
        if mode == "label":
            return "label" if a == 0 else "key"
        if roles and a == b and sig[a] in argn and argn[sig[a]] in roles:
            return roles[argn[sig[a]]]
        prev = S[a - 1] if a else None
        nxt = S[b + 1] if b + 1 < n else None
        pt = prev.text if prev is not None else ""
        nt = nxt.text if nxt is not None else ""
        callee, argi, kind, opener = info[a]
        base = ctx0
        if kind == "keyarray":
            return "key"
        if kind == "[" and opener is not None and opener >= 2 and S[opener - 1].text == ":" \
                and S[opener - 2].text.strip("'\"") in KEY_KEYS:
            return "key"  # locationTags: ['home', 'inside'] — элементы массива под «ключевым» свойством
        if kind == "[" and opener in match:  # ["a", "b"].includes(x) — элементы массива это ключи
            c = match[opener]
            if c + 2 < n and S[c + 1].text in (".", "?.") and S[c + 2].text in KEY_FUNCS:
                return "key"
        if ctx0 == "output" and kind is not None and not (kind == "(" and callee is None):
            base = "data"  # аргументы функций и элементы массивов внутри <<print>> — данные
        if pt in CMP or nt in CMP or pt == "case" or nt in ("in", ".", "?."):
            return "key"
        if nt == ":" and pt in ("{", ",") and kind == "{":
            return "key"
        if kind == "index" and pt == "[" and nt == "]":
            return "key"
        if callee == "either" and ctx0 == "output":
            return "label"  # <<print either("big", "huge")>> — эти слова видит игрок
        if callee:
            r = KEY_FUNCS.get(callee)
            if r is not None and (r == "all" or argi in r):
                return "key"
            r = OUT_FUNCS.get(callee)
            if r is not None and (r == "all" or argi in r):
                return "output"
        if pt in ("=", "+=", "to") and a >= 2:
            prop = S[a - 2].text
            if prop in ATTR_PROPS:
                return "key"
            if prop in OUT_PROPS:
                return "output"
        if (pt == ":" and a >= 3 and kind == "{" and S[a - 3].text in ("{", ",")
                and S[a - 2].type in ("ident", "str")):
            key = S[a - 2].text.strip("'\"")
            if key in KEY_KEYS:
                return "key"
            if key in OUT_KEYS:
                return "output"
        return base

    # --- поиск склеек "строка" + выражение + "строка" ---
    chains = {}
    if mode == "js":
        def operand(k):
            j, last = k, None
            while j < n:
                t, tx = S[j], S[j].text
                if t.type == "punct":
                    if tx in ("(", "["):
                        if j not in match:
                            return None
                        j, last = match[j] + 1, "prim"
                        continue
                    if tx in TIGHT:
                        if last != "prim":
                            return None
                        j, last = j + 1, "op"
                        continue
                    if tx in ("++", "--") and last == "prim":
                        j += 1
                        continue
                    if tx in ("!", "~", "++", "--") or (tx in ("-", "+") and last != "prim"):
                        if last == "prim":
                            break
                        j, last = j + 1, "op"
                        continue
                    break
                if t.type == "ident":
                    if tx in PREFIX_KW:
                        if last == "prim":
                            break
                        j, last = j + 1, "op"
                        continue
                    if tx in BOUND_KW or last == "prim":
                        break
                    j, last = j + 1, "prim"
                    continue
                if t.type in ("num", "str", "tmpl", "regex"):
                    if last == "prim":
                        break
                    j, last = j + 1, "prim"
                    continue
                break
            return j - 1 if last == "prim" and j > k else None

        k = 0
        while k < n:
            prev = S[k - 1] if k else None
            start = (prev is None or (prev.type == "punct" and prev.text in START_AFTER)
                     or (prev.type == "ident" and prev.text in BOUND_KW))
            if not start:
                k += 1
                continue
            e = operand(k)
            if e is None:
                k += 1
                continue
            ops = [(k, e)]
            while e + 1 < n and S[e + 1].type == "punct" and S[e + 1].text == "+":
                e2 = operand(e + 2)
                if e2 is None:
                    break
                ops.append((e + 2, e2))
                e = e2
            single_str = [a == b and S[a].type == "str" for a, b in ops]
            if (len(ops) >= 2 and (single_str[0] or single_str[1])
                    and any(s and LATIN.search(S[a].text) for s, (a, b) in zip(single_str, ops))):
                chains[sig[ops[0][0]]] = (ops, ctx_at(ops[0][0], ops[-1][1]))
            k += 1

    where = CUR.get("macro") or ""

    def snippet(a, b):
        """Код вокруг строки — для анализа структуры (--analyze)."""
        def show(t):
            return {"str": '"…"', "tmpl": "`…`", "num": "0", "regex": "/…/"}.get(t.type, t.text)
        left = " ".join(show(t) for t in S[max(0, a - 6):a])
        right = " ".join(show(t) for t in S[b + 1:b + 4])
        pre = f"<<{where} " if where else ""
        return (pre + left + " ⟨X⟩ " + right).strip()

    def prop_of(k):
        """Имя свойства, с которым связана строка: hColor = "blonde", fetish == "sub", case "sub"."""
        j, depth = k - 1, 0
        while j >= 0 and k - j < 16:
            t = S[j]
            tx = t.text
            if t.type == "punct" and tx in (")", "]"):
                depth += 1
            elif t.type == "punct" and tx in ("(", "["):
                depth = max(0, depth - 1)
            elif depth == 0 and t.type == "ident" and tx == "case":
                return switch_at(j)
            elif depth == 0 and (tx in ("=", "==", "===", "!=", "!==", "+=", ":")
                                 or (t.type == "ident" and tx in ("to", "is", "isnot", "eq", "neq"))):
                if j and S[j - 1].type == "ident":
                    return S[j - 1].text
                if tx == ":" and j and S[j - 1].type == "str":
                    return S[j - 1].text[1:-1]
                return None
            elif depth == 0 and t.type == "punct" and tx in (";", "{", "}"):
                return None
            j -= 1
        if k + 2 < n and S[k + 1].text in CMP:  # "sub" == x.fetish
            e = k + 2
            while e + 2 < n and S[e + 1].text in (".", "?."):
                e += 2
            return S[e].text if S[e].type == "ident" else None
        return None

    def switch_at(j):
        while j >= 0:
            if S[j].type == "ident" and S[j].text == "switch" and j + 1 < n and S[j + 1].text == "(":
                end = match.get(j + 1)
                if end:
                    return last_ident(" ".join(t.text for t in S[j + 2:end]))
                return None
            j -= 1
        return None

    def make_unit(ti, ctx):
        u = _make_unit(ti, ctx)
        if isinstance(u, (Str, Tmpl)):
            k = pos_of[ti]
            u.snip = snippet(k, k)
            if isinstance(u, Str) and u.val:
                prop = prop_of(k)
                note_prop(u.val, prop)
                if prop and u.text is not None and u.ctx != "label":
                    for t in u.text.texts:
                        t.prop_hint = prop.lstrip("$_")
        return u

    def _make_unit(ti, ctx):
        t = toks[ti]
        k = pos_of[ti]
        if t.type == "str":
            u = Str(t, ctx if ctx else ctx_at(k, k), sc=(mode != "js"))
            u.append = (k > 0 and S[k - 1].text in ("+=", "+")) or (k + 1 < n and S[k + 1].text == "+")
            u.wrole = bool(roles) and u.ctx == "label" and sig[k] in argn and argn[sig[k]] in roles
            return u
        # шаблон
        if mode != "js":  # в аргументах макросов `...` — это выражение JS
            inner = src[t.s + 1:t.e - 1] if not t.broken else None
            if inner is None:
                return t.text
            c = "output" if ctx_at(k, k) == "label" else "data"
            return Seq(["`", process_js(inner, c), "`"])
        prev = S[k - 1] if k else None
        tagged = prev is not None and (prev.type in ("ident", "str", "tmpl") or prev.text in (")", "]")) \
            and prev.text not in BOUND_KW and prev.text not in PREFIX_KW
        return Tmpl(src, t, ctx if ctx else ctx_at(k, k), tagged)

    def walk(i0, i1):
        parts, i = [], i0
        while i < i1:
            if i in chains:
                ops_k, cctx = chains[i]
                last_ti = sig[ops_k[-1][1]]
                if last_ti < i1:
                    ops, seps, prev_end = [], [], i
                    for a, b in ops_k:
                        ta, tb = sig[a], sig[b]
                        seps.append(src[toks[prev_end].s:toks[ta].s] if ops else "")
                        if a == b and S[a].type == "str":
                            ops.append(Str(S[a], cctx))
                        else:
                            seq = Seq(walk(ta, tb + 1))
                            ex = Expr(seq, src[toks[ta].s:toks[tb].e])
                            reg(ex)
                            ops.append(ex)
                        prev_end = tb + 1
                    ch = Chain(src, ops, seps, cctx)
                    ch.snip = snippet(ops_k[0][0], ops_k[-1][1])
                    parts.append(ch)
                    i = last_ti + 1
                    continue
            t = toks[i]
            if t.type in ("str", "tmpl"):
                parts.append(make_unit(i, None))
            else:
                parts.append(t.text)
            i += 1
        return parts

    return Seq(walk(0, len(toks)), kind="code")


def process_js(src, ctx="data", mode="js"):
    toks, _ = tokenize(src)
    return js_build(src, toks, ctx, mode)


# ===========================================================================
# Проверки после перевода
# ===========================================================================

def macro_balance(s, names):
    bal = {}
    for m in re.finditer(r"<<\s*(/?)\s*([A-Za-z][\w-]*)", s):
        name = m.group(2)
        if name in names:
            bal[name] = bal.get(name, 0) + (-1 if m.group(1) else 1)
    return {k: v for k, v in bal.items() if v}, s.count("[["), s.count("]]")


def containers(*texts):
    """Имена макросов-контейнеров (у которых встречается закрывающий тег)."""
    return {m.group(1) for t in texts for m in re.finditer(r"<</\s*([A-Za-z][\w-]*)", t)}


def js_ok(s):
    toks, _ = tokenize(s)
    bal = []
    pairs = {")": "(", "]": "[", "}": "{"}
    for t in toks:
        if t.broken:
            return False
        if t.type == "comment" and t.text.startswith("/*") and not t.text.endswith("*/"):
            return False
        if t.type == "punct":
            if t.text in "([{":
                bal.append(t.text)
            elif t.text in pairs:
                if not bal or bal.pop() != pairs[t.text]:
                    return False
    return not bal


def node_check(code):
    node = shutil.which("node")
    if not node:
        return None
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(code)
        path = f.name
    try:
        r = subprocess.run([node, "--check", path], capture_output=True, text=True, timeout=120)
        return r.returncode == 0
    except Exception:  # noqa: BLE001
        return None
    finally:
        os.unlink(path)


def ru_gender_helper():
    fem = sorted({f.lower() for m, f in GENDER.values()} | {"her"})
    masc = sorted({m.lower() for m, f in GENDER.values()} - set(fem))
    return ("/* ruGender: выбор варианта перевода по роду (she -> 1, he -> 0). */\n"
            "window.ruGender = function (v) {\n"
            "\tvar s = String(v).trim().toLowerCase();\n"
            f"\tif ({json.dumps(fem)}.indexOf(s) !== -1) {{ return 1; }}\n"
            f"\tif ({json.dumps(masc)}.indexOf(s) !== -1) {{ return 0; }}\n"
            "\treturn -1;\n"
            "};\n")


# ===========================================================================
# Переводчик (Google) с кэшем
# ===========================================================================

class Halted(Exception):
    """Рабочий поток остановлен (Ctrl+C или конец перевода)."""


class RateLimited(Exception):
    """Переводчик слишком долго просит подождать."""


class QuotaExceeded(Exception):
    """Лимит ключа исчерпан или ключ не подходит."""


class BadLanguage(Exception):
    """Google не знает такой код языка (ответ 400 на всех адресах)."""


class FreeBlocked(Exception):
    """Все бесплатные адреса Google сейчас блокируют запросы."""


def why_of(e):
    """Почему адрес не ответил — для строки «Почему не отвечают» в игре."""
    kind = classify_error(e)
    if kind in ("rate", "quota"):
        return kind
    if isinstance(e, ValueError):
        return "bad"
    if getattr(getattr(e, "response", None), "status_code", None):
        return "other"
    return "net"


def classify_error(e):
    if isinstance(e, FreeBlocked):
        return "rate"
    name, msg = type(e).__name__, str(e).lower()
    status = getattr(getattr(e, "response", None), "status_code", None)
    if status in (401, 403, 456) or "quota" in msg or "limit exceeded" in msg:
        return "quota"
    if status == 429 or "toomanyrequests" in name.lower() or "429" in msg or "too many" in msg:
        return "rate"
    return "other"


CACHE_VERSION = 3          # меняется, когда скрипт начинает по-другому готовить фразы для переводчика
META_KEY = "\u0001meta"
SAME_MARK = "\u0001same\u0001"  # в кэше: фраза проверена по одной и правда не меняется (имена и т.п.)
CYRILLIC_LANGS = {"ru", "uk", "be", "bg", "sr", "mk", "kk", "ky", "tg", "mn"}


def untranslated(src, res, dst):
    """Переводчик вернул фразу без перевода (бывает, когда в пачке много коротких фраз с кодом)."""
    if res is None:
        return True
    plain = PH_IN.sub(" ", src)
    words = re.findall(r"[A-Za-z]{3,}", plain)
    if not words:
        return False
    if res.strip() == src.strip():
        return True
    if dst.split("-")[0].lower() in CYRILLIC_LANGS and len(words) >= 2:
        return not re.search(r"[А-Яа-яЁёІіЇїЄєЎў]", PH_IN.sub(" ", res))
    return False


def complexity(s):
    """Сколько в фразе кода: меток ⟦n⟧ много, а слов мало — такие фразы переводим маленькими пачками."""
    n_ph = len(PH_IN.findall(s))
    n_words = len(re.findall(r"[A-Za-z]{2,}", PH_IN.sub(" ", s)))
    return n_ph >= 3 or (n_ph >= 1 and n_words <= 3 * n_ph)


ENGINES = ("free", "google", "google-cloud", "deepl", "microsoft")
RATE_WAITS = (30, 60, 120, 300, 600, 900)


class Translator:
    FREE_LIMIT = 4500
    # (символов в запросе, фраз в запросе)
    LIMITS = {"free": (4500, 250), "google": (4500, 250), "google-cloud": (5000, 128), "deepl": (20000, 50),
              "microsoft": (10000, 500)}

    def __init__(self, src, dst, cache_path, engine="google", key=None, region=None, delay=0.5,
                 glossary=None, max_chars=0, max_wait=60):
        self.src, self.dst, self.engine, self.key, self.region = src, dst, engine, key, region
        self.cache_path, self.glossary = cache_path, glossary or {}
        self.delay = self.base_delay = delay
        self.max_chars, self.max_wait = max_chars, max_wait * 60
        self.sent = 0                      # символов отправлено за этот запуск
        self.offline, self.stop_reason = False, ""
        self.rate_hits = self.waited = self.ok_streak = 0
        self.cache = {}
        if os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as f:
                self.cache = json.load(f)
            bad = [k for k, v in self.cache.items() if not k.startswith("\u0001") and isinstance(v, str)
                   and SAME_MARK + k not in self.cache and untranslated(k, v, dst)]
            for k in bad:
                del self.cache[k]
            self.redo = len(bad)
        else:
            self.redo = 0
        meta = self.cache.get(META_KEY)
        phrases = sum(1 for k in self.cache if not k.startswith("\u0001"))
        self.cache_old = phrases > 0 and not (isinstance(meta, dict) and meta.get("v", 0) >= CACHE_VERSION)
        self.last_save = time.time()
        self.gt = None
        self.lock, self.save_lock = threading.RLock(), threading.Lock()
        self.halt = threading.Event()
        self.workers = 1
        self.net_rest = 1800     # сколько отдыхает адрес, который не ответил (сеть); в -c — меньше
        self.fast_fail = False   # -c: при ошибке сети не ждать минутами, а сразу отвечать игре
        self._tls = threading.local()

    def _http(self):
        """Своё соединение для каждого потока: повторные запросы идут без нового подключения (быстрее)."""
        sess = getattr(self._tls, "s", None)
        if sess is None:
            import requests
            sess = self._tls.s = requests.Session()
        return sess

    # --- кэш ---
    def start_fresh(self):
        """Старый кэш → <кэш>.bak-ДАТА, переводим заново."""
        if self.cache_path and os.path.exists(self.cache_path):
            bak = self.cache_path + time.strftime(".bak-%Y%m%d-%H%M%S")
            os.replace(self.cache_path, bak)
            print(f"Старый кэш сохранён как {bak}", file=sys.stderr)
        self.cache, self.cache_old, self.redo = {}, False, 0

    def save(self, force=False):
        if not self.cache_path:
            return
        with self.lock:
            if not (force or time.time() - self.last_save > 30):
                return
            data = {k: (dict(v) if isinstance(v, dict) else v) for k, v in self.cache.items()}
            if not os.path.exists(self.cache_path) and not any(not k.startswith("\u0001") for k in data):
                return  # переводов ещё нет — пустой файл кэша не создаём
            if not self.cache_old:
                data[META_KEY] = {"v": CACHE_VERSION}
            self.last_save = time.time()
        with self.save_lock:
            tmp = self.cache_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, self.cache_path)

    def has(self, s):
        return s in self.glossary or s in self.cache

    def peek(self, s):
        """Перевод из кэша (без запроса к переводчику) или None."""
        if s in self.glossary:
            return self.glossary[s]
        return self.cache.get(s)

    def get(self, s):
        """Перевод строки или None, если перевести сейчас нельзя (лимит/блокировка)."""
        if s in self.glossary:
            return self.glossary[s]
        if s not in self.cache and not self.offline:
            self.prefetch([s], quiet=True)
        return self.cache.get(s)

    # --- вызов с ожиданием при блокировке ---
    def _call(self, fn, *args, **kwargs):
        other = 0
        while True:
            try:
                res = fn(*args, **kwargs)
                self.rate_hits = self.waited = 0
                self.ok_streak += 1
                if self.ok_streak >= 20 and self.delay > self.base_delay:
                    self.delay = max(self.base_delay, self.delay * 0.8)
                    self.ok_streak = 0
                return res
            except (KeyboardInterrupt, Halted, BadLanguage):
                raise
            except Exception as e:  # noqa: BLE001
                kind = classify_error(e)
                self.ok_streak = 0
                if kind == "quota":
                    raise QuotaExceeded(str(e)) from e
                if kind == "rate":
                    wait = RATE_WAITS[min(self.rate_hits, len(RATE_WAITS) - 1)]
                    self.rate_hits += 1
                    if self.waited + wait > self.max_wait:
                        raise RateLimited(str(e)) from e
                    self.waited += wait
                    self.delay = min(self.delay * 2 + 0.5, 10.0)
                    until = time.strftime("%H:%M:%S", time.localtime(time.time() + wait))
                    print(f"\n  Переводчик просит подождать (слишком много запросов). Пауза "
                          f"{wait // 60} мин {wait % 60} с, продолжу в {until}. "
                          f"Пауза между запросами теперь {self.delay:.1f} с.", file=sys.stderr)
                    self._sleep(wait)
                    continue
                other += 1
                if other > 5 or (self.fast_fail and other > 1):
                    raise
                wait = 1 if self.fast_fail else 5 * 2 ** other
                print(f"\n  Ошибка: {e!r}. Повтор через {wait} с...", file=sys.stderr)
                self._sleep(wait)

    # --- движки ---
    # --- бесплатный Google: несколько адресов по кругу, заблокированные отдыхают ---
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/124.0 Safari/537.36")
    # Разные «клиенты» (gtx, dict-chrome-ex, мобильная страница) и разные адреса Google часто считаются
    # отдельно: когда один блокирует, другой ещё работает. Нерабочие у вас адреса проверка перед
    # переводом сама отключит, так что лишние записи не мешают.
    GOOGLE_EPS = (
        ("gtx", "translate.googleapis.com"), ("gtx", "translate.google.com"), ("gtx", "clients5.google.com"),
        ("gtx", "translate.google.com.ua"), ("gtx", "translate.google.de"),
        ("gtxt", "translate.googleapis.com"), ("gtxt", "clients5.google.com"), ("gtxt", "translate.google.com"),
        ("dict", "clients5.google.com"), ("dict", "translate.googleapis.com"), ("dict", "translate.google.com"),
        ("dict", "clients1.google.com"), ("dict", "clients2.google.com"), ("dict", "clients4.google.com"),
        ("dict", "clients6.google.com"),
        ("mweb", "translate.google.com"), ("mweb", "translate.google.com.ua"), ("mweb", "translate.google.de"),
        ("mweb", "translate.google.pl"),
        ("pa", "translate-pa.googleapis.com"),  # тот же сервер, что у виджета «Перевести сайт»
    )
    PA_KEY = "AIzaSyATBXajvzQLTDHEQbcpq0Ihe0vWDHmO520"  # общий открытый ключ виджета Google

    def _pool(self):
        if not hasattr(self, "eps"):
            self.eps = [{"kind": k, "host": h, "until": 0.0, "cool": 300, "busy": False}
                        for k, h in self.GOOGLE_EPS]
            self.rr = 0
        return self.eps

    def _take_ep(self, tried):
        """Следующий по кругу рабочий адрес, не занятый другим потоком (None — рабочих нет)."""
        eps = self._pool()
        while True:
            with self.lock:
                now, n = time.time(), len(eps)
                alive = [e for e in eps if e["until"] <= now and id(e) not in tried]
                if not alive:
                    return None
                for i in range(n):
                    ep = eps[(self.rr + i) % n]
                    if ep["until"] <= now and not ep["busy"] and id(ep) not in tried:
                        ep["busy"] = True
                        self.rr = (self.rr + i + 1) % n  # следующий запрос — на следующий адрес
                        return ep
            self._sleep(0.05)  # все рабочие адреса сейчас заняты другими потоками

    def probe(self):
        """Перед переводом: какие адреса Google сейчас отвечают. Нерабочие сразу отдыхают."""
        ok = []

        def test(ep):
            try:
                res = self._ep_call(ep, "Hello")
                if not res or not res.strip() or res.strip() == "Hello" and self.dst != self.src:
                    raise ValueError("пустой ответ")
                return ep, None
            except Exception as e:  # noqa: BLE001
                return ep, e
        print("Проверяю адреса Google...", file=sys.stderr)
        for ep, err in self._parallel(test, self._pool()):
            ep["why"] = None if err is None else why_of(err)
            if err is None:
                ok.append(self.ep_name(ep))
            else:
                ep["until"] = time.time() + (600 if classify_error(err) == "rate" or isinstance(err, ValueError)
                                             else 1800)
        print(f"Работают адреса Google: {len(ok)} из {len(self.eps)}" + (": " + ", ".join(ok) if ok else ""),
              file=sys.stderr)
        return len(ok)

    @staticmethod
    def _parallel(fn, items):
        """fn для всех items сразу в фоновых потоках (для быстрой проверки адресов)."""
        import queue
        q, items = queue.Queue(), list(items)
        for it in items:
            threading.Thread(target=lambda it=it: q.put(fn(it)), daemon=True).start()
        res = [q.get() for _ in items]
        order = {id(it): i for i, it in enumerate(items)}
        return sorted(res, key=lambda r: order[id(r[0])])

    @staticmethod
    def ep_name(ep):
        return {"gtx": "{}  (api)", "gtxt": "{}  (api-t)", "dict": "{}  (dict)",
                "mweb": "{}/m  (web)", "pa": "{}  (html)"}[ep["kind"]].format(ep["host"])

    def _ep_call(self, ep, text):
        http = self._http()
        if ep["kind"] == "pa":  # фразы — списком: строки никогда не склеиваются
            import html as htmlmod
            lines = text.split("\n")
            body = [[[htmlmod.escape(x, quote=False) for x in lines], self.src, self.dst], "wt_lib"]
            r = http.post(f"https://{ep['host']}/v1/translateHtml", data=json.dumps(body, ensure_ascii=False).encode(),
                          headers={"Content-Type": "application/json+protobuf", "X-Goog-API-Key": self.PA_KEY,
                                   "User-Agent": self.UA}, timeout=60)
            r.raise_for_status()
            res = r.json()[0]
            if not isinstance(res, list) or len(res) != len(lines):
                raise ValueError("неожиданный ответ")
            return "\n".join(htmlmod.unescape(re.sub(r"\s*<br\s*/?>\s*", " ", x or "")).replace("\n", " ") for x in res)
        if ep["kind"] == "gtx":
            r = http.post(f"https://{ep['host']}/translate_a/single",
                              params={"client": "gtx", "sl": self.src, "tl": self.dst, "dt": "t"},
                              data={"q": text}, headers={"User-Agent": self.UA}, timeout=60)
            r.raise_for_status()
            data = r.json()
            return "".join(seg[0] for seg in (data[0] or []) if seg and isinstance(seg[0], str))
        out = []
        for chunk in self._chunks(text, 1500):  # GET-запросы — короткими кусками
            if ep["kind"] in ("dict", "gtxt"):
                client = "dict-chrome-ex" if ep["kind"] == "dict" else "gtx"
                r = http.get(f"https://{ep['host']}/translate_a/t",
                                 params={"client": client, "sl": self.src, "tl": self.dst, "q": chunk},
                                 headers={"User-Agent": self.UA}, timeout=60)
                r.raise_for_status()
                data = r.json()
                if isinstance(data, dict):
                    out.append("".join(x.get("trans", "") for x in data.get("sentences", [])))
                else:
                    first = data[0]
                    out.append(first[0] if isinstance(first, list) else first)
            else:
                import html as htmlmod
                r = http.get(f"https://{ep['host']}/m",
                                 params={"sl": self.src, "tl": self.dst, "hl": self.dst, "q": chunk},
                                 headers={"User-Agent": self.UA}, timeout=60)
                r.raise_for_status()
                m = re.search(r'class="result-container">([\s\S]*?)</div>', r.text)
                if not m:
                    raise ValueError("в ответе нет перевода (возможно, капча)")
                out.append(htmlmod.unescape(m.group(1)))
        return "\n".join(out)

    @staticmethod
    def _chunks(text, limit):
        """Режет текст по строкам на куски <= limit."""
        chunks, cur = [], ""
        for line in text.split("\n"):
            if cur and len(cur) + len(line) + 1 > limit:
                chunks.append(cur)
                cur = line
            else:
                cur = f"{cur}\n{line}" if cur else line
        chunks.append(cur)
        return chunks

    def _google_pool(self, text):
        """Запрос через следующий по кругу рабочий адрес Google; заблокированные адреса отдыхают."""
        tried, n400, nerr = set(), 0, 0
        while True:
            ep = self._take_ep(tried)
            if ep is None:
                if n400 and n400 == nerr:
                    raise BadLanguage(f"Google не знает язык «{self.dst}»")
                raise FreeBlocked("все адреса Google сейчас заблокированы")
            try:
                res = self._ep_call(ep, text)
                if not isinstance(res, str) or (text.strip() and not res.strip()):
                    raise ValueError("пустой ответ")
                ep["cool"] = 300
                ep["why"] = None
                return res
            except KeyboardInterrupt:
                raise
            except Exception as e:  # noqa: BLE001
                tried.add(id(ep))
                nerr += 1
                if getattr(getattr(e, "response", None), "status_code", None) == 400:
                    n400 += 1  # «неверный запрос» — обычно неизвестный код языка; адрес не виноват
                    continue
                with self.lock:
                    ep["why"] = why_of(e)
                    if classify_error(e) in ("rate", "quota") or isinstance(e, ValueError):
                        ep["until"] = time.time() + ep["cool"]
                        mins = ep["cool"] // 60
                        ep["cool"] = min(ep["cool"] * 2, 3600)
                    else:  # адрес недоступен (сеть, DNS, блокировка провайдером)
                        ep["until"] = time.time() + self.net_rest
                        mins = max(1, self.net_rest // 60)
                    alive = sum(1 for x in self.eps if x["until"] <= time.time())
                print(f"\n  {self.ep_name(ep)}: не отвечает или блокирует — отдых {mins} мин; "
                      f"работающих адресов Google: {alive} из {len(self.eps)}", file=sys.stderr)
            finally:
                ep["busy"] = False

    def _free_text(self, text):
        """Склеенный через \\n текст: адреса Google по кругу."""
        self._sleep(self.delay)
        return self._google_pool(text)

    def _free_long(self, text):
        if len(text) <= self.FREE_LIMIT:
            return self._call(self._free_text, text)
        chunks, cur = [], ""
        for part in re.split(r"(?<=[.!?])\s+", text):
            while len(part) > self.FREE_LIMIT:
                chunks.append(part[:self.FREE_LIMIT])
                part = part[self.FREE_LIMIT:]
            if cur and len(cur) + len(part) + 1 > self.FREE_LIMIT:
                chunks.append(cur)
                cur = part
            else:
                cur = f"{cur} {part}" if cur else part
        if cur:
            chunks.append(cur)
        return " ".join(self._call(self._free_text, c) for c in chunks)

    def _free_batch(self, texts):
        """Много фраз — одним запросом (через перевод строки). Если строки склеились,
        делим пачку пополам, а не шлём каждую фразу отдельно."""
        if len(texts) == 1:
            return [self._free_long(texts[0])]
        out = self._call(self._free_text, "\n".join(texts)).split("\n")
        if len(out) == len(texts):
            return out
        mid = len(texts) // 2
        return self._free_batch(texts[:mid]) + self._free_batch(texts[mid:])

    def check(self):
        """Проверка: какие переводчики работают (для --check)."""
        sample = "Hello! She smiles at you."
        if self.engine in ("free", "google"):
            ok = 0

            def test(ep):
                try:
                    res = self._ep_call(ep, sample)
                    if not res or not res.strip():
                        raise ValueError("пустой ответ")
                    return ep, res
                except Exception as e:  # noqa: BLE001
                    return ep, e
            eps = self._pool()
            for ep, res in self._parallel(test, eps):
                name = self.ep_name(ep)
                if isinstance(res, str):
                    print(f"  {name:42} OK: {res}", file=sys.stderr)
                    ok += 1
                else:
                    kind = {"rate": "блокирует (слишком много запросов)", "quota": "отказ доступа"}.get(
                        classify_error(res), "не отвечает")
                    print(f"  {name:42} {kind}: {str(res)[:70]}", file=sys.stderr)
            print(f"Работает адресов: {ok} из {len(eps)}", file=sys.stderr)
            return ok > 0
        try:
            res = self.translate_batch([sample])[0]
            print(f"  {self.engine}: OK: {res}", file=sys.stderr)
            return True
        except Exception as e:  # noqa: BLE001
            print(f"  {self.engine}: ошибка: {str(e)[:200]}", file=sys.stderr)
            return False

    def _post(self, url, **kw):
        self._sleep(self.delay if self.delay != self.base_delay else 0)
        r = self._http().post(url, timeout=120, **kw)
        r.raise_for_status()
        return r.json()

    def _google_cloud_batch(self, texts):
        data = self._call(self._post, "https://translation.googleapis.com/language/translate/v2",
                          params={"key": self.key},
                          json={"q": texts, "source": self.src, "target": self.dst, "format": "text"})
        return [t["translatedText"] for t in data["data"]["translations"]]

    def _deepl_batch(self, texts):
        host = "api-free.deepl.com" if self.key.endswith(":fx") else "api.deepl.com"
        data = self._call(self._post, f"https://{host}/v2/translate",
                          headers={"Authorization": "DeepL-Auth-Key " + self.key},
                          json={"text": texts, "source_lang": self.src.upper(),
                                "target_lang": self.dst.upper()})
        return [t["text"] for t in data["translations"]]

    def _microsoft_batch(self, texts):
        headers = {"Ocp-Apim-Subscription-Key": self.key, "Content-Type": "application/json"}
        if self.region:
            headers["Ocp-Apim-Subscription-Region"] = self.region
        data = self._call(self._post, "https://api.cognitive.microsofttranslator.com/translate",
                          params={"api-version": "3.0", "from": self.src, "to": self.dst},
                          headers=headers, json=[{"Text": t} for t in texts])
        return [x["translations"][0]["text"] for x in data]

    def translate_batch(self, texts):
        return {"free": self._free_batch, "google": self._free_batch, "google-cloud": self._google_cloud_batch,
                "deepl": self._deepl_batch, "microsoft": self._microsoft_batch}[self.engine](texts)

    # --- пакетный перевод с прогрессом ---
    def _store(self, batch, results):
        """Сохраняет переводы; фразы, вернувшиеся без перевода, переводит заново по одной."""
        retry = []
        with self.lock:
            for src, res in zip(batch, results):
                if untranslated(src, res, self.dst) and len(batch) > 1:
                    retry.append(src)
                else:
                    self.cache[src] = res if res is not None else src
                    if untranslated(src, res, self.dst):
                        self.cache[SAME_MARK + src] = "1"
        for src in retry:
            res = self.translate_batch([src])[0]
            with self.lock:
                self.cache[src] = res
                if untranslated(src, res, self.dst):
                    self.cache[SAME_MARK + src] = "1"  # и по одной не переводится — значит так и есть
                self.retried = getattr(self, "retried", 0) + 1

    def _sleep(self, sec):
        """Пауза. В рабочих потоках её можно прервать (Ctrl+C или остановка) — поток сразу выходит."""
        if threading.current_thread() is threading.main_thread():
            time.sleep(sec)
        elif self.halt.wait(sec):
            raise Halted()

    def _prefetch_parallel(self, batches, total, started, quiet):
        """Быстрый режим: несколько пачек одновременно — каждая на свой рабочий адрес.
        Потоки «фоновые»: Ctrl+C останавливает скрипт сразу, без зависаний."""
        import queue
        tasks, results = queue.Queue(), queue.Queue()
        self.halt.clear()
        queued, reserved = 0, 0
        for b in batches:
            n = sum(len(x) for x in b)
            if self.max_chars and self.sent + reserved + n > self.max_chars:
                self.offline = True
                self.stop_reason = f"достигнут лимит этого запуска (--max-chars {self.max_chars:,} символов)"
                break
            tasks.put(b)
            queued, reserved = queued + 1, reserved + n

        def worker():
            while not self.halt.is_set():
                try:
                    b = tasks.get_nowait()
                except queue.Empty:
                    return
                try:
                    results.put((b, self.translate_batch(b), None))
                except BaseException as e:  # noqa: BLE001 — передаём ошибку в главный поток
                    results.put((b, None, e))
                    return

        threads = [threading.Thread(target=worker, daemon=True) for _ in range(self.workers)]
        for t in threads:
            t.start()
        done = got = 0
        try:
            while got < queued:
                try:
                    b, res, err = results.get(timeout=0.5)  # короткое ожидание — Ctrl+C срабатывает быстро
                except queue.Empty:
                    if not any(t.is_alive() for t in threads) and results.empty():
                        break
                    continue
                got += 1
                if err is not None:
                    if isinstance(err, Halted):
                        continue
                    raise err
                self._store(b, res)
                n = sum(len(x) for x in b)
                self.sent += n
                done += n
                self.save()
                if not quiet:
                    el = time.time() - started
                    eta = el / done * (total - done) if done else 0
                    print(f"\r  {done:,} / {total:,} симв. ({done / total:6.1%}), осталось ~{eta / 60:.0f} мин "
                          f"[{self.workers} потока]   ", end="", file=sys.stderr)
        except RateLimited:
            self.offline = True
            self.stop_reason = (f"переводчик блокирует запросы дольше {self.max_wait // 60} мин "
                                f"(слишком много запросов с вашего адреса)")
        except QuotaExceeded as e:
            self.offline = True
            self.stop_reason = f"лимит ключа исчерпан или ключ не подходит ({e})"
        finally:
            self.halt.set()  # остальные потоки заканчивают текущий запрос и выходят сами
            if not quiet:
                print(file=sys.stderr)
            self.save(force=True)

    def prefetch(self, strings, quiet=False):
        todo = [s for s in dict.fromkeys(strings) if not self.has(s)]
        if not todo or self.offline:
            return
        max_chars, max_items = self.LIMITS[self.engine]
        total, done, started = sum(len(s) for s in todo), 0, time.time()
        if not quiet:
            print(f"\r  0 / {total:,} симв. (  0.0%) — жду первый ответ переводчика...", end="",
                  file=sys.stderr)
        # Обычный текст — большими пачками; короткие фразы, где много кода, — маленькими
        # (бесплатный Google на них чаще ошибается, если их слишком много в одном запросе)
        groups = [(todo, max_chars, max_items)]
        if self.engine in ("free", "google"):
            simple = [s for s in todo if not complexity(s)]
            hard = [s for s in todo if complexity(s)]
            groups = [(simple, max_chars, max_items), (hard, 1200, 8)]
        batches = []
        for items, lim_c, lim_n in groups:
            batch, size = [], 0
            for s in items:
                if batch and (size + len(s) + 1 > lim_c or len(batch) >= lim_n):
                    batches.append(batch)
                    batch, size = [], 0
                batch.append(s)
                size += len(s) + 1
            if batch:
                batches.append(batch)
        if self.workers > 1 and len(batches) > 1:
            return self._prefetch_parallel(batches, total, started, quiet)
        try:
            for b in batches:
                n = sum(len(s) for s in b)
                if self.max_chars and self.sent + n > self.max_chars:
                    room, cut = self.max_chars - self.sent, []
                    for s in b:  # сколько строк ещё влезает в лимит
                        if len(s) > room:
                            break
                        cut.append(s)
                        room -= len(s)
                    self.offline = True
                    self.stop_reason = (f"достигнут лимит этого запуска (--max-chars {self.max_chars:,} "
                                        f"символов)")
                    if cut:
                        self._store(cut, self.translate_batch(cut))
                        self.sent += sum(len(s) for s in cut)
                    break
                self._store(b, self.translate_batch(b))
                self.sent += n
                done += n
                self.save()
                if not quiet:
                    el = time.time() - started
                    eta = el / done * (total - done) if done else 0
                    print(f"\r  {done:,} / {total:,} симв. ({done / total:6.1%}), "
                          f"осталось ~{eta / 60:.0f} мин   ", end="", file=sys.stderr)
        except RateLimited:
            self.offline = True
            self.stop_reason = (f"переводчик блокирует запросы дольше {self.max_wait // 60} мин "
                                f"(слишком много запросов с вашего адреса)")
        except QuotaExceeded as e:
            self.offline = True
            self.stop_reason = f"лимит ключа исчерпан или ключ не подходит ({e})"
        finally:
            if not quiet:
                print(file=sys.stderr)
            self.save(force=True)


# ===========================================================================
# Интерфейс SugarCube на русском (l10nStrings) — свои переводы
# ===========================================================================

L10N_RU = {
    # SugarCube 2.36 и старше
    "identity": "игра", "aborting": "Прерывание", "cancel": "Отмена", "close": "Закрыть",
    "ok": "ОК", "errorTitle": "Ошибка", "errorToggle": "Показать/скрыть подробности ошибки",
    "errorNonexistentPassage": "пассаж «{passage}» не существует",
    "errorSaveDiskLoadFailed": "не удалось загрузить сохранение с диска",
    "errorSaveMissingData": "в сохранении нет нужных данных: возможно, файл повреждён или выбран не тот файл",
    "errorSaveIdMismatch": "это сохранение от другой игры",
    "_warningIntroLacking": "Ваш браузер не поддерживает или отключил",
    "_warningOutroDegraded": ", поэтому игра работает в ограниченном режиме. Продолжать можно, но часть возможностей может не работать.",
    "warningNoWebStorage": "{_warningIntroLacking} Web Storage API{_warningOutroDegraded}",
    "warningDegraded": "{_warningIntroLacking} некоторые нужные игре возможности{_warningOutroDegraded}",
    "debugBarToggle": "Показать/скрыть панель отладки",
    "debugBarNoWatches": "— переменные не отслеживаются —",
    "debugBarAddWatch": "Добавить отслеживание", "debugBarDeleteWatch": "Удалить отслеживание",
    "debugBarWatchAll": "Отслеживать все", "debugBarWatchNone": "Удалить все",
    "debugBarLabelAdd": "Добавить", "debugBarLabelWatch": "Отслеживание",
    "debugBarLabelTurn": "Ход", "debugBarLabelViews": "Режимы",
    "debugBarViewsToggle": "Показать/скрыть режимы отладки",
    "debugBarWatchToggle": "Показать/скрыть панель отслеживания",
    "uiBarToggle": "Показать/скрыть боковую панель",
    "uiBarBackward": "Шаг назад по истории", "uiBarForward": "Шаг вперёд по истории",
    "uiBarJumpto": "Перейти к моменту в истории",
    "jumptoTitle": "Перейти к моменту", "jumptoTurn": "Ход",
    "jumptoUnavailable": "Сейчас нет моментов, к которым можно перейти…",
    "savesTitle": "Сохранения", "savesDisallowed": "Здесь сохраняться нельзя.",
    "savesIncapable": "{_warningIntroLacking} возможности, нужные для сохранений, поэтому в этой сессии они отключены.",
    "savesLabelAuto": "Автосохранение", "savesLabelDelete": "Удалить",
    "savesLabelExport": "Сохранить на диск…", "savesLabelImport": "Загрузить с диска…",
    "savesLabelLoad": "Загрузить", "savesLabelClear": "Удалить все", "savesLabelSave": "Сохранить",
    "savesLabelSlot": "Слот", "savesUnavailable": "Слоты сохранений не найдены…",
    "savesUnknownDate": "неизвестно", "settingsTitle": "Настройки", "settingsOff": "Выкл.",
    "settingsOn": "Вкл.", "settingsReset": "Сбросить по умолчанию", "restartTitle": "Начать заново",
    "restartPrompt": "Вы уверены, что хотите начать заново? Несохранённый прогресс будет потерян.",
    "shareTitle": "Поделиться", "alertTitle": "Внимание", "autoloadTitle": "Автозагрузка",
    "autoloadCancel": "Начать сначала", "autoloadOk": "Загрузить автосохранение",
    "autoloadPrompt": "Найдено автосохранение. Загрузить его или начать сначала?",
    "macroBackText": "Назад", "macroReturnText": "Вернуться",
    # SugarCube 2.37+
    "textAbort": "Прервать", "textAborting": "Прерывание", "textCancel": "Отмена",
    "textClear": "Очистить", "textClose": "Закрыть", "textDelete": "Удалить", "textExport": "Экспорт",
    "textIdentity": "игра", "textImport": "Импорт", "textLoad": "Загрузить", "textOff": "Выкл.",
    "textOk": "ОК", "textOn": "Вкл.", "textSave": "Сохранить", "textTurn": "Ход",
    "warningNoStorage": "Хранилище браузера недоступно: сохранения и настройки не будут запоминаться.",
    "warningNoSaves": "Сохранения в этой сессии отключены.",
    "saveErrorDisallowed": "сохранение сейчас запрещено",
    "saveErrorDecodeFail": "не удалось прочитать сохранение",
    "saveErrorDiskLoadFail": "не удалось загрузить сохранение с диска",
    "saveErrorIdMismatch": "это сохранение от другой игры",
    "saveErrorInvalidData": "в сохранении нет нужных данных или файл повреждён",
    "saveErrorLoadTooEarly": "игра ещё не готова загрузить сохранение",
    "saveErrorNonexistent": "сохранение не найдено",
    "uiBarLabelToggle": "Показать/скрыть боковую панель",
    "uiBarLabelBackward": "Шаг назад по истории", "uiBarLabelForward": "Шаг вперёд по истории",
    "uiBarLabelJumpto": "Перейти к моменту в истории",
    "restartMesgPrompt": "Вы уверены, что хотите начать заново? Несохранённый прогресс будет потерян.",
    "continueTitle": "Продолжить", "savesHeaderBrowser": "В браузере", "savesHeaderDisk": "На диске",
    "savesLabelBrowserClear": "Удалить все", "savesLabelBrowserExport": "Экспорт в файл…",
    "savesLabelBrowserImport": "Импорт из файла…", "savesLabelDiskLoad": "Загрузить с диска…",
    "savesLabelDiskSave": "Сохранить на диск…", "savesTextBrowserAuto": "Авто",
    "savesTextBrowserSlot": "Слот", "savesTextNoDate": "дата неизвестна",
    "settingsTextReset": "Сбросить по умолчанию", "errorViewTitle": "Ошибка",
    "errorViewLabelToggle": "Показать/скрыть подробности",
    "debugBarLabelToggle": "Показать/скрыть панель отладки",
    "debugBarLabelViewsToggle": "Показать/скрыть режимы отладки",
    "debugBarLabelWatchAdd": "Добавить отслеживание", "debugBarLabelWatchAll": "Отслеживать все",
    "debugBarLabelWatchClear": "Очистить список", "debugBarLabelWatchDelete": "Удалить отслеживание",
    "debugBarLabelWatchPlaceholder": "имя переменной", "debugBarLabelPassagePlaceholder": "имя пассажа",
    "debugBarLabelPassagePlay": "Перейти к пассажу",
    "debugBarLabelWatchToggle": "Показать/скрыть панель отслеживания",
    "debugBarMesgNoWatches": "Переменные не отслеживаются", "debugBarTextAdd": "Добавить",
    "debugBarTextPassage": "Пассаж", "debugBarTextViews": "Режимы", "debugBarTextWatch": "Отслеживание",
    "autoloadMesgPrompt": "Найдено автосохранение. Загрузить его или начать сначала?",
    "autoloadTextCancel": "Начать сначала", "autoloadTextOk": "Загрузить автосохранение",
    "jumptoMesgUnavailable": "Сейчас нет моментов, к которым можно перейти…",
}
OUT_PROPS.update(L10N_RU)
OUT_KEYS.update(L10N_RU)


def ui_strings(tr, dst, fetch=True):
    """Интерфейс SugarCube: русский — готовый, для других языков переводим его с русского.
    fetch=False — только то, что уже есть в кэше (без запросов)."""
    if dst.lower().startswith("ru"):
        return L10N_RU
    src_old, dst_old = tr.src, tr.dst
    out = {}
    try:
        tr.src = "ru"
        items = list(L10N_RU.items())
        local = []
        for k, v in items:
            phs = re.findall(r"\{\w+\}", v)
            t = v
            for i, ph in enumerate(phs):
                t = t.replace(ph, PH_OUT.format(i), 1)
            local.append((k, v, t, phs))
        need = ["\u0002ui:" + dst + "\u0002" + t for _, _, t, _ in local]
        missing = [(n, t) for n, (_, _, t, _) in zip(need, local) if n not in tr.cache]
        if missing and not tr.offline and fetch:
            res = []
            for i in range(0, len(missing), 40):
                chunk = [t for _, t in missing[i:i + 40]]
                res += tr.translate_batch(chunk)
            for (n, _), r in zip(missing, res):
                tr.cache[n] = r
            tr.save(force=True)
        for n, (k, v, t, phs) in zip(need, local):
            r = tr.cache.get(n)
            if not r:
                continue
            for i, ph in enumerate(phs):
                r = re.sub(r"[⟦\[]\s*" + str(i) + r"\s*[⟧\]]", ph, r)
            if "⟦" not in r:
                out[k] = r.strip()
    except Exception:  # noqa: BLE001
        print("  (интерфейс SugarCube перевести не удалось — останется английским)", file=sys.stderr)
    finally:
        tr.src, tr.dst = src_old, dst_old
    return out


LISP_JS = """/* ruIsLisp: шепелявит ли персонаж сейчас — спрашиваем сам виджет игры (<<s>> печатает "s" или "th"). */
window.ruIsLisp = function (name) {
	try {
		var t = jQuery("<span>").wiki("<<" + name + ">>").text();
		return t !== "" && t.toLowerCase() !== String(name).toLowerCase();
	} catch (e) { return false; }
};"""


COPULA_JS = r"""/* Страховка на экране: игра часто собирает фразу из кусков прямо во время игры («$name is» + слово
   из <<if>> или из JavaScript), и английская связка «is» может остаться: «Сара is предана».
   Здесь, уже на готовой странице, убираем отдельное «is/are/was/were», если слева и справа от него
   не английские слова (то есть фраза уже русская). Меняется только видимый текст — не код и не переменные. */
(function () {
	var LAT = /[A-Za-z]/, CYR = /[А-Яа-яЁёІіЇїЄєЎўҐґ]/;
	var RE = /(^|[^A-Za-z'’\u0400-\u04FF])(is|are|am|was|were)(?=$|[^A-Za-z'’\u0400-\u04FF])/g;
	var SKIP = { SCRIPT: 1, STYLE: 1, TEXTAREA: 1, INPUT: 1, CODE: 1, PRE: 1, SELECT: 1, OPTION: 1 };
	function nodesOf(root) {
		var out = [], w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null, false), n;
		while ((n = w.nextNode())) {
			var p = n.parentNode, bad = false;
			while (p && p !== root) { if (SKIP[p.nodeName]) { bad = true; break; } p = p.parentNode; }
			if (!bad) { out.push(n); }
		}
		return out;
	}
	function word(s, fromEnd) {
		var m = fromEnd ? s.match(/([^\s.,;:!?()"'«»“”„—–\-]+)[\s"'«»“”„]*$/) : s.match(/^[\s"'«»“”„]*([^\s.,;:!?()"'«»“”„—–\-]+)/);
		return m ? m[1] : "";
	}
	function clean(root) {
		if (!root || !document.createTreeWalker) { return; }
		var nodes = nodesOf(root), full = "", starts = [], lens = [], i;
		for (i = 0; i < nodes.length; i++) { starts.push(full.length); lens.push(nodes[i].nodeValue.length); full += nodes[i].nodeValue; }
		if (!/(?:^|[^A-Za-z])(?:is|are|am|was|were)(?:[^A-Za-z]|$)/.test(full)) { return; }
		var cuts = [], m;
		RE.lastIndex = 0;
		while ((m = RE.exec(full))) {
			var a = m.index + m[1].length, b = a + m[2].length;
			var pw = word(full.slice(Math.max(0, a - 60), a), true), nw = word(full.slice(b, b + 60), false);
			if (LAT.test(pw) || LAT.test(nw) || !(CYR.test(pw) || CYR.test(nw))) { continue; }
			if (full.charAt(b) === " ") { b++; } else if (a > 0 && full.charAt(a - 1) === " ") { a--; }
			cuts.push([a, b]);
			RE.lastIndex = Math.max(RE.lastIndex, b);
		}
		for (var k = cuts.length - 1; k >= 0; k--) {
			for (var j = 0; j < nodes.length; j++) {
				var s0 = starts[j], s1 = s0 + lens[j];
				if (s1 <= cuts[k][0] || s0 >= cuts[k][1]) { continue; }
				var v = nodes[j].nodeValue, x = Math.max(cuts[k][0], s0) - s0, y = Math.min(cuts[k][1], s1) - s0;
				nodes[j].nodeValue = v.slice(0, x) + v.slice(y);
			}
		}
	}
	window.ruCleanCopula = clean;
	var timer = null;
	function later() {
		if (timer) { return; }
		timer = setTimeout(function () {
			timer = null;
			["passages", "ui-dialog-body", "story-caption"].forEach(function (id) { clean(document.getElementById(id)); });
		}, 0);
	}
	try {
		if (typeof jQuery !== "undefined") {
			jQuery(document).on(":passagerender", function (ev) { clean(ev.content); });
			jQuery(document).on(":passagedisplay", later);
		}
		if (typeof MutationObserver !== "undefined") {
			var start = function () { new MutationObserver(later).observe(document.body, { childList: true, subtree: true }); };
			if (document.body) { start(); } else { document.addEventListener("DOMContentLoaded", start); }
		}
	} catch (e) { /* ничего страшного */ }
})();"""


RUV_JS = r"""/* ruV("$a.b"): переменная в тексте — как её показывает сам SugarCube ($a.b без <<print>>): нет такой
   переменной — печатается как есть, без ошибки; есть — значение через ruT. */
window.ruV = function (x) {
	var v;
	try {
		if (typeof State !== "undefined" && typeof State.getVar === "function") { v = State.getVar(x); }
		else if (typeof Wikifier !== "undefined" && typeof Wikifier.getValue === "function") { v = Wikifier.getValue(x); }
		else if (typeof Scripting !== "undefined" && typeof Scripting.evalTwineScript === "function") { v = Scripting.evalTwineScript(x); }
	} catch (e) { v = undefined; }
	return v === null || v === undefined ? x : window.ruT(v);
};"""


def prelude_js(gender, ui, values=None, ui_map=None, lisp=False, copula=False):
    parts = ["/* === Добавлено sugarcube_translate: перевод интерфейса и выбор рода === */"]
    if copula:
        parts.append(COPULA_JS)
    if lisp:
        parts.append(LISP_JS)
    if values:
        parts.append("/* ruT: показывает значения переменных (\"white\" и т.п.) переведёнными; сами значения\n"
                     "   в игре не меняются, поэтому логика игры не ломается. */\n"
                     "window.ruTMap = " + json.dumps(values, ensure_ascii=False, sort_keys=True) + ";\n"
                     "window.ruT = function (v) {\n"
                     "\treturn (typeof v === \"string\" && Object.prototype.hasOwnProperty.call(window.ruTMap, v))"
                     " ? window.ruTMap[v] : v;\n};\n" + RUV_JS)
    if ui:
        parts.append("(function () {\n\tif (typeof l10nStrings === \"undefined\") { return; }\n"
                     "\tvar ru = " + json.dumps(ui_map or L10N_RU, ensure_ascii=False, indent=1).replace("\n", "\n\t")
                     + ";\n\tObject.keys(ru).forEach(function (k) { l10nStrings[k] = ru[k]; });\n"
                     "\t/* в старых версиях меню уже построено к этому моменту — переименуем его */\n"
                     "\tvar fix = function () {\n"
                     "\t\tvar m = {\"menu-item-saves\": \"savesTitle\", \"menu-item-settings\": \"settingsTitle\", "
                     "\"menu-item-restart\": \"restartTitle\", \"menu-item-share\": \"shareTitle\"};\n"
                     "\t\tObject.keys(m).forEach(function (id) {\n"
                     "\t\t\tvar a = document.querySelector(\"#\" + id + \" a\");\n"
                     "\t\t\tif (a) { a.textContent = ru[m[id]]; }\n"
                     "\t\t});\n\t};\n"
                     "\ttry { fix(); if (typeof jQuery !== \"undefined\") { jQuery(document).one(\":passagestart\", fix); } } "
                     "catch (e) { /* ничего страшного */ }\n})();")
    if gender:
        parts.append(ru_gender_helper().rstrip("\n"))
    parts.append("/* === конец добавленного === */")
    return "\n".join(parts) + "\n"


# ===========================================================================
# Чтение и запись игр: .twee/.tw, .html (Twine 2 и Twine 1), папка с исходниками
# ===========================================================================

HEADER = re.compile(r"^::\s*(?P<name>(?:\\.|[^\\\[{])*?)\s*"
                    r"(?:\[(?P<tags>(?:\\.|[^\]\\])*)\])?\s*(?P<meta>\{.*\})?\s*$")


def read_text(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        raw = f.read()
    return raw.replace("\r\n", "\n"), "\r\n" in raw


def write_text(path, text, crlf=False):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text.replace("\n", "\r\n") if crlf else text)
    os.replace(tmp, path)  # файл не останется недописанным, если прервать запись


class TweeFile:
    """Файл .twee / .tw (Twee 1 и Twee 3)."""

    def __init__(self, path, rel=None):
        self.path, self.rel = path, rel
        self.text, self.crlf = read_text(path)
        self.preamble, self.passages, cur = [], [], None
        for line in self.text.split("\n"):
            if line.startswith("::"):
                m = HEADER.match(line)
                name = re.sub(r"\\(.)", r"\1", m.group("name").strip()) if m else line[2:].strip()
                tags = set((m.group("tags") or "").split()) if m else set()
                cur = {"header": line, "name": name, "tags": tags, "lines": []}
                self.passages.append(cur)
            elif cur is None:
                self.preamble.append(line)
            else:
                cur["lines"].append(line)
        for p in self.passages:
            p["body"] = "\n".join(p["lines"])

    def format(self):
        for p in self.passages:
            if p["name"] == "StoryData":
                try:
                    return json.loads(p["body"]).get("format")
                except ValueError:
                    return None
        return None

    def inject(self, js):
        for p in self.passages:
            if "script" in p["tags"]:
                p["new"] = js + "\n" + p.get("new", p["body"])
                return True
        self.passages.append({"header": ":: Перевод (добавлено) [script]", "name": "_ru", "tags": {"script"},
                              "body": "", "new": js, "added": True})
        return True

    def reset(self):
        self.passages = [p for p in self.passages if not p.get("added")]
        for p in self.passages:
            p.pop("new", None)

    def render(self):
        out = list(self.preamble)
        for p in self.passages:
            out.append(p["header"])
            out.extend(p.get("new", p["body"]).split("\n"))
        return "\n".join(out)

    def save(self, path):
        write_text(path, self.render(), self.crlf)


class HtmlFile:
    """Собранная игра .html: Twine 2 (<tw-passagedata>) или Twine 1 (store-area)."""
    TW2_P = re.compile(r"<tw-passagedata\b([^>]*)>([\s\S]*?)</tw-passagedata>")
    TW2_JS = re.compile(r"(<script\b[^>]*type=[\"']text/twine-javascript[\"'][^>]*>)([\s\S]*?)(</script>)")
    TW2_CSS = re.compile(r"(<style\b[^>]*type=[\"']text/twine-css[\"'][^>]*>)([\s\S]*?)(</style>)")
    TW1_P = re.compile(r"<div\b([^>]*\btiddler=[\"'][^>]*)>([\s\S]*?)</div>")
    ATTR = re.compile(r"([\w-]+)\s*=\s*(\"[^\"]*\"|'[^']*')")

    def __init__(self, path):
        import html as htmlmod
        self.h = htmlmod
        self.path, self.rel = path, None
        self.text, self.crlf = read_text(path)
        self.passages = []
        t = self.text
        if "<tw-storydata" in t:
            self.kind = "tw2"
            sd = re.search(r"<tw-storydata\b([^>]*)>", t)
            self.attrs = self._attrs(sd.group(1))
            m = self.TW2_CSS.search(t)
            if m:
                self.passages.append({"name": "Story Stylesheet", "tags": {"stylesheet"}, "body": m.group(2),
                                      "span": m.span(2), "esc": "raw"})
            m = self.TW2_JS.search(t)
            if m:
                self.passages.append({"name": "Story JavaScript", "tags": {"script"}, "body": m.group(2),
                                      "span": m.span(2), "esc": "raw"})
            for m in self.TW2_P.finditer(t):
                a = self._attrs(m.group(1))
                self.passages.append({"name": a.get("name", ""), "tags": set(a.get("tags", "").split()),
                                      "body": self.h.unescape(m.group(2)), "span": m.span(2), "esc": "tw2"})
        elif re.search(r"id=[\"']store-area[\"']", t):
            self.kind = "tw1"
            self.attrs = {}
            sa = re.search(r"<div\b[^>]*id=[\"']store-area[\"'][^>]*>", t)
            self.store_start = sa.end()
            for m in self.TW1_P.finditer(t, sa.end()):
                a = self._attrs(m.group(1))
                body = self._tw1_unescape(self.h.unescape(m.group(2)))
                self.passages.append({"name": a.get("tiddler", ""), "tags": set(a.get("tags", "").split()),
                                      "body": body, "span": m.span(2), "esc": "tw1"})
        else:
            raise SystemExit("Не похоже на игру Twine: в HTML нет <tw-storydata> и store-area. "
                             "Возможно, файл зашифрован или собран не в Twine.")
        self.extra = None

    def _attrs(self, s):
        return {k: self.h.unescape(v[1:-1]) for k, v in self.ATTR.findall(s)}

    @staticmethod
    def _tw1_unescape(s):
        return re.sub(r"\\[nts]|\\", lambda m: {"\\n": "\n", "\\t": "\t", "\\s": "\\"}.get(m.group(), "\\"), s)

    def _escape(self, body, esc):
        if esc == "raw":
            return body
        if esc == "tw1":
            body = body.replace("\\", "\\s").replace("\n", "\\n").replace("\t", "\\t")
        return (body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    .replace('"', "&quot;").replace("'", "&#39;"))

    def format(self):
        if self.kind == "tw2":
            return self.attrs.get("format")
        return "SugarCube" if re.search(r"SugarCube", self.text[:200000]) else None

    def inject(self, js):
        for p in self.passages:
            if "script" in p["tags"] and "span" in p:
                p["new"] = js + "\n" + p.get("new", p["body"])
                return True
        if self.kind == "tw1":
            self.extra = ('<div tiddler="_ru" tags="script" modifier="sugarcube_translate">'
                          + self._escape(js, "tw1") + "</div>")
            return True
        return False

    def reset(self):
        self.extra = None
        for p in self.passages:
            p.pop("new", None)

    def render(self):
        t, out, pos = self.text, [], 0
        edits = sorted((p["span"], self._escape(p["new"], p["esc"])) for p in self.passages
                       if "span" in p and "new" in p and p["new"] != p["body"])
        for (a, b), rep in edits:
            out += [t[pos:a], rep]
            pos = b
        out.append(t[pos:])
        res = "".join(out)
        if self.extra:
            sa = re.search(r"<div\b[^>]*id=[\"']store-area[\"'][^>]*>", res)
            res = res[:sa.end()] + self.extra + res[sa.end():]
        return res

    LIB_RE = re.compile(r"(jquery|lodash|underscore|moment|bootstrap|howler|pixi|three|\bd3\b|chart|react|vue|"
                        r"gsap|anime|popper|swiper|sugarcube|localforage|crypto|seedrandom|marked|math|tween|"
                        r"polyfill|webfont|fontawesome|\.min\.)", re.I)

    def attach_external(self):
        """Файлы .js, которые игра подключает (<script src>, importScripts) — их текст тоже переводим."""
        base = os.path.dirname(os.path.abspath(self.path))
        refs = re.findall(r"<script\b[^>]*\bsrc\s*=\s*[\"']([^\"']+)[\"']", self.text)
        for p in self.passages:
            if "script" in p["tags"]:
                for m in re.finditer(r"importScripts\s*\(([^)]*)\)", p["body"]):
                    refs += re.findall(r"[\"']([^\"']+\.js(?:\?[^\"']*)?)[\"']", m.group(1))
        self.external, seen = [], set()
        for ref in refs:
            if re.match(r"^(?:[a-z]+:)?//|^data:", ref, re.I) or ref in seen:
                continue
            seen.add(ref)
            full = os.path.normpath(os.path.join(base, ref.split("?")[0].split("#")[0]))
            if not os.path.isfile(full) or not full.lower().endswith(".js"):
                continue
            info = {"ref": ref, "path": full, "status": ""}
            self.external.append(info)
            if self.LIB_RE.search(os.path.basename(full)):
                info["status"] = "библиотека — пропускаю"
                continue
            text, crlf = read_text(full)
            lines = text.count("\n") + 1
            if len(text) > 8_000_000 or len(text) / lines > 400:
                info["status"] = "сжатый/огромный файл — пропускаю"
                continue
            info["status"] = "переводится"
            self.passages.append({"name": ref, "tags": {"script"}, "body": text, "ext": info, "crlf": crlf})

    def save(self, path):
        res = self.render()
        stem = os.path.splitext(os.path.basename(self.path))[0]
        out_stem = os.path.splitext(os.path.basename(path))[0]
        suffix = out_stem[len(stem):] if out_stem.startswith(stem) and out_stem != stem else "_ru"
        for p in self.passages:
            if "ext" in p and "new" in p and p["new"] != p["body"]:
                ref = p["ext"]["ref"]
                head, sep, query = ref.partition("?")
                new_ref = head[:-3] + suffix + ".js" + (sep + query)
                write_text(os.path.join(os.path.dirname(p["ext"]["path"]),
                                        os.path.basename(head[:-3] + suffix + ".js")), p["new"], p["crlf"])
                for q in "\"'":
                    res = res.replace(q + ref + q, q + new_ref + q)
        write_text(path, res, self.crlf)


class SourceDir:
    """Папка с исходниками (проект Tweego): .tw/.twee, .js, .css."""

    def __init__(self, path):
        self.path, self.files, self.passages = path, [], []
        for root, dirs, files in os.walk(path):
            dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d != "node_modules")
            for fn in sorted(files):
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, path)
                ext = os.path.splitext(fn)[1].lower()
                if ext in (".tw", ".twee", ".tw2", ".tw3"):
                    tf = TweeFile(full, rel)
                    self.files.append(tf)
                    self.passages += tf.passages
                elif ext in (".js", ".css"):
                    text, crlf = read_text(full)
                    p = {"name": rel, "tags": {"script" if ext == ".js" else "stylesheet"}, "body": text,
                         "rel": rel, "crlf": crlf}
                    self.files.append(p)
                    self.passages.append(p)
        self.added = None

    def format(self):
        for f in self.files:
            if isinstance(f, TweeFile) and f.format():
                return f.format()
        return None

    def inject(self, js):
        self.added = js
        return True

    def reset(self):
        self.added = None
        for p in self.passages:
            p.pop("new", None)

    def save(self, out):
        if os.path.abspath(out) != os.path.abspath(self.path):
            shutil.copytree(self.path, out, dirs_exist_ok=True,
                            ignore=lambda d, names: [n for n in names if os.path.join(d, n) == os.path.abspath(out)])
        for f in self.files:
            if isinstance(f, TweeFile):
                if any("new" in p for p in f.passages):
                    write_text(os.path.join(out, f.rel), f.render(), f.crlf)
            elif "new" in f:
                write_text(os.path.join(out, f["rel"]), f["new"], f["crlf"])
        if self.added:
            write_text(os.path.join(out, "_ru_prelude.js"), self.added)


class WebApp:
    """Игра на HTML/JavaScript, но не Twine (например, Lilith's Throne CE): текст собирает код игры,
    поэтому для неё — только перевод на лету (-l / --live, -c / --console-live): переводится то, что на экране."""

    def __init__(self, path):
        self.path = path
        self.text, self.crlf = read_text(path)
        self.passages = []
        self.kind = "web"

    def format(self):
        return "web"

    def inject(self, js):
        return False

    def reset(self):
        pass

    def render(self):
        return self.text


# Где в игре текст, что не трогать и что прятать, пока не придёт перевод (селекторы CSS)
WEB_PROFILES = (
    {"name": "Lilith's Throne (HTML)",
     "test": lambda t: 'id="ui-stage"' in t and 'id="response-grid"' in t,
     "roots": "#app, #tooltip", "noSel": ".hotkey-icon, #grid, .map-container",
     "waitSel": "#ui-stage, #content-title, #responses"},
    {"name": "Harlowe", "test": lambda t: "<tw-story" in t or 'format="Harlowe"' in t,
     "roots": "tw-story", "noSel": "tw-sidebar", "waitSel": "tw-passage"},
    {"name": "Snowman / Chapbook", "test": lambda t: 'format="Snowman"' in t or 'format="Chapbook"' in t,
     "roots": "body", "noSel": "", "waitSel": ""},
)


def web_profile(text):
    for prof in WEB_PROFILES:
        if prof["test"](text):
            return prof
    return {"name": "HTML", "roots": "body", "noSel": "", "waitSel": ""}


def looks_web(path):
    """Игра на HTML/JavaScript, но не Twine (для неё — только перевод на лету)."""
    if not path or not os.path.exists(path):
        return False
    if os.path.isdir(path):
        idx = os.path.join(path, "index.html")
        return os.path.isfile(idx) and not is_twine_html(idx) and not find_game_html(path)
    return path.lower().endswith((".html", ".htm")) and not is_twine_html(path)


def is_twine_html(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            head = f.read()
    except OSError:
        return False
    return "<tw-storydata" in head or bool(re.search(r"id=[\"']store-area[\"']", head))


OUT_HTML = re.compile(r"_[a-z]{2,3}(?:-[A-Za-z]{2,4})?_(safe|full)\.html?$|_live\.html?$", re.I)  # наши результаты
OUT_DIR = re.compile(r"_[a-z]{2,3}(?:-[A-Za-z]{2,4})?_(safe|full)$")


def html_candidates(folder):
    """Файлы игры в папке: ([.html с игрой Twine — в папке и глубже], [прочие .html в самой папке], есть ли .twee).
    Наши же результаты (_ru_safe.html, _live.html) не считаются."""
    twine, plain, sources = [], [], False
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules" and not OUT_DIR.search(d)]
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext in (".tw", ".twee", ".tw2", ".tw3"):
                sources = True
            if ext in (".html", ".htm") and not OUT_HTML.search(fn):
                full = os.path.join(root, fn)
                if is_twine_html(full):
                    twine.append(full)
                elif os.path.normpath(root) == os.path.normpath(folder):
                    plain.append(full)
    return twine, plain, sources


def _main_first(folder, files):
    """Сначала — файлы в самой папке, потом новее: по номеру версии в имени («Game 0.9.8.html»), index.html,
    по дате, по размеру."""
    def key(f):
        try:
            st = os.stat(f)
            mt, size = st.st_mtime, st.st_size
        except OSError:
            mt = size = 0
        name = os.path.basename(f)
        return (os.path.normpath(os.path.dirname(f)) == os.path.normpath(folder),
                tuple(int(x) for x in re.findall(r"\d+", name)[:6]), name.lower() == "index.html", mt, size)
    return sorted(files, key=key, reverse=True)


def resolve_input(path):
    """Указана папка игры на HTML — находим главный файл сам: единственный .html с игрой или index.html.
    Если их несколько (например, разные версии игры) — спрашиваем, какой переводить (Enter — самый новый)."""
    if not path or not os.path.isdir(path):
        return path
    try:
        if detect_engine(path)[0]:
            return path  # Ren'Py / Godot — своя обработка
    except SystemExit:
        return path
    twine, plain, sources = html_candidates(path)
    try:
        top_src = any(n.lower().endswith((".tw", ".twee", ".tw2", ".tw3")) for n in os.listdir(path))
    except OSError:
        top_src = False
    if top_src or (sources and not twine):
        return path  # исходники Tweego (собранной игры рядом нет)
    if sources:  # проект Tweego с собранными версиями игры (как SummerGrowth): берём собранную
        print("Здесь есть исходники Tweego, но и собранная игра — перевожу собранную (.html).", file=sys.stderr)
    if twine:
        cands = _main_first(path, twine)
    elif plain:
        cands = _main_first(path, plain)
        if os.path.basename(cands[0]).lower() == "index.html":
            cands = cands[:1]  # игра на HTML/JavaScript: index.html, остальные .html — её страницы
    else:
        return path
    if len(cands) == 1:
        print(f"Файл игры: {cands[0]}", file=sys.stderr)
        return cands[0]
    shown = cands[:20]
    print("В папке несколько файлов игры:", file=sys.stderr)
    for i, f in enumerate(shown, 1):
        try:
            st = os.stat(f)
            info = f"{st.st_size / 1048576:.1f} МБ, {time.strftime('%Y-%m-%d', time.localtime(st.st_mtime))}"
        except OSError:
            info = "?"
        print(f"  {i}) {os.path.relpath(f, path)}   ({info})", file=sys.stderr)
    n = 1
    if sys.stdin.isatty():
        while True:
            ans = ask("Какой переводить? Номер, Enter — 1, exit — выйти: ").strip()
            if not ans:
                break
            if ans.isdigit() and 1 <= int(ans) <= len(shown):
                n = int(ans)
                break
            print(f"Введите номер от 1 до {len(shown)}.", file=sys.stderr)
    else:
        print("Беру первый. Другой можно указать сразу: python sugarcube_translate.py \"путь/к/файлу.html\"",
              file=sys.stderr)
    print(f"Файл игры: {shown[n - 1]}", file=sys.stderr)
    return shown[n - 1]


def find_game_html(folder):
    """Папка с готовой игрой: ищем .html со встроенной игрой Twine (картинки и звуки рядом не трогаем)."""
    found, sources = [], False
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"
                   and not re.search(r"_[a-z]{2,3}(?:-[A-Za-z]{2,4})?_(safe|full)$", d)]
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext in (".tw", ".twee", ".tw2", ".tw3"):
                sources = True
            if ext in (".html", ".htm") and not OUT_HTML.search(fn):
                full = os.path.join(root, fn)
                try:
                    with open(full, encoding="utf-8", errors="replace") as f:
                        head = f.read()
                except OSError:
                    continue
                if "<tw-storydata" in head or re.search(r"id=[\"']store-area[\"']", head):
                    found.append(full)
    if sources or not found:
        return None
    found.sort(key=lambda f: (os.path.dirname(f) != folder, os.path.basename(f).lower() != "index.html",
                              -os.path.getsize(f)))
    if len(found) > 1:
        print("Нашёл несколько файлов игры, беру первый:\n  " + "\n  ".join(found)
              + "\nДругой можно указать напрямую: python sugarcube_translate.py \"путь\\к\\файлу.html\"",
              file=sys.stderr)
    return found[0]


def open_game(path):
    if os.path.isdir(path):
        html_game = find_game_html(path)
        idx = os.path.join(path, "index.html")
        if not html_game and os.path.isfile(idx) and not is_twine_html(idx) and not any(
                f.lower().endswith((".tw", ".twee", ".tw2", ".tw3")) for f in os.listdir(path)):
            print(f"Это игра на HTML/JavaScript (не Twine): {idx}", file=sys.stderr)
            return WebApp(idx)
        if html_game:
            print(f"Это папка с готовой игрой. Перевожу файл: {html_game}\n"
                  f"(картинки, звуки и остальные папки остаются как есть — переведённые .html "
                  f"появятся рядом с ним и будут их видеть)", file=sys.stderr)
            h = HtmlFile(html_game)
            h.attach_external()
            return h
        return SourceDir(path)
    ext = os.path.splitext(path)[1].lower()
    if ext in (".html", ".htm") and not is_twine_html(path):
        return WebApp(path)
    if ext in (".html", ".htm"):
        h = HtmlFile(path)
        h.attach_external()
        return h
    return TweeFile(path)


def output_paths(path, base=None, lang="ru"):
    """game.html -> game_ru_safe.html и game_ru_full.html (папка -> папка_ru_safe / папка_ru_full)."""
    tag = "_" + lang.lower()
    p = (base or path).rstrip("/\\")
    if os.path.isdir(path):
        stem, ext = (p if base else p + tag), ""
    else:
        stem, ext = os.path.splitext(p)
        if not base:
            stem += tag
        elif not ext:
            ext = os.path.splitext(path)[1]  # расширение как у исходной игры
    return {"safe": f"{stem}_safe{ext}", "full": f"{stem}_full{ext}"}


# ===========================================================================
# Подготовка: имена пассажей, CSS-классы, переменные-местоимения
# ===========================================================================

PRON_WORDS = "he|she|him|her|his|hers|himself|herself"
PRON_ASSIGN = re.compile(
    r"(?<![\w$])([$_]?[A-Za-z_][\w$]*)\s*(?:=(?![=>])|\bto\b|:)\s*"
    r"(?:[^;\n{}\"'`]{0,80}\?\s*)?([\"'])(" + PRON_WORDS + r")\2"
    r"(?:\s*:\s*([\"'])(" + PRON_WORDS + r")\4)?", re.I)


def harvest(passages):
    found = {}
    scan_macro_roles(passages)
    allbody = [p["body"] for p in passages if "script" not in p["tags"]]
    n_endif = sum(b.count("<<endif>>") for b in allbody)
    n_close = sum(b.count("<</if>>") for b in allbody)
    STYLE["endif"] = n_endif > 0 and n_close == 0
    for p in passages:
        PASSAGES.add(p["name"])
        body = p["body"]
        if "stylesheet" in p["tags"]:
            css = re.sub(r"url\([^)]*\)", "", body)
            CSS.update(re.findall(r"(?<![\w-])[.#](-?[A-Za-z_][\w-]*)", css))
            continue
        for m in re.finditer(r"\b(?:class|id)\s*=\s*([\"'])([^\"'<>]*)\1", body):
            CSS.update(m.group(2).split())
        for m in re.finditer(r"@@((?:[.#][\w-]+)+);", body):
            CSS.update(re.findall(r"[.#]([\w-]+)", m.group(1)))
        if OPTS.gender:
            for m in PRON_ASSIGN.finditer(body):
                name = m.group(1).lstrip("$_")
                found.setdefault(name, []).extend(v for v in (m.group(3), m.group(5)) if v)
    # переменные, в которые игра кладёт местоимения, — тоже переменные рода
    for name, vals in found.items():
        base = re.sub(r"\d+$", "", name)
        if not base or base in GENDER:
            continue
        low = {v.lower() for v in vals}
        if low & {"he", "she"}:
            pair = ("he", "she")
        elif low & {"himself", "herself"}:
            pair = ("himself", "herself")
        elif "his" in low and "hers" in low:
            pair = ("his", "hers")
        elif "his" in low:
            pair = ("his", "her")
        elif "him" in low:
            pair = ("him", "her")
        else:
            continue
        if any(v[:1].isupper() for v in vals):
            pair = (pair[0].capitalize(), pair[1].capitalize())
        GENDER[base] = pair


def build_markup(body):
    marked = protect(body, values=True)
    parts = []
    for n, line in enumerate(marked.split("\n")):
        if n:
            parts.append("\n")
        parts.extend(build_units(line, markup=True))
        group_labels(line)
    return Seq(parts, kind="body")


def first_str(seq):
    for x in getattr(seq, "p", []):
        if isinstance(x, Str):
            return x
        if isinstance(x, Seq):
            r = first_str(x)
            if r is not None:
                return r
    return None


def label_text_of(it):
    """Text подписи ссылки/кнопки ([[Текст|P]], <<link "Текст">>) или None."""
    t = None
    if isinstance(it, Label):
        t = it.text
    elif isinstance(it, Seq) and getattr(it, "mname", "") in LABEL_MACROS:
        st = first_str(it)
        if st is not None and st.ctx == "label" and isinstance(st.text, MultiText) and st.text.single:
            t = st.text.texts[0]
    if t is None or MARK.search(t.core) or "|" in t.core or not LATIN.search(t.core):
        return None
    return t


SEP_ONLY = re.compile(r"^[\s|/\\,;·•\-–—()\[\]]*$")


def hard_item(it):
    return ctx_kind(it) == "hard" and not isinstance(it, (Label,)) and getattr(it, "mname", "") not in LABEL_MACROS


def group_labels(line):
    """Подписи ссылок в одной строке через « | » — одна группа: переводятся вместе с началом строки."""
    toks = MARK_SPLIT.split(line)
    labels = []
    for i, tok in enumerate(toks):
        m = MARK.fullmatch(tok)
        if m:
            t = label_text_of(ITEMS[int(m.group(1))])
            if t is not None:
                labels.append((i, t))
    if not labels:
        return

    def between_ok(a, b):
        for tok in toks[a + 1:b]:
            m = MARK.fullmatch(tok)
            if m:
                it = ITEMS[int(m.group(1))]
                if getattr(it, "kind", "") == "nl" or (getattr(it, "kind", "") == "tag" and hard_item(it)):
                    return False
                continue  # <<set>>, <<goto>>, <</link>> между подписями — это код, не мешает
            if not SEP_ONLY.match(tok):
                return False
        return True

    def prefix(idx):
        out = []
        for tok in toks[:idx]:
            m = MARK.fullmatch(tok)
            if not m:
                out.append(tok)
                continue
            it = ITEMS[int(m.group(1))]
            lt = label_text_of(it)
            if lt is not None:
                out.append(" " + lt.core + " ")
            elif getattr(it, "kind", "") in ("nl",) or (getattr(it, "kind", "") == "tag" and hard_item(it)):
                out = []
            else:
                out.append(" ")
        return tidy_hint(strip_markup("".join(out)), True)

    runs, cur = [], [labels[0]]
    for prev, nxt in zip(labels, labels[1:]):
        if between_ok(prev[0], nxt[0]):
            cur.append(nxt)
        else:
            runs.append(cur)
            cur = [nxt]
    runs.append(cur)
    for run in runs:
        hint = prefix(run[0][0])
        texts = [t for _, t in run]
        if len(texts) >= 2 and all(t.short() for t in texts) and len(texts) <= 30:
            g = LabelGroup(texts, hint)
            for k, t in enumerate(texts):
                t.lgroup = (g, k)
        elif hint:
            for t in texts:
                if t.short():
                    t.label_hint = hint


# ===========================================================================
# Главная программа
# ===========================================================================

def unit_value(u):
    """Значение строки JS для проверки согласованности (None — не участвует)."""
    if getattr(u, "claimed", False) or u.text is None or u.ctx == "label":
        return None
    if isinstance(u, Str) and u.val is not None:
        return u.val.strip().lower()
    if isinstance(u, Tmpl) and not any(k == "expr" for k, _ in u.items) and u.check:
        return u.check.strip().lower()
    return None


TAG_ONLY = set("div span br img input p a b i u s hr td tr th li ul ol".split())
HINT_SKIP = set("type value name names id key text desc label result title list item items data tmp temp "
                "str string arr array obj object val res out output msg message entry option opt".split())


def value_hint(v):
    """Подсказка для перевода короткого значения: "sub" → "fetish: sub" (а не «подписка»),
    "perky" → "breast shape: perky" («упругая», а не «весёлый»)."""
    if len(v.split()) > 4:
        return None
    props = VALUE_PROPS.get(v)
    if not props:
        return None
    w = prop_words(max(props, key=props.get))
    return f"{w}: {v}" if w else None


def hint_result(res):
    """Из «фетиш: саб» берём «саб»; None — если переводчик не сохранил двоеточие."""
    if not res:
        return None
    m = re.match(r"^[^:：]{1,40}[:：]\s*(.+)$", res.strip())
    return m.group(1).strip() if m else None


def value_candidate(v):
    """Значение-данные, которое игра может показать игроку ("white", "a nun", "Continue",
    или целая фраза вроде происхождения рабыни, с которой игра где-то сравнивает)."""
    s = v.strip()
    if s != v or not s or len(re.findall(r"[A-Za-z]", s)) < 2:
        return False
    if len(s) > 40 or len(s.split()) > 4:  # длинная фраза
        return len(s) <= 400 and not re.search(r"[<>\[\]{}$@|=\\/_#`]", s) and not looks_code(s)
    if re.search(r"[<>\[\]{}$@|=\\/_#;:0-9]", s) or (looks_code(s) and not NAMEISH.fullmatch(s)):
        return False
    low = s.lower()
    if low in GENDER_WORDS or low in TAG_ONLY or low in CSS_UNITS or re.fullmatch(r"[A-Z0-9_-]{1,6}", s):
        return False  # ("sub" — и тег, и фетиш: для показа на экране его переводить можно)
    if re.fullmatch(r"[a-z]+[A-Z]\w*|[A-Z][a-z]+[A-Z]\w*", s) and " " not in s and not NAMEISH.fullmatch(s):
        return False  # camelCase: dickShrink (но не McGrath)
    return True


def write_skipped(path, mode):
    """Список строк JS с буквами, которые НЕ переведены, и почему (чтобы можно было добавить вручную)."""
    rows = set()
    for u in JSUNITS:
        if u.active or getattr(u, "claimed", False) or isinstance(u, Chain) or u.text is None:
            continue
        val = u.val if isinstance(u, Str) else u.check
        if not val or len(re.findall(r"[A-Za-z]", val)) < 2:
            continue
        reason = u.reasons.get(mode, "") or "текст только внутри кода/разметки"
        rows.add((reason, u.passage, val.replace("\t", " ").replace("\n", "\\n")))
    with open(path, "w", encoding="utf-8") as f:
        f.write("причина\tпассаж\tстрока (можно скопировать в файл для --translate-list)\n")
        for r in sorted(rows):
            f.write("\t".join(r) + "\n")
    return len(rows)


def fix_lines(new, chk, orig, names):
    """Пассаж не прошёл проверку — оставляем на английском только «плохие» строки, а не весь пассаж."""
    nl, cl, ol = new.split("\n"), chk.split("\n"), orig.split("\n")
    if not (len(nl) == len(cl) == len(ol)):
        return None, 0
    out, out_chk, bad = [], [], 0
    for a, c, o in zip(nl, cl, ol):
        if macro_balance(c, names) != macro_balance(o, names) or M_OPEN in a or M_CLOSE in a:
            out.append(o)
            out_chk.append(o)
            bad += 1
        else:
            out.append(a)
            out_chk.append(c)
    fixed_chk = "\n".join(out_chk)
    names2 = containers(fixed_chk, orig)
    if macro_balance(fixed_chk, names2) != macro_balance(orig, names2):
        return None, 0  # разбалансировка через несколько строк — тогда весь пассаж остаётся как был
    return "\n".join(out), bad


def render_checked(p, have_node=False):
    """Собирает пассаж и проверяет, что код не сломан. Возвращает (ок, новый текст, причина)."""
    orig = p["body"]
    why = ""
    try:
        new = expand(p["seq"].render())
        # для проверки баланса берём вариант без развилок «он/она»: в развилке одна и та же ссылка
        # повторяется в каждой ветке, но в игре показывается только одна ветка
        STYLE["neutral"] = True
        try:
            chk = expand(p["seq"].render())
        finally:
            STYLE["neutral"] = False
        if M_OPEN in new or M_CLOSE in new:
            why = "остались служебные метки"
        elif "⟦" in new and "⟦" not in orig:
            why = "остались метки ⟦n⟧"
        elif p["mode"] == "markup":
            names = containers(chk, orig)
            b_new, b_old = macro_balance(chk, names), macro_balance(orig, names)
            if b_new != b_old:
                fixed, n_bad = fix_lines(new, chk, orig, names)
                if fixed is not None:
                    p["lines_kept"] = n_bad
                    return True, fixed, ""
                diff = [f"{k}: {b_old[0].get(k, 0):+d}→{b_new[0].get(k, 0):+d}"
                        for k in sorted(set(b_new[0]) | set(b_old[0])) if b_new[0].get(k) != b_old[0].get(k)]
                if b_new[1:] != b_old[1:]:
                    diff.append(f"[[ {b_old[1]}→{b_new[1]}, ]] {b_old[2]}→{b_new[2]}")
                why = "баланс макросов/ссылок: " + "; ".join(diff)
            else:
                for m in re.finditer(r"<<script\b[^>]*>>([\s\S]*?)<</script>>", new):
                    if not js_ok(m.group(1)):
                        why = "сломан JavaScript внутри <<script>>"
                        break
        else:
            if not js_ok(new) and js_ok(orig):
                why = "сломан JavaScript (скобки/кавычки)"
            elif have_node and new != orig and node_check(new) is False and node_check(orig) is not False:
                why = "сломан JavaScript (проверка node)"
    except RecursionError:
        why, new = "слишком глубокая вложенность", orig
    return not why, new, why


def set_mode(mode):
    """Включает решения выбранного режима для всех строк JS."""
    for u in JSUNITS:
        u.active = u.modes.get(mode, False)
        if isinstance(u, Chain):
            u.merged = u.active
        if u.text is not None:
            u.text.active = u.active


def write_report(path, mode, reverted, kept=()):
    clean = lambda s: s.replace("\t", " ").replace("\r", " ").replace("\n", "\\n")  # noqa: E731
    with open(path, "w", encoding="utf-8") as f:
        f.write("пассаж\tрежим\tбыло\tстало\n")
        for u in JSUNITS:
            if not u.active or u.passage in reverted:
                continue
            tag = "safe" if u.modes.get("safe") else "ТОЛЬКО FULL (риск)"
            try:
                old = u.raw if u.raw is not None else ""
                if isinstance(u, Chain):
                    old = "".join(s + (o.raw if isinstance(o, Str) else o.src) for s, o in zip(u.seps, u.ops))
                new = u.render()
            except Exception:  # noqa: BLE001
                continue
            f.write(f"{clean(u.passage)}\t{tag}\t{clean(old)}\t{clean(new)}\n")
        if reverted:
            f.write("\n# Пассажи, оставленные на английском (не прошли проверку):\n")
            for name in reverted:
                f.write(f"# {name}\n")
        if kept:
            f.write("\n# В этих пассажах отдельные строки оставлены на английском (остальное переведено):\n")
            for name, n in kept:
                f.write(f"# {name}: строк — {n}\n")


# ===========================================================================
# Анализ структуры игры (--analyze): шаблоны кода без текста игры
# ===========================================================================

def short_repr(tok_text):
    """Строка JS для отчёта: короткие значения-ключи показываем, фразы — как "T"."""
    try:
        v = js_unescape(tok_text[1:-1])
    except (ValueError, OverflowError):
        return '"?"'
    if not LATIN.search(v):
        return tok_text if len(tok_text) <= 20 else '"…"'
    if len(re.findall(r"[A-Za-z]+", v)) <= 2 and len(v) <= 24 and not re.search(r"[.!?]", v):
        return json.dumps(v, ensure_ascii=False)
    return '"T"'


def mask_code(src, limit=160):
    try:
        toks, _ = tokenize(src)
    except Exception:  # noqa: BLE001
        return src[:limit]
    out = []
    for t in toks:
        out.append({"ws": " ", "comment": "/*…*/", "num": "0", "tmpl": "`…`"}.get(t.type)
                   or (short_repr(t.text) if t.type == "str" else t.text))
    r = re.sub(r"\s+", " ", "".join(out)).strip()
    return r if len(r) <= limit else r[:limit] + "…"


def skel_item(it):
    if isinstance(it, Expr):
        return "${…}"
    if isinstance(it, Label):
        after = it.after.render() if isinstance(it.after, Seq) else it.after
        pre = it.before[:it.before.index("[[")] if "[[" in it.before else ""
        pre = "<<" + mask_code(pre[2:], 30).strip() + " " if pre.startswith("<<") else ""
        setter = ""
        if "][" in after:
            setter = "][" + mask_code(after.split("][", 1)[1].rsplit("]]", 1)[0], 90)
        tail = ">>" if pre else ""
        return f"{pre}[[T|P{setter}]]{tail}"
    kind = getattr(it, "kind", "")
    text = it.render() if isinstance(it, Seq) else getattr(it, "s", "")
    if kind == "code":
        return "<<script>>…<</script>>" if text.startswith("<<") else "<script>…</script>"
    if kind == "macro":
        m = re.match(r"^<<(/?)\s*([^\s>]*)([\s\S]*)>>$", text)
        if not m:
            return text[:40]
        args = mask_code(m.group(3), 120)
        return f"<<{m.group(1)}{m.group(2)}{(' ' + args) if args else ''}>>"
    if kind == "var":
        return re.sub(r"\d+", "0", text)
    if kind == "tag":
        t = re.sub(r"(\s(?!class\b)[\w-]+)\s*=\s*(\"[^\"]*\"|'[^']*')", r"\1=…", text)
        return t if len(t) <= 60 else t[:60] + "…>"
    if kind == "nl":
        return "↵"
    if kind == "url":
        return "URL"
    if kind in ("comment", "verbatim"):
        return text[:4] + "…"
    if kind == "link":
        return "[[…]]"
    return text[:20]


def skel_text(core):
    out = []
    for p in MARK_SPLIT.split(core):
        m = MARK.fullmatch(p)
        if m:
            out.append(skel_item(ITEMS[int(m.group(1))]))
        elif LATIN.search(p):
            out.append(" T ")
        elif p.strip():
            out.append(p.strip()[:3])
        elif p:
            out.append(" ")
    r = "".join(out)
    r = re.sub(r"T(?:[\s,.;:!?'\"«»…—()-]*T)+", "T", r)
    r = re.sub(r"\d+", "0", r)
    return re.sub(r"\s+", " ", r).strip()


def analyze(game, passages, modes, out_path, have_node):
    from collections import Counter, defaultdict
    lines = []
    w = lines.append
    fmt = game.format()
    ver = getattr(game, "attrs", {}).get("format-version", "") if hasattr(game, "attrs") else ""
    if isinstance(game, TweeFile):
        sd = next((p["body"] for p in game.passages if p["name"] == "StoryData"), "")
        m = re.search(r'"format-version"\s*:\s*"([^"]+)"', sd)
        ver = m.group(1) if m else ""
    STYLE["sc2"] = not (getattr(game, "kind", "") == "tw1" or ver.startswith("1.")) or "?"
    tags = Counter(t for p in passages for t in p["tags"])
    w("СТРУКТУРА ИГРЫ ДЛЯ НАСТРОЙКИ ПЕРЕВОДА (текст игры заменён на T, P — имя пассажа)")
    w("=" * 78)
    w(f"Формат: {fmt}" + (f" {game.attrs.get('format-version', '')}" if hasattr(game, "attrs") else ""))
    w(f"Пассажей: {len(passages)}; с тегами: " + ", ".join(f"{k}={v}" for k, v in tags.most_common(15)))
    w(f"Скриптов JS: {sum(1 for p in passages if 'script' in p['tags'])}, символов JS: "
      f"{sum(len(p['body']) for p in passages if 'script' in p['tags']):,}")
    ext = getattr(game, "external", None)
    if ext is not None:
        w("\nФАЙЛЫ .js, КОТОРЫЕ ПОДКЛЮЧАЕТ ИГРА:")
        for e in ext or [{"ref": "(нет)", "status": ""}]:
            w(f"  {e['ref']:50} {e['status']}")
        folder = os.path.dirname(os.path.abspath(game.path))
        known = {os.path.normcase(e["path"]) for e in ext}
        loose = []
        for root, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"]
            for fn in files:
                if (fn.lower().endswith(".js") and not re.search(r"_[a-z]{2,3}(?:-[A-Za-z]{2,4})?_(safe|full)\.js$", fn)
                        and os.path.normcase(os.path.join(root, fn)) not in known):
                    loose.append(os.path.relpath(os.path.join(root, fn), folder))
        if loose:
            w("  .js в папке, которые игра напрямую не подключает (не переводятся):")
            for f in sorted(loose)[:60]:
                w(f"    {f}")
    gv = sorted({k for k in GENDER if k not in GENDER_BASE and not k.endswith("Cap")
                 and not (k[:1].isupper() and k[:1].lower() + k[1:] in GENDER_BASE)})
    w("\nПЕРЕМЕННЫЕ РОДА, НАЙДЕННЫЕ В ИГРЕ: " + (", ".join(gv) if gv else "—"))
    widgets = sorted({m.group(1) for p in passages if "widget" in p["tags"]
                      for m in re.finditer(r"<<widget\s+[\"']([^\"']+)", p["body"])})
    w("ВИДЖЕТЫ (свои макросы игры): " + (", ".join(widgets[:200]) if widgets else "—"))

    # --- сбор шаблонов
    text_pat, macro_names, macro_pat, link_pat = Counter(), Counter(), Counter(), Counter()

    for t in TEXTS:
        if t.markup:
            k = skel_text(t.core) + ("   ⚥род" if t.group else "")
            text_pat[k] += 1
    for it in ITEMS:
        kind = getattr(it, "kind", "")
        if kind == "macro" and getattr(it, "mname", ""):
            macro_names[it.mname] += 1
            macro_pat[skel_item(it)] += 1
        elif isinstance(it, Label):
            link_pat[skel_item(it)] += 1
    known = LABEL_MACROS | JS_MACROS | KEY_MACROS | set(
        "nobr silently widget script else elseif endif capture unset run back return".split())

    def section(title, counter, limit):
        w(f"\n{title}  (уникальных: {len(counter):,}, показано до {limit})")
        w("-" * 78)
        for k, n in counter.most_common(limit):
            w(f"{n:7}  {k}")

    w("\nМАКРОСЫ: сколько раз встречаются (* — неизвестные скрипту, считаются виджетами игры)")
    w("-" * 78)
    w("  " + ", ".join(f"{'*' if k not in known else ''}{k}={v}" for k, v in macro_names.most_common(300)))
    section("СТРОКИ ТЕКСТА В ПАССАЖАХ — ШАБЛОНЫ", text_pat, 400)
    section("МАКРОСЫ — ШАБЛОНЫ", macro_pat, 400)
    section("ССЫЛКИ — ШАБЛОНЫ", link_pat, 150)

    # --- строки JS: контекст и решения
    js = defaultdict(lambda: [0, Counter()])
    for u in JSUNITS:
        snip = getattr(u, "snip", None)
        if not snip or u.text is None:
            continue
        if isinstance(u, Str):
            shown = short_repr(u.raw)
        elif isinstance(u, Tmpl):
            shown = "`" + ("T" if u.check and LATIN.search(u.check) else "") + "${…}`"
        else:
            shown = '"T" + … (склейка)'
        dec = " ".join(f"{m}:{'✓' if u.modes.get(m) else '✗'}" for m in modes)
        why = next((u.reasons.get(m) for m in modes if u.reasons.get(m)), "")
        cls = "T" if shown == '"T"' or shown.startswith("`T") or "склейка" in shown else "S"
        key = (snip.replace("⟨X⟩", "⟨T⟩" if cls == "T" else "⟨S⟩"), u.ctx, dec, why)
        js[key][0] += 1
        if cls == "S":
            js[key][1][shown] += 1
    w(f"\nСТРОКИ В КОДЕ JS — ГДЕ СТОЯТ И ЧТО С НИМИ ДЕЛАЕТ СКРИПТ  (уникальных: {len(js):,}, показано до 700)")
    w("  ⟨T⟩ — фраза, ⟨S⟩ — короткое значение (примеры справа); ✓ переводится, ✗ нет")
    w("-" * 78)
    for (snip, ctx, dec, why), (n, ex) in sorted(js.items(), key=lambda kv: -kv[1][0])[:700]:
        exs = ", ".join(x for x, _ in ex.most_common(6))
        w(f"{n:7}  [{ctx:6}] {dec:13} {snip}" + (f"   ← {why}" if why else "") + (f"   {{{exs}}}" if exs else ""))

    # --- пробная сборка с фальшивым переводом: какие пассажи не прошли бы проверку
    class Fake:
        def get(self, x):
            return x.upper()

        def has(self, x):
            return True

        def peek(self, x):
            return x.upper()
    for u in JSUNITS:
        u.active = any(u.modes.values())
        if isinstance(u, Chain):
            u.merged = u.active
        if u.text is not None:
            u.text.active = u.active
    fake = Fake()
    for t in TEXTS:
        t.apply(fake)
    for t in TEXTS:
        t.apply_fallback(fake)
    w("\nПРОБНАЯ СБОРКА (вместо перевода — ЗАГЛАВНЫЕ БУКВЫ): пассажи, которые не прошли бы проверку")
    w("-" * 78)
    for mode in modes:
        set_mode(mode)
        bad = []
        for p in passages:
            if p.get("mode"):
                ok, _, why = render_checked(p, have_node)
                if not ok:
                    bad.append(f"{p['name']} — {why}")
        w(f"  {mode}: {len(bad)}")
        for b in bad[:80]:
            w(f"     {b}")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return out_path


# ===========================================================================
# Перевод на лету (-c / --console-live, -l / --live), текст переводится на экране
# ===========================================================================

LIVE_JS = r'''/* === sugarcube_translate: перевод на лету (-l / --live, -c / --console-live) ===
   Переводит уже показанный на экране текст. Код игры, переменные и ссылки не меняются:
   ссылки и кнопки остаются теми же элементами, меняются только надписи на них.
   В боковой панели: выбор языка и кнопка «Обновить перевод». */
(function () {
	"use strict";
	if (window.__rutLive) { return; }
	window.__rutLive = true;
	var C = window.RUT_CFG || {};
	var SRC = C.src || "en";
	var WAIT = typeof C.wait === "number" ? C.wait : 3000;
	var LAT = /[A-Za-z]/;
	var HAS = Object.prototype.hasOwnProperty;
	var SKIP_TAGS = { SCRIPT: 1, STYLE: 1, TEXTAREA: 1, INPUT: 1, SELECT: 1, OPTION: 1, CODE: 1, PRE: 1,
		NOSCRIPT: 1, SVG: 1, CANVAS: 1, MATH: 1, IFRAME: 1, OBJECT: 1, VIDEO: 1, AUDIO: 1, KBD: 1, SAMP: 1 };
	var BLOCK_TAGS = { ADDRESS: 1, ARTICLE: 1, ASIDE: 1, BLOCKQUOTE: 1, BR: 1, BUTTON: 1, CAPTION: 1, CENTER: 1,
		DD: 1, DETAILS: 1, DIALOG: 1, DIV: 1, DL: 1, DT: 1, FIELDSET: 1, FIGCAPTION: 1, FIGURE: 1, FOOTER: 1,
		FORM: 1, H1: 1, H2: 1, H3: 1, H4: 1, H5: 1, H6: 1, HEADER: 1, HR: 1, LEGEND: 1, LI: 1, MAIN: 1, MENU: 1,
		NAV: 1, OL: 1, P: 1, SECTION: 1, SUMMARY: 1, TABLE: 1, TBODY: 1, TD: 1, TFOOT: 1, TH: 1, THEAD: 1, TR: 1,
		UL: 1 };
	var BLOCK_SEL = Object.keys(BLOCK_TAGS).map(function (t) { return t.toLowerCase(); }).join(",");
	/* SugarCube или другая игра на HTML (engine: "web"): где текст, что не трогать, что прятать до перевода */
	var ENGINE = C.engine === "web" ? "web" : "sugarcube";
	var ROOT_SEL = C.roots || "#passages, #ui-bar, #ui-dialog";
	var EXTRA_NO = C.noSel || "";
	var NO_SEL = "#story-title, #story-author, #menu-core, .rut-badge, .rut-panel" + (EXTRA_NO ? ", " + EXTRA_NO : "");
	var WAIT_SEL = C.waitSel === undefined ? "#passages" : C.waitSel;
	var FLOAT = ENGINE === "web" || C.panel === "float";  // панель — значком в углу (нет боковой панели SugarCube)
	var WORD = /[A-Za-z]{2}/;
	var CYR_LANGS = { ru: 1, uk: 1, be: 1, bg: 1, sr: 1, mk: 1, kk: 1, ky: 1, tg: 1, mn: 1, tt: 1 };
	var LANG_RE = /^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,4})?$/;
	var FAV = ["ru", "uk", "be", "pl", "cs", "de", "fr", "es", "it", "pt", "tr", "kk", "zh-CN", "ja", "ko"];
	/* языки Google: код, название по-русски, самоназвание */
	var GLANGS = [["af", "Африкаанс", "Afrikaans"], ["sq", "Албанский", "Shqip"], ["am", "Амхарский", "አማርኛ"],
		["ar", "Арабский", "العربية"], ["hy", "Армянский", "Հայերեն"], ["as", "Ассамский", "অসমীয়া"], ["ay", "Аймара", "Aymar aru"],
		["az", "Азербайджанский", "Azərbaycan"], ["bm", "Бамбара", "Bamanankan"], ["eu", "Баскский", "Euskara"],
		["be", "Белорусский", "Беларуская"], ["bn", "Бенгальский", "বাংলা"], ["bho", "Бходжпури", "भोजपुरी"],
		["bs", "Боснийский", "Bosanski"], ["bg", "Болгарский", "Български"], ["ca", "Каталанский", "Català"],
		["ceb", "Себуанский", "Cebuano"], ["ny", "Чева", "Chichewa"], ["zh-CN", "Китайский (упрощённый)", "简体中文"],
		["zh-TW", "Китайский (традиционный)", "繁體中文"], ["co", "Корсиканский", "Corsu"], ["hr", "Хорватский", "Hrvatski"],
		["cs", "Чешский", "Čeština"], ["da", "Датский", "Dansk"], ["dv", "Мальдивский", "ދިވެހި"], ["doi", "Догри", "डोगरी"],
		["nl", "Нидерландский", "Nederlands"], ["en", "Английский", "English"], ["eo", "Эсперанто", "Esperanto"],
		["et", "Эстонский", "Eesti"], ["ee", "Эве", "Eʋegbe"], ["tl", "Филиппинский", "Filipino"], ["fi", "Финский", "Suomi"],
		["fr", "Французский", "Français"], ["fy", "Фризский", "Frysk"], ["gl", "Галисийский", "Galego"],
		["ka", "Грузинский", "ქართული"], ["de", "Немецкий", "Deutsch"], ["el", "Греческий", "Ελληνικά"],
		["gn", "Гуарани", "Avañe'ẽ"], ["gu", "Гуджарати", "ગુજરાતી"], ["ht", "Гаитянский креольский", "Kreyòl ayisyen"],
		["ha", "Хауса", "Hausa"], ["haw", "Гавайский", "ʻŌlelo Hawaiʻi"], ["iw", "Иврит", "עברית"], ["hi", "Хинди", "हिन्दी"],
		["hmn", "Хмонг", "Hmoob"], ["hu", "Венгерский", "Magyar"], ["is", "Исландский", "Íslenska"], ["ig", "Игбо", "Igbo"],
		["ilo", "Илокано", "Ilokano"], ["id", "Индонезийский", "Bahasa Indonesia"], ["ga", "Ирландский", "Gaeilge"],
		["it", "Итальянский", "Italiano"], ["ja", "Японский", "日本語"], ["jw", "Яванский", "Basa Jawa"],
		["kn", "Каннада", "ಕನ್ನಡ"], ["kk", "Казахский", "Қазақша"], ["km", "Кхмерский", "ខ្មែរ"],
		["rw", "Киньяруанда", "Kinyarwanda"], ["gom", "Конкани", "कोंकणी"], ["ko", "Корейский", "한국어"], ["kri", "Крио", "Krio"],
		["ku", "Курдский (курманджи)", "Kurdî"], ["ckb", "Курдский (сорани)", "کوردی"], ["ky", "Киргизский", "Кыргызча"],
		["lo", "Лаосский", "ລາວ"], ["la", "Латынь", "Latina"], ["lv", "Латышский", "Latviešu"], ["ln", "Лингала", "Lingála"],
		["lt", "Литовский", "Lietuvių"], ["lg", "Луганда", "Luganda"], ["lb", "Люксембургский", "Lëtzebuergesch"],
		["mk", "Македонский", "Македонски"], ["mai", "Майтхили", "मैथिली"], ["mg", "Малагасийский", "Malagasy"],
		["ms", "Малайский", "Bahasa Melayu"], ["ml", "Малаялам", "മലയാളം"], ["mt", "Мальтийский", "Malti"], ["mi", "Маори", "Māori"],
		["mr", "Маратхи", "मराठी"], ["mni-Mtei", "Манипури", "ꯃꯩꯇꯩꯂꯣꯟ"], ["lus", "Мизо", "Mizo ṭawng"],
		["mn", "Монгольский", "Монгол"], ["my", "Бирманский", "မြန်မာ"], ["ne", "Непальский", "नेपाली"], ["no", "Норвежский", "Norsk"],
		["or", "Ория", "ଓଡ଼ିଆ"], ["om", "Оромо", "Afaan Oromoo"], ["ps", "Пушту", "پښتو"], ["fa", "Персидский", "فارسی"],
		["pl", "Польский", "Polski"], ["pt", "Португальский", "Português"], ["pt-PT", "Португальский (Португалия)", "Português (Portugal)"],
		["pa", "Панджаби", "ਪੰਜਾਬੀ"], ["qu", "Кечуа", "Runasimi"], ["ro", "Румынский", "Română"], ["ru", "Русский", "Русский"],
		["sm", "Самоанский", "Gagana Samoa"], ["sa", "Санскрит", "संस्कृतम्"], ["gd", "Шотландский гэльский", "Gàidhlig"],
		["nso", "Сепеди", "Sesotho sa Leboa"], ["sr", "Сербский", "Српски"], ["st", "Сесото", "Sesotho"], ["sn", "Шона", "chiShona"],
		["sd", "Синдхи", "سنڌي"], ["si", "Сингальский", "සිංහල"], ["sk", "Словацкий", "Slovenčina"], ["sl", "Словенский", "Slovenščina"],
		["so", "Сомали", "Soomaali"], ["es", "Испанский", "Español"], ["su", "Сунданский", "Basa Sunda"], ["sw", "Суахили", "Kiswahili"],
		["sv", "Шведский", "Svenska"], ["tg", "Таджикский", "Тоҷикӣ"], ["ta", "Тамильский", "தமிழ்"], ["tt", "Татарский", "Татар"],
		["te", "Телугу", "తెలుగు"], ["th", "Тайский", "ไทย"], ["ti", "Тигринья", "ትግርኛ"], ["ts", "Тсонга", "Xitsonga"],
		["tr", "Турецкий", "Türkçe"], ["tk", "Туркменский", "Türkmen"], ["ak", "Тви (акан)", "Akan"], ["uk", "Украинский", "Українська"],
		["ur", "Урду", "اردو"], ["ug", "Уйгурский", "ئۇيغۇرچە"], ["uz", "Узбекский", "Oʻzbek"], ["vi", "Вьетнамский", "Tiếng Việt"],
		["cy", "Валлийский", "Cymraeg"], ["xh", "Коса", "isiXhosa"], ["yi", "Идиш", "ייִדיש"], ["yo", "Йоруба", "Yorùbá"], ["zu", "Зулу", "isiZulu"]];
	var GL = Object.create(null);
	GLANGS.forEach(function (x) { GL[x[0].toLowerCase()] = x; });
	/* --- подписи нашей панели: на языке, который сейчас на экране (оригинал игры — на её языке) --- */
	var UIS = {
		original: ["Оригинал", "Original"], orig_short: ["оригинал", "original"], label: ["Перевод", "Translation"],
		pill_t: ["Перевод: язык, обновить, состояние", "Translation: language, refresh, status"],
		fav: ["Часто выбирают", "Popular"], all: ["Все языки Google", "All Google languages"],
		own: ["Свой код языка…", "Other language code…"], code_ph: ["код языка: hy, ka, he…", "language code: hy, ka, he…"],
		code_bad: ["не понял код — пример: hy, ka, he", "unknown code — for example hy, ka, he"],
		refresh: ["Обновить перевод", "Refresh translation"], refresh_short: ["Обновить", "Refresh"],
		refresh_t: ["Повторить то, что не перевелось (например, пропала связь), и заново проверить серверы Google",
			"Retry what was not translated (for example, the connection dropped) and check the Google servers again"],
		redo: ["Перевести страницу заново", "Translate the page again"],
		redo_t: ["Если перевод на экране получился странным: каждая фраза этой страницы переводится ещё раз отдельно, новый вариант запоминается вместо старого",
			"If the translation on the screen looks odd: every phrase of this page is translated again separately, the new variant replaces the old one"],
		fix: ["Исправить фразу", "Fix a phrase"],
		fix_t: ["Нажмите эту кнопку, а потом на фразу в игре — и впишите свой перевод. Он запоминается, «Перевести страницу заново» его не трогает",
			"Press this button, then tap a phrase in the game and type your own translation. It is remembered, and “Translate the page again” does not touch it"],
		export: ["Сохранить переводы в файл", "Save translations to a file"],
		export_t: ["Всё, что этот браузер перевёл сам, — в файл .json, чтобы добавить в файл игры на ПК (-i / --import)",
			"Everything this browser translated by itself goes into a .json file, to add it to the game file on a PC (-i / --import)"],
		why: ["Почему не отвечают", "Why they do not answer"], busy: ["Перевод… {n}", "Translating… {n}"],
		unavail: ["Перевод недоступен: {t}", "Translation unavailable: {t}"],
		redo_done: ["Страница переведена заново. Фраз: {n}, изменилось: {m}", "The page is translated again. Phrases: {n}, changed: {m}"],
		srv_down: ["окно скрипта не отвечает — перевожу напрямую через Google", "the script window does not answer — translating directly via Google"],
		part_late: ["часть текста пока без перевода: переводчик не ответил. «Обновить перевод» — попробовать снова",
			"some text is not translated yet: the translator did not answer. “Refresh translation” tries again"],
		late: ["переводчик не ответил — повторю через минуту", "the translator did not answer — will try again in a minute"],
		badlang_n: ["Google не знает язык «{l}». Выберите другой язык или проверьте код", "Google does not know the language “{l}”. Choose another language or check the code"],
		badlang: ["Google не знает язык «{l}»", "Google does not know the language “{l}”"],
		w429: ["Google просит подождать (слишком много запросов)", "Google asks to wait (too many requests)"],
		w403: ["Google отказал в доступе", "Google refused access"],
		wnet: ["нет связи или Google не пускает браузер", "no connection, or Google does not let the browser in"],
		wtimeout: ["не ответил вовремя", "did not answer in time"], wbad: ["пустой или непонятный ответ", "an empty or unclear answer"],
		w5xx: ["сбой на стороне Google", "a failure on Google's side"], wother: ["другая ошибка", "another error"],
		gdown_n: ["Google не отвечает или не пускает браузер. «Обновить перевод» — попробовать снова",
			"Google does not answer or does not let the browser in. “Refresh translation” tries again"],
		gdown: ["нет связи с Google — повторю через минуту", "no connection to Google — will try again in a minute"],
		orig_first: ["Сейчас показан оригинал — сначала выберите язык", "The original is shown — choose a language first"],
		none_screen: ["На экране нет переведённого текста", "There is no translated text on the screen"],
		redo_n: ["Перевожу страницу заново (фраз: {n})…", "Translating the page again ({n} phrases)…"],
		orig_shown: ["Показан оригинал", "The original is shown"],
		all_done: ["Всё на экране уже переведено", "Everything on the screen is already translated"],
		tap: ["Нажмите на фразу, перевод которой нужно исправить", "Tap the phrase whose translation you want to fix"],
		cancel: ["Отмена", "Cancel"], no_here: ["Здесь нет переведённого текста — нажмите на другую фразу", "There is no translated text here — tap another phrase"],
		fix_saved: ["Исправление сохранено", "The fix is saved"], cant_fix: ["Эту подпись исправить не получится", "This label can not be fixed"],
		fix_title: ["Исправить перевод", "Fix the translation"], orig_lbl: ["Оригинал:", "Original:"], tr_lbl: ["Перевод:", "Translation:"],
		marks_hint: ["⟦0⟧…⟦1⟧ — ссылки и выделение, ⟦n⟧ — числа и значки: оставьте все метки, их можно переставлять.",
			"⟦0⟧…⟦1⟧ are links and formatting, ⟦n⟧ are numbers and icons: keep every mark, they may be moved."],
		marks_bad: ["Не хватает меток ⟦n⟧ (или они повторяются) — так сохранить нельзя", "Some ⟦n⟧ marks are missing (or repeated) — it can not be saved like this"],
		will_be: ["Будет: {t}", "Result: {t}"], google_back: ["Вернуть перевод Google", "Restore the Google translation"],
		save: ["Сохранить", "Save"], via_srv: ["Через окно скрипта", "Via the script window"],
		srv_eng: ["переводчик: {e}", "translator: {e}"], not_probed: ["Google: серверы ещё не проверены", "Google: the servers are not checked yet"],
		probing: ["Проверяю серверы Google…", "Checking the Google servers…"],
		eps: ["Google: {a} из {b} серверов отвечают", "Google: {a} of {b} servers answer"],
		retry_in: ["проверю снова через {m} мин", "will check again in {m} min"],
		nothing_save: ["Сохранять пока нечего: новых переводов в этом браузере нет (встроенные уже в файле игры)",
			"Nothing to save yet: this browser has no new translations (the built-in ones are already in the game file)"],
		file_name: ["переводы", "translations"],
		saved_n: ["Сохранено переводов: {n} (файл «{f}»). На ПК: python sugarcube_translate.py <игра> -i <этот файл>",
			"Translations saved: {n} (file “{f}”). On a PC: python sugarcube_translate.py <game> -i <this file>"],
		save_fail: ["Браузер не дал сохранить файл", "The browser did not let the file be saved"]
	};
	var UI_MT = Object.create(null), uiMtBusy = Object.create(null);  // язык → подписи, переведённые машинно с английского
	function uiLang() { return LANG === "off" ? SRC : LANG; }
	function uiBase() { return String(uiLang()).split("-")[0].toLowerCase(); }
	function U(k, vars) {
		var e = UIS[k], t;
		if (!e) { return k; }
		if (uiBase() === "ru") { t = e[0]; }
		else {
			t = e[1];
			if (uiBase() !== "en" && /^en(-|$)/i.test(SRC)) {  // другие языки — через тот же переводчик (запоминается)
				var m = UI_MT[uiLang()];
				if (m && typeof m[k] === "string") { t = m[k]; } else if (!m) { uiMt(uiLang()); }
			}
		}
		if (vars) { Object.keys(vars).forEach(function (v) { t = t.split("{" + v + "}").join(String(vars[v])); }); }
		return t;
	}
	function uiMt(lang) {
		if (uiMtBusy[lang]) { return; }
		uiMtBusy[lang] = 1;
		try {
			var saved = JSON.parse(store("rut-live-ui-" + lang) || "null");
			if (saved && typeof saved === "object") { UI_MT[lang] = saved; relabelLater(); return; }
		} catch (e) { /* нет сохранённого */ }
		setTimeout(function () {  // после того, как ушёл перевод текста игры
			var keys = Object.keys(UIS), phs = [];
			var texts = keys.map(function (k) {
				var p = [];
				phs.push(p);
				return UIS[k][1].replace(/\{\w+\}/g, function (m) { p.push(m); return "⟦" + (p.length - 1) + "⟧"; });
			});
			backend(texts, lang, false, false, function (res) {
				var map = {}, n = 0;
				keys.forEach(function (k, i) {
					var r = res && res[i], ok = true;
					if (typeof r !== "string" || !r || /⟦/.test(UIS[k][1])) { return; }
					r = r.replace(/[⟦\[]\s*(\d+)\s*[⟧\]]/g, function (m, d) {
						if (phs[i][+d] === undefined) { ok = false; return ""; }
						return phs[i][+d];
					});
					if (ok && !/[⟦⟧]/.test(r)) { map[k] = r; n++; }
				});
				if (n) { UI_MT[lang] = map; store("rut-live-ui-" + lang, JSON.stringify(map)); relabelLater(); }
				else { setTimeout(function () { delete uiMtBusy[lang]; }, 60000); }  // нет связи — позже ещё раз
			});
		}, 1500);
	}
	var LBLS = [], relabelT = null;  // [элемент, ключ, свойство, приставка] — подписи, которые меняются вместе с языком
	function lab(el, k, prop, pre) {
		LBLS.push([el, k, prop || "textContent", pre || ""]);
		el[prop || "textContent"] = (pre || "") + U(k);
		return el;
	}
	function relabelLater() { clearTimeout(relabelT); relabelT = setTimeout(relabelPanel, 30); }
	function relabelPanel() {
		quiet(function () {
			LBLS.forEach(function (x) { var v = x[3] + U(x[1]); if (x[0][x[2]] !== v) { x[0][x[2]] = v; } });
		});
		if (sel) { fillSelect(); }
		showStatus();
		pillSync();
	}
	var DONE = new WeakSet();      // текстовые узлы, которые уже наши (переведены)
	var HANDLED = new WeakSet();   // содержимое пассажа, обработанное при показе
	var MEMS = Object.create(null), FAILS = Object.create(null);  // по языкам: исходник → перевод
	var RECS = [];                 // что и где переведено на экране (для смены языка без перезагрузки)
	var LISP_WORDS = C.lispWords || {};
	var STUT_SRC = /(^|[^A-Za-z])([A-Za-z])-(?=\2)(?!(?:cups?|shaped?|days?|types?|size|sized|cells?|class|list|lines?|zone|rank|ring|grade|rated|rating|section|series|spot|stars?|bombs?|team|test|track|words?|bars?|box|cars?)(?![A-Za-z]))/i;
	var STUT_TR = /(^|[^A-Za-zА-Яа-яЁёІіЇїЄєҐґ])((?:[A-Za-zА-Яа-яЁёІіЇїЄєҐґ]-){1,4})([А-Яа-яЁёІіЇїЄєҐґ])/g;

	function store(k, v) {  // запоминаем выбор языка в браузере (если браузер позволяет)
		try { if (v === undefined) { return window.localStorage.getItem(k); } window.localStorage.setItem(k, v); } catch (e) { /* нет доступа */ }
		return null;
	}
	/* язык по умолчанию — оригинал игры; выбор в боковой панели запоминается */
	var LANG = store("rut-live-lang") || (C.lang && C.lang !== "auto" ? C.lang : sysLang()) || "off";
	if (LANG !== "off" && !LANG_RE.test(LANG)) { LANG = "off"; }
	var EMBED = Object.create(null);  // сколько переводов встроено в файл, по языкам
	var EMBED_MANUAL = Object.create(null);  // исправленные вручную фразы (из файла)
	(function () {  // переводы, встроенные в файл игры (-l / --live): показываются сразу, без интернета
		try {
			var el = document.getElementById("rut-dict");
			if (!el) { return; }
			var d = JSON.parse(el.textContent), langs = d.langs || {};
			if (d.manual && typeof d.manual === "object") { Object.keys(d.manual).forEach(function (l) { if (Array.isArray(d.manual[l])) { EMBED_MANUAL[l] = d.manual[l]; } }); }
			if (d.lang && d.t) { langs[d.lang] = d.t; }
			Object.keys(langs).forEach(function (lang) {
				var M = MEMS[lang] = Object.create(null), t = langs[lang];
				Object.keys(t).forEach(function (k) { M[k] = t[k]; });
				EMBED[lang] = Object.keys(t).length;
			});
			el.textContent = "";
		} catch (e) { /* без встроенных переводов */ }
	})();
	var OVER = Object.create(null);
	function overlayDb(lang) {  // переведённое в этом браузере после сборки файла (например, «заново») главнее встроенного
		if (OVER[lang] || !EMBED[lang] || lang === "off") { return; }
		OVER[lang] = true;
		dbAll(lang, function (obj) {
			if (!obj) { return; }
			var M = MEMS[lang] || (MEMS[lang] = Object.create(null)), changed = Object.create(null), n = 0;
			Object.keys(obj).forEach(function (k) { if (M[k] !== obj[k]) { M[k] = obj[k]; changed[k] = 1; n++; } });
			if (!n || lang !== LANG) { return; }
			RECS.forEach(function (rec) {
				var hit = rec.node ? changed[rec.k.key] : rec.group ? changed[rec.group.key] : changed[rec.key] || changed[keyInfo(rec.st, lang).key];
				if (hit && rec.lang === LANG && recLive(rec)) { rec.lang = null; showRec(rec); }
			});
		}, typeof C.built === "number" ? C.built : 0);
	}
	function sysLang() {  // язык браузера / телефона — если это не язык оригинала и Google его знает
		try {
			var list = navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language || ""];
			for (var i = 0; i < list.length; i++) {
				var p = String(list[i] || "").split(/[-_]/), l = p[0].toLowerCase(), rg = (p[1] || "").toUpperCase();
				if (!l) { continue; }
				var c = l === "zh" ? (rg === "TW" || rg === "HK" || rg === "MO" ? "zh-TW" : "zh-CN") :
					(l === "pt" && rg === "PT") ? "pt-PT" : ({ he: "iw", jv: "jw", fil: "tl", nb: "no", nn: "no" }[l] || l);
				if (c.split("-")[0] === String(SRC).split("-")[0].toLowerCase()) { return ""; }  // система на языке игры
				if (GL[c.toLowerCase()]) { return GL[c.toLowerCase()][0]; }
			}
		} catch (e) { /* старый браузер */ }
		return "";
	}
	function langName(code) {
		if (code === "off") { var o = GL[SRC.toLowerCase()]; return U("original") + " (" + (o ? o[2] : SRC) + ")"; }
		var g = GL[String(code).toLowerCase()];
		if (!g) { return code; }
		return uiBase() === "ru" ? g[1] + (g[2] !== g[1] ? " \u2014 " + g[2] : "") : g[2];
	}
	var gen = 0;  // номер «эпохи» языка: ответы для старого языка не применяем
	function mem() { return MEMS[LANG] || (MEMS[LANG] = Object.create(null)); }
	function fails() { return FAILS[LANG] || (FAILS[LANG] = Object.create(null)); }

	function up(n) { return String(n.nodeName || "").toUpperCase(); }
	function skipEl(n) {
		if (!n || n.nodeType !== 1) { return false; }
		if (SKIP_TAGS[up(n)] || n.isContentEditable) { return true; }
		if (n.getAttribute && n.getAttribute("translate") === "no") { return true; }
		var cl = n.classList;
		if (cl && (cl.contains("notranslate") || cl.contains("rut-skip") || cl.contains("rut-badge") || cl.contains("rut-panel"))) { return true; }
		try { return !!(EXTRA_NO && n.matches && n.matches(EXTRA_NO)); } catch (e) { return false; }
	}
	function tiny(n) { return (n.textContent || "").trim().length <= 1; }  // «1», «q» — подписи клавиш и т.п.
	function isBlock(n) { return n.nodeType === 1 && !!BLOCK_TAGS[up(n)]; }
	function blocky(n) {
		if (n.nodeType !== 1) { return false; }
		if (isBlock(n)) { return true; }
		return !skipEl(n) && !!(n.querySelector && n.querySelector(BLOCK_SEL));
	}
	function isLisp(n) { return n.nodeType === 1 && n.classList && n.classList.contains("rut-l"); }

	/* --- куски текста: строка между <br> и блоками, вместе со ссылками и выделением внутри --- */
	function collect(box, out) {
		var cur = [];
		function flush() { if (cur.length) { out.push(cur); cur = []; } }
		for (var c = box.firstChild; c; c = c.nextSibling) {
			if (c.nodeType === 1 && skipEl(c)) {
				if (isBlock(c)) { flush(); } else { cur.push(c); }
				continue;
			}
			if (blocky(c)) {
				flush();
				if (up(c) !== "BR" && !(c.matches && c.matches(NO_SEL))) { collect(c, out); }
				continue;
			}
			cur.push(c);
		}
		flush();
	}
	function newLatin(n) {  // есть ли тут ещё не переведённый английский текст
		if (n.nodeType === 3) { return !DONE.has(n) && LAT.test(n.nodeValue); }
		if (n.nodeType !== 1 || skipEl(n) || isLisp(n)) { return false; }
		for (var c = n.firstChild; c; c = c.nextSibling) { if (newLatin(c)) { return true; } }
		return false;
	}
	function runNew(run) {
		for (var i = 0; i < run.length; i++) { if (newLatin(run[i])) { return true; } }
		return false;
	}

	/* --- кусок → строка для переводчика: элементы и числа заменяются метками ⟦n⟧ --- */
	function intVal(m) {  // «5», «1,000» → число; «05», «2.5», «10:30» — не целое количество
		return /^(?:0|[1-9]\d{0,14}|[1-9]\d{0,2}(?:,\d{3})+)$/.test(m) ? +m.replace(/,/g, "") : null;
	}
	function elNum(n) {  // <span class="gold">¤1,234</span> — число в отдельном элементе
		var m = (n.textContent || "").trim().match(/^[+\-\u2212]?[\u00A4$\u20AC\u00A3\u00A5\u20BD]?\s?(\d[\d,]*)\s?%?$/);
		return m ? intVal(m[1]) : null;
	}
	/* Шепелявость — только там, где шепелявил сам персонаж: слово с буквой-виджетом (<<s>>) или шепелявое
	   слово из данных игры («Mathter»), а если оно в прямой речи (в кавычках) — вся эта реплика. Это место
	   обводится парой меток ⟦a⟧…⟦b⟧ (как ссылка): переводчик сохраняет их вокруг перевода этого слова. */
	var LZ = "\uE001";
	function marksNested(t, st) {
		var stack = [], re = /\u27E6(\d+)\u27E7/g, m;
		while ((m = re.exec(t))) {
			var it = st.items[+m[1]];
			if (!it) { return false; }
			if (it.open || it.lz === 1) { stack.push(+m[1]); }
			else if (it.close !== undefined) { if (stack.pop() !== it.close) { return false; } }
			else if (it.lz === 2) { if (stack.pop() !== it.of) { return false; } }
		}
		return !stack.length;
	}
	function putZones(s, zones, st) {
		var uniq = [], seen = Object.create(null);
		zones.forEach(function (z) { var k = z[0] + ":" + z[1]; if (!seen[k] && z[1] > z[0]) { seen[k] = 1; uniq.push(z); } });
		uniq.sort(function (x, y) { return x[0] - y[0]; });
		for (var i = 1; i < uniq.length; i++) { if (uniq[i][0] < uniq[i - 1][1]) { return null; } }
		var n0 = st.items.length, opens = Object.create(null), closes = Object.create(null);
		uniq.forEach(function (z) {
			var a = st.items.length;
			st.items.push({ lz: 1 });
			st.items.push({ lz: 2, of: a });
			st.pairs[a] = a + 1;
			(opens[z[0]] = opens[z[0]] || []).push(a);
			(closes[z[1]] = closes[z[1]] || []).push(a + 1);
		});
		var out = "";
		for (var j = 0; j <= s.length; j++) {
			if (closes[j]) { out += closes[j].map(function (b) { return "\u27E6" + b + "\u27E7"; }).join(""); }
			if (opens[j]) { out += opens[j].map(function (a) { return "\u27E6" + a + "\u27E7"; }).join(""); }
			if (j < s.length && s.charAt(j) !== LZ) { out += s.charAt(j); }
		}
		if (!uniq.length || !marksNested(out, st)) {
			for (var k = n0; k < st.items.length; k++) { delete st.pairs[k]; }
			st.items.length = n0;
			return null;
		}
		st.lisp = true;
		st.np += uniq.length;
		return out;
	}
	function lispZones(s, st) {
		if (s.indexOf(LZ) < 0) { return s; }
		var quotes = [], open = -1, i, ch;
		for (i = 0; i < s.length; i++) {
			ch = s.charAt(i);
			if (open < 0 && "\"«“„".indexOf(ch) >= 0) { open = i; }
			else if (open >= 0 && "\"»”“".indexOf(ch) >= 0) { quotes.push([open + 1, i]); open = -1; }
		}
		var isW = function (c) { return c === LZ || /[A-Za-z\u00C0-\u024F]/.test(c); };
		var zq = [], zw = [];
		for (i = 0; i < s.length; i++) {
			if (s.charAt(i) !== LZ) { continue; }
			var a = i, b = i + 1, q = null;
			while (a > 0 && isW(s.charAt(a - 1))) { a--; }
			while (b < s.length && isW(s.charAt(b))) { b++; }
			for (var k = 0; k < quotes.length; k++) { if (quotes[k][0] <= i && i < quotes[k][1]) { q = quotes[k]; } }
			zw.push([a, b]);
			zq.push(q || [a, b]);
		}
		var out = putZones(s, zq, st);
		if (out === null) { out = putZones(s, zw, st); }  // реплика пересекает ссылку — тогда только само слово
		return out === null ? s.split(LZ).join("") : out;
	}
	function serialize(run) {
		var st = { items: [], lisp: false, nums: 0, pairs: {}, np: 0 };
		function mark(it) { st.items.push(it); return "⟦" + (st.items.length - 1) + "⟧"; }
		function text(t) {
			t = t.replace(/[⟦⟧\uE001]/g, "");
			return t.replace(/\d+(?:[.,:]\d+)*/g, function (m, off, all) {
				var it = { text: m }, v = intVal(m);
				if (v !== null && !/[A-Za-z]/.test(all.charAt(off - 1)) && !/[A-Za-z]/.test(all.charAt(off + m.length))) { it.v = v; st.nums++; }
				return mark(it);
			});
		}
		function walk(nodes) {
			var s = "";
			for (var i = 0; i < nodes.length; i++) {
				var n = nodes[i];
				if (n.nodeType === 3) { s += DONE.has(n) ? mark({ node: n }) : text(n.nodeValue); continue; }
				if (n.nodeType !== 1) { s += mark({ node: n }); continue; }
				if (isLisp(n)) {  // буква шепелявости (<<s>> и т.п.): переводчику — обычная буква
					s += (n.getAttribute("data-rul-on") === "1" ? LZ : "") + (n.getAttribute("data-rul") || "");
					continue;
				}
				if (skipEl(n) || !newLatin(n) || tiny(n)) {
					var nit = { node: n }, nv = skipEl(n) ? null : elNum(n);
					if (nv !== null) { nit.v = nv; st.nums++; }
					s += mark(nit);
					continue;
				}
				var open = st.items.length;
				st.items.push({ open: n });
				var inner = walk(Array.prototype.slice.call(n.childNodes));
				st.items.push({ close: open });
				st.pairs[open] = st.items.length - 1;  // для HTML-режима: какая метка закрывает этот элемент
				st.np++;
				s += "⟦" + open + "⟧" + inner + "⟦" + (st.items.length - 1) + "⟧";
			}
			return s;
		}
		var s = walk(run);
		s = s.replace(/[A-Za-z]+/g, function (w) {  // Mathter → Master (шепелявые слова из данных игры)
			return HAS.call(LISP_WORDS, w) ? LZ + LISP_WORDS[w] : w;
		});
		s = lispZones(s, st);
		st.lead = s.match(/^\s*/)[0];
		var rest = s.slice(st.lead.length);
		st.trail = rest.match(/\s*$/)[0];
		st.core = rest.slice(0, rest.length - st.trail.length);
		return st;
	}

	/* --- перевод → обратно в страницу (те же элементы, новые надписи) --- */
	function parse(res, st) {
		var n = st.items.length, seen = [], toks = [], re = /⟦\s*(\d+)\s*⟧/g, last = 0, m;
		if (st.core.indexOf("[") < 0) { res = res.replace(/\[\s*(\d+)\s*\]/g, "⟦$1⟧"); }
		while ((m = re.exec(res))) {
			if (m.index > last) { toks.push({ t: res.slice(last, m.index) }); }
			var id = +m[1];
			if (id >= n || seen[id]) { return null; }
			seen[id] = true;
			toks.push({ id: id });
			last = re.lastIndex;
		}
		if (last < res.length) { toks.push({ t: res.slice(last) }); }
		for (var i = 0; i < n; i++) { if (!seen[i]) { return null; } }
		var stack = [];
		for (var k = 0; k < toks.length; k++) {
			if (toks[k].id === undefined) { continue; }
			var it = st.items[toks[k].id];
			if (it.open || it.lz === 1) { stack.push(toks[k].id); }
			else if (it.close !== undefined) { if (stack.pop() !== it.close) { return null; } }
			else if (it.lz === 2 && stack.pop() !== it.of) { return null; }
		}
		return stack.length ? null : toks;
	}
	/* --- числа и согласование: «1 монета», «2 монеты», «5 монет» ---
	   Числа в тексте переводчику не видны (метки ⟦n⟧) — тогда он не знает, какую форму слова ставить.
	   Поэтому вместо метки подставляем «число-заместитель» той же грамматической категории языка
	   (для русского: 21 — как 1, 22 — как 2, 25 — как 5), а в переводе возвращаем настоящее число.
	   Одна и та же фраза с 5 и с 7 монетами переводится один раз (обе — «как 5»). */
	var PL = Object.create(null);
	function plural(lang) {
		if (HAS.call(PL, lang)) { return PL[lang]; }
		var p = null;
		try {
			if (typeof Intl !== "undefined" && Intl.PluralRules) {
				var r = new Intl.PluralRules(lang), list = Object.create(null), cats = 0;
				var add = function (n) {
					var c = r.select(n);
					if (!list[c]) { list[c] = []; cats++; }
					if (list[c].length < 40) { list[c].push(n); }
				};
				var n;
				for (n = 21; n < 1000; n++) { add(n); }  // двузначные и больше: переводчик не пишет их словами
				for (n = 2; n <= 20; n++) { add(n); }
				add(0);
				add(1);
				if (cats > 1) { p = { r: r, list: list }; }  // в китайском, японском… форма одна — не нужно
			}
		} catch (e) { p = null; }
		PL[lang] = p;
		return p;
	}
	function keyInfo(st, lang) {  // ключ фразы для языка: числа — заместителями своей категории
		if (!st.nums || lang === "off") { return { key: st.core, map: null }; }
		var c = st.kc || (st.kc = Object.create(null));
		if (c[lang]) { return c[lang]; }
		var P = plural(lang), info = { key: st.core, map: null };
		if (P) {
			var used = Object.create(null), map = Object.create(null), any = false;
			var key = st.core.replace(/\u27E6(\d+)\u27E7/g, function (m, i) {
				var it = st.items[+i];
				if (!it || it.v === undefined) { return m; }
				var cat = P.r.select(it.v), list = P.list[cat] || [], k = used[cat] || 0;
				if (k >= list.length) { return m; }
				used[cat] = k + 1;
				map[list[k]] = +i;
				any = true;
				return String(list[k]);
			});
			if (any && !/\d\d{3,}/.test(key.replace(/\u27E6\d+\u27E7/g, " "))) { info = { key: key, map: map }; }
		}
		c[lang] = info;
		return info;
	}
	function fromStand(res, info) {  // перевод с заместителями → с метками ⟦n⟧ (null — переводчик их испортил)
		if (!info.map || typeof res !== "string") { return res; }
		var count = Object.create(null), ok = true;
		var out = res.replace(/[\u27E6\[]\s*\d+\s*[\u27E7\]]|\d+/g, function (m) {
			if (!/^\d+$/.test(m)) { return m; }
			if (!HAS.call(info.map, m)) { ok = false; return m; }
			count[m] = (count[m] || 0) + 1;
			return "\u27E6" + info.map[m] + "\u27E7";
		});
		Object.keys(info.map).forEach(function (k) { if (count[k] !== 1) { ok = false; } });
		return ok ? out : null;
	}
	function trFor(st, lang) {  // [перевод с метками, его ключ] из памяти: сначала с числами по правилам языка
		var M = MEMS[lang], info = keyInfo(st, lang);
		if (!M) { return undefined; }
		if (info.map && typeof M[info.key] === "string") {
			var r = fromStand(M[info.key], info);
			if (r !== null) { return [r, info.key]; }
		}
		return typeof M[st.core] === "string" ? [M[st.core], st.core] : undefined;
	}
	var LISP_JA = { "さ": "しゃ", "す": "しゅ", "せ": "しぇ", "そ": "しょ", "ざ": "じゃ", "ず": "じゅ", "ぜ": "じぇ", "ぞ": "じょ",
		"サ": "シャ", "ス": "シュ", "セ": "シェ", "ソ": "ショ", "ザ": "ジャ", "ズ": "ジュ", "ゼ": "ジェ", "ゾ": "ジョ" };
	function lispStr(t, lang) {  // шепелявость на языке перевода (там, где у языка есть подходящие буквы)
		var l = String(lang).split("-")[0].toLowerCase();
		if (CYR_LANGS[l]) {
			return t.replace(/[сц]/g, "ш").replace(/з/g, "ж").replace(/[СЦ]/g, "Ш").replace(/З/g, "Ж");
		}
		if (l === "en") {
			return t.replace(/SS|SH/g, "TH").replace(/Ss|Sh/g, "Th").replace(/ss|sh/g, "th").replace(/[SZ]/g, "Th")
				.replace(/[sz]/g, "th").replace(/C(?=[eiy])/g, "Th").replace(/c(?=[eiy])/g, "th");
		}
		if (l === "es") { return t.replace(/s/g, "z").replace(/S/g, "Z"); }  // ceceo: «zí, zeñor»
		if (l === "el") { return t.replace(/[σςζ]/g, "θ").replace(/[ΣΖ]/g, "Θ"); }
		if (/^(ar|fa|ur|ps|sd|ug|ckb)$/.test(l)) { return t.replace(/[سص]/g, "ث").replace(/ز/g, "ذ"); }
		if (/^(iw|he|yi)$/.test(l)) { return t.replace(/[סש]/g, "ת").replace(/ז/g, "ד"); }
		if (/^(hi|mr|ne|sa|mai|bho|doi|gom)$/.test(l)) { return t.replace(/[सशष]/g, "थ"); }
		if (l === "ja") { return t.replace(/[さすせそざずぜぞサスセソザズゼゾ]/g, function (c) { return LISP_JA[c]; }); }
		if (/^(zh|ko|th|lo|km|my|ka|hy|am|ti|si|ta|te|kn|ml|gu|pa|bn|or|as|dv)$/.test(l)) { return t; }  // нет таких букв
		// прочие языки на латинице: s, z → th (звук шепелявости), но «sch» / «sz» как одна буква
		return t.replace(/sch/g, "\u0001").replace(/Sch/g, "\u0002").replace(/S[sSzZ]/g, "Th").replace(/ss|ß|sz|s|z/g, "th").replace(/S|Z/g, "Th")
			.replace(/\u0001/g, "sch").replace(/\u0002/g, "Sch");
	}
	function lispToks(toks, lang, st) {  // шепелявим только отмеченные места (слово или реплика персонажа)
		var depth = 0;
		toks.forEach(function (tk) {
			if (tk.id !== undefined) {
				var it = st.items[tk.id];
				if (it && it.lz === 1) { depth++; } else if (it && it.lz === 2) { depth--; }
				return;
			}
			if (depth > 0 && tk.t !== undefined) { tk.t = lispStr(tk.t, lang); }
		});
	}
	function pipes(t) { return (String(t).match(/[|\uFF5C\u00A6]/g) || []).length; }
	function inner(t, a, b) {  // текст между метками ⟦a⟧ и ⟦b⟧ (null — меток нет)
		var i = t.indexOf("\u27E6" + a + "\u27E7"), j = t.indexOf("\u27E6" + b + "\u27E7");
		return i < 0 || j < i ? null : t.slice(i + String(a).length + 2, j);
	}
	function sane(key, res, st) {  // перевод не ломает строку: столько же «|», у ссылок с текстом текст остался
		if (pipes(key) !== pipes(res)) { return false; }  // «Huge | Facepussy» → «Огромные | Лицо | Вагина» — нет
		var ok = true;
		Object.keys(st.pairs).forEach(function (a) {
			var s0 = inner(key, a, st.pairs[a]), r0 = inner(res, a, st.pairs[a]);
			if (s0 !== null && r0 !== null && WORD.test(s0.replace(/\u27E6\d+\u27E7/g, " "))
				&& !r0.replace(/\u27E6\d+\u27E7/g, "").trim()) { ok = false; }  // ссылка пропала (пустая)
		});
		return ok;
	}
	var NOSPACE = { zh: 1, ja: 1, th: 1, lo: 1, km: 1, my: 1 };
	function markSpaces(key, toks, lang) {  // «Огромный.Тонкий» → «Огромный. Тонкий»: пробел у ссылки, как в оригинале
		if (NOSPACE[String(lang).split("-")[0]]) { return; }
		var pre = Object.create(null), post = Object.create(null), re = /\u27E6(\d+)\u27E7/g, m;
		while ((m = re.exec(key))) {
			if (/\s/.test(key.charAt(m.index - 1))) { pre[m[1]] = 1; }
			if (/\s/.test(key.charAt(m.index + m[0].length))) { post[m[1]] = 1; }
		}
		for (var i = 0; i < toks.length; i++) {
			var tk = toks[i];
			if (tk.id === undefined) { continue; }
			var p = toks[i - 1], n = toks[i + 1];
			if (pre[tk.id] && p && p.t && !/[\s(«"“„\[]$/.test(p.t)) { p.t += " "; }
			if (post[tk.id] && n && n.t && !/^[\s.,;:!?…»)\]]/.test(n.t)) { n.t = " " + n.t; }
		}
	}
	var LOOK = { "А": "A", "В": "B", "С": "C", "Е": "E", "Н": "H", "К": "K", "М": "M", "О": "O", "Р": "P", "Т": "T", "Х": "X", "У": "Y" };
	function plainHyphens(src) {  // буквы «C» в «C-cup», «T» в «T-shaped»: это не заикание
		var out = {}, re = /(^|[^A-Za-z])([A-Za-z])-([A-Za-z]+)/g, m;
		while ((m = re.exec(src))) {
			if (m[2].toLowerCase() !== m[3].charAt(0).toLowerCase() || !STUT_SRC.test(m[0])) { out[m[2].toUpperCase()] = 1; }
		}
		return out;
	}
	function fixStutter(t, src) {  // H-hello → «Н-привет» → «П-привет»
		var keep = plainHyphens(src || "");
		return t.replace(STUT_TR, function (m, pre, letters, first) {
			var l0 = letters.charAt(0).toUpperCase();
			if (keep[l0] || keep[LOOK[l0] || ""]) { return m; }
			var parts = letters.split("-").slice(0, -1);
			return pre + parts.map(function (p) { return (p === p.toUpperCase() ? first.toUpperCase() : first.toLowerCase()) + "-"; }).join("") + first;
		});
	}
	function build(toks, st, made) {
		var root = { kids: [] }, stack = [root];
		for (var k = 0; k < toks.length; k++) {
			var tk = toks[k], top = stack[stack.length - 1];
			if (tk.t !== undefined) { var tn = document.createTextNode(tk.t); made.push(tn); top.kids.push(tn); continue; }
			var it = st.items[tk.id];
			if (it.lz) { continue; }  // граница шепелявого места — на экране её нет
			if (it.text !== undefined) { var nn = document.createTextNode(it.text); made.push(nn); top.kids.push(nn); }
			else if (it.node) { top.kids.push(it.node); }
			else if (it.open) { stack.push({ el: it.open, kids: [] }); }
			else {
				var fr = stack.pop(), el = fr.el;
				while (el.firstChild) { el.removeChild(el.firstChild); }
				fr.kids.forEach(function (x) { el.appendChild(x); });
				stack[stack.length - 1].kids.push(el);
			}
		}
		return root.kids;
	}
	function tidy(made) {  // лишние пробелы на стыках с ссылками и выделением
		var list = made.filter(function (t) { return t.parentNode; });
		var touching = function (a, b) {  // между ними на экране нет другого текста (например, числа в отдельном элементе)
			try {
				var r = document.createRange();
				r.setStartAfter(a);
				r.setEndBefore(b);
				return r.toString() === "";
			} catch (e) { return false; }
		};
		for (var i = 1; i < list.length; i++) {
			var a = list[i - 1], b = list[i];
			if (/\s$/.test(a.nodeValue) && /^\s/.test(b.nodeValue) && touching(a, b)) { b.nodeValue = b.nodeValue.replace(/^\s+/, ""); }
			if (/^[.,;:!?…»)]/.test(b.nodeValue) && / $/.test(a.nodeValue) && touching(a, b)) { a.nodeValue = a.nodeValue.replace(/ +$/, ""); }
		}
	}
	function textFor(rec, res, lang) {  // перевод (или оригинал для «off») → готовые куски
		if (lang !== "off" && !sane(rec.key, res, rec.st)) { return null; }
		var toks = parse(lang === "off" ? rec.key : res, rec.st);
		if (!toks) { return null; }
		if (lang !== "off") { markSpaces(rec.key, toks, lang); }
		if (lang !== "off" && STUT_SRC.test(rec.key)) { toks.forEach(function (x) { if (x.t !== undefined) { x.t = fixStutter(x.t, rec.key); } }); }
		if (rec.st.lisp) { lispToks(toks, lang === "off" ? SRC : lang, rec.st); }
		return toks;
	}
	function place(parent, before, nodes, rec, toks) {
		var made = [];
		var kids = build(toks, rec.st, made);
		var anchor = document.createTextNode("");
		parent.insertBefore(anchor, before);
		nodes.forEach(function (n) { if (n.parentNode === parent) { parent.removeChild(n); } });
		var lead = document.createTextNode(rec.st.lead), trail = document.createTextNode(rec.st.trail);
		made.unshift(lead);
		made.push(trail);
		var all = [lead].concat(kids, [trail]);
		all.forEach(function (x) { parent.insertBefore(x, anchor); });
		parent.removeChild(anchor);
		made.forEach(function (t) { DONE.add(t); ORIG_OF.set(t, rec); });
		tidy(made);
		rec.nodes = all;
	}
	var ORIG_OF = new WeakMap();  // переведённый текстовый узел → запись (там английский исходник)
	function srcText(el) {  // английский текст элемента (уже переведённые куски — по исходнику)
		var out = [], seen = [];
		(function walk(n) {
			if (n.nodeType === 3) {
				var rec = ORIG_OF.get(n);
				if (rec) {
					if (seen.indexOf(rec) < 0) { seen.push(rec); out.push(rec.key.replace(/\u27E6\d+\u27E7/g, " ")); }
				} else { out.push(n.nodeValue); }
				return;
			}
			if (n.nodeType !== 1 || skipEl(n)) { return; }
			for (var c = n.firstChild; c; c = c.nextSibling) { walk(c); }
		})(el);
		return out.join(" ").replace(/\s+/g, " ").trim();
	}
	var lastBad = false;  // последний apply не удался из-за испорченных меток (а не потому, что страница сменилась)
	function apply(run, key, res, group, k) {  // k — ключ, для которого получен перевод (с числами-заместителями)
		lastBad = false;
		var parent = run[0].parentNode;
		if (!parent) { return false; }
		for (var i = 0; i < run.length; i++) { if (run[i].parentNode !== parent) { return false; } }
		var st = serialize(run);  // страница могла измениться, пока ждали перевод
		if (st.core !== key) { return false; }
		if (k !== undefined && k !== key) {
			var info = keyInfo(st, LANG);
			if (info.key !== k) {  // числа на экране успели смениться (1 → 5): нужна другая форма
				var t0 = trFor(st, LANG);
				if (t0 !== undefined) { return apply(run, key, t0[0], group, key); }
				need(info.key, { run: run, key: key, k: info.key, passage: false });
				return "wait";
			}
			res = fromStand(res, info);
			if (res === null) {  // переводчик испортил числа — та же фраза с метками
				if (known(key)) { return mem()[key] !== null ? apply(run, key, mem()[key], group, key) : false; }
				need(key, { run: run, key: key, k: key, passage: false });
				return "wait";
			}
		}
		var rec = { key: key, st: st, nodes: run, lang: LANG, group: group || null, kk: k === undefined ? key : k };
		var toks = textFor(rec, res, LANG);
		if (!toks) { lastBad = true; return false; }
		place(parent, run[0], run, rec, toks);
		RECS.push(rec);
		return rec;
	}
	function reapply(rec, res, lang) {  // смена языка: те же места на экране, другой текст
		var nodes = rec.nodes.filter(function (n) { return n.parentNode; });
		if (!nodes.length) { return false; }
		var parent = nodes[0].parentNode;
		for (var i = 0; i < nodes.length; i++) { if (nodes[i].parentNode !== parent) { return false; } }
		var toks = textFor(rec, res, lang);
		if (!toks) { return false; }
		place(parent, nodes[0], nodes, rec, toks);
		return true;
	}

	/* --- запасной путь: переводчик испортил метки — переводим текстовые узлы по одному --- */
	function textJobs(run) {
		var nodes = [];
		function walk(n) {
			if (n.nodeType === 3) { if (!DONE.has(n) && LAT.test(n.nodeValue)) { nodes.push(n); } return; }
			if (n.nodeType !== 1 || skipEl(n) || isLisp(n)) { return; }
			for (var c = n.firstChild; c; c = c.nextSibling) { walk(c); }
		}
		run.forEach(walk);
		return nodes;
	}
	function nodeKey(t) {
		var nums = [];
		var s = t.nodeValue.replace(/[⟦⟧]/g, "").replace(/\d+(?:[.,:]\d+)*/g, function (m) { nums.push(m); return "⟦" + (nums.length - 1) + "⟧"; });
		var lead = s.match(/^\s*/)[0], rest = s.slice(lead.length), trail = rest.match(/\s*$/)[0];
		return { key: rest.slice(0, rest.length - trail.length), lead: lead, trail: trail, nums: nums, orig: t.nodeValue };
	}
	function applyNode(t, k, res, lang, again) {
		if (!t.parentNode || (DONE.has(t) && !again)) { return; }
		var out;
		if (lang === "off") { out = null; t.nodeValue = k.orig; DONE.add(t); return; }
		var ok = true;
		out = res.replace(/⟦\s*(\d+)\s*⟧/g, function (m, i) { if (k.nums[+i] === undefined) { ok = false; return ""; } return k.nums[+i]; });
		if (!ok || /⟦|⟧/.test(out)) { return; }
		if (STUT_SRC.test(k.key)) { out = fixStutter(out, k.key); }
		t.nodeValue = k.lead + out + k.trail;
		DONE.add(t);
		if (!again) { RECS.push({ node: t, k: k, lang: lang }); }
	}

	/* --- очередь запросов --- */
	var waiting = Object.create(null), sendQ = [], pumpT = null, inflight = 0, pendingPassage = 0, waitTimer = null, force = false;
	var REDO = Object.create(null), redoLeft = 0, redoChanged = 0, redoTotal = 0;  // «Перевести страницу заново»
	var RETRY = Object.create(null);  // фраза с испорченными метками — ещё раз отдельно, мимо кэша
	var RETRIED = Object.create(null);
	var redoRuns = false, redoRunsN = 0;  // «заново»: развалившиеся фразы собираются и переводятся целиком
	/* --- HTML-режим (как встроенный переводчик Chrome): фраза уходит в Google как HTML — ссылки и выделение
	   настоящими тегами <a i=N>…</a>, а не метками ⟦n⟧. Google понимает такие теги и переводит фразу целиком,
	   со смыслом; метки же часто сбивают его, и фраза разваливается на отдельные слова («Perky» → «Весёлый»).
	   Короткие подписи-кнопки — обычным списком через запятую после заголовка: «Форма груди: круглая, упругая…» */
	var HINFO = Object.create(null);
	function noteHtml(key, job) {
		if (HAS.call(HINFO, key)) { return; }
		var g = job.group ? { n: job.group.keys.length, hint: job.group.hint } : job.grec ? { n: job.grec.group.n, hint: job.grec.group.hint } : null;
		if (g) { HINFO[key] = { g: g.n, hint: !!g.hint }; return; }
		var st = job.st || (job.rec && job.rec.st) || null;
		if (!st && job.run) { try { st = serialize(job.run); } catch (e) { st = null; } }
		if (st && st.np) { HINFO[key] = { p: st.pairs }; }
	}
	function escT(t) { return String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
	function toHtml(key, info, sep) {
		if (info.g) {
			var m = key.split(/\s*\u27E698\u27E7\s*/), hint = info.hint && m.length === 2 ? m[0] : "";
			var items = (info.hint && m.length === 2 ? m[1] : key).split(" | ");
			if (items.length !== info.g) { return null; }
			return (hint ? escT(hint.replace(/[\s.:;,]+$/, "")) + ": " : "") +
				items.map(function (x, i) { return "<a i=" + i + ">" + escT(x) + "</a>"; }).join(sep || ", ");
		}
		var closes = Object.create(null);
		Object.keys(info.p).forEach(function (o) { closes[info.p[o]] = 1; });
		return escT(key).replace(/\u27E6(\d+)\u27E7/g, function (m, d) {
			return HAS.call(info.p, d) ? "<a i=" + d + ">" : HAS.call(closes, d) ? "</a>" : m;
		});
	}
	function marks(t) { return (t.match(/\u27E6\d+\u27E7/g) || []).sort().join(","); }
	function fromHtml(html, key, info) {  // ответ Google → наш формат (null — теги перепутаны: тогда метками)
		if (typeof html !== "string") { return null; }
		html = html.replace(/\s*<br\s*\/?>\s*/gi, " ");
		var re, m;
		if (info.g) {
			var parts = [], seen = 0, first = -1;
			re = /<a\s+i\s*=\s*["']?(\d+)["']?\s*>([\s\S]*?)<\/a\s*>/gi;
			while ((m = re.exec(html))) {
				var i = +m[1];
				if (i >= info.g || parts[i] !== undefined) { return null; }
				parts[i] = decodeHtml(m[2].replace(/<[^>]*>/g, "")).replace(/[|\u27E6\u27E7]/g, " ").replace(/\s+/g, " ").trim();
				if (first < 0) { first = m.index; }
				seen++;
			}
			if (seen !== info.g || parts.some(function (x) { return !x; })) { return null; }
			if (!tidyParts(groupItems(key, info.hint), parts)) { return null; }
			var out = parts.join(" | ");
			if (info.hint) {
				var h = decodeHtml(html.slice(0, first).replace(/<[^>]*>/g, "")).replace(/[\s:\uFF1A,\u060C\u3001]+$/, "").replace(/[|\u27E6\u27E7]/g, " ").trim();
				out = (h || "-") + " \u27E698\u27E7 " + out;
			}
			return out;
		}
		var stack = [], ok = true;
		var res = html.replace(/<a\s+i\s*=\s*["']?(\d+)["']?\s*>|<\/a\s*>/gi, function (t, d) {
			if (d !== undefined) {
				if (!HAS.call(info.p, d)) { ok = false; return ""; }
				stack.push(d);
				return "\u27E6" + d + "\u27E7";
			}
			var o = stack.pop();
			if (o === undefined) { ok = false; return ""; }
			return "\u27E6" + info.p[o] + "\u27E7";
		});
		if (!ok || stack.length) { return null; }
		res = decodeHtml(res.replace(/<[^>]*>/g, ""));
		return marks(res) === marks(key) ? res : null;
	}
	function need(key, job) {
		job.gen = gen;
		noteHtml(key, job);
		if (!waiting[key]) { waiting[key] = []; sendQ.push(key); }
		waiting[key].push(job);
		if (job.passage) { pendingPassage++; }
		if (!pumpT) { pumpT = setTimeout(pump, 10); }
		badge();
	}
	function known(key) {
		var M = mem();
		if (!HAS.call(M, key)) { return false; }
		if (M[key] !== null) { return true; }
		return Date.now() - (fails()[key] || 0) < 60000;  // не вышло — повторим не раньше чем через минуту
	}
	function codes(t) {  // «F-cup» → F, «AA-cup» → AA, «Level 5» → 5: это переводчик должен оставить как есть
		var out = [], re = /(^|[^A-Za-z0-9])([A-Z]{2,4}|[A-Z](?=-)|\d+)(?![A-Za-z0-9])/g, m;
		while ((m = re.exec(String(t)))) { out.push(m[2]); re.lastIndex = m.index + m[0].length; }
		return out;
	}
	function hasCode(t, c) { return new RegExp("(^|[^A-Za-z0-9])" + c + "(?![A-Za-z0-9])").test(t); }
	function groupItems(key, hint) {
		var m = key.split(/\s*\u27E698\u27E7\s*/);
		return (hint && m.length === 2 ? m[1] : key).split(" | ");
	}
	function tidyParts(items, parts) {  // точка, которую Google ставит в конце списка, и перепутанные подписи
		if (!parts || parts.length !== items.length) { return null; }
		for (var i = 0; i < parts.length; i++) {
			if (!/[.!?\u2026]$/.test(items[i])) { parts[i] = parts[i].replace(/[\s.\u3002;,]+$/, ""); }
			if (!parts[i]) { return null; }
			var cs = codes(items[i]);
			for (var j = 0; j < cs.length; j++) { if (!hasCode(parts[i], cs[j])) { return null; } }  // «F-cup» → «FF» — не то
		}
		return parts;
	}
	function groupParts(r, n, hint, key) {  // «подсказка ⟦98⟧ Круглая | Заострённая | …» → ["Круглая", …]
		if (typeof r !== "string") { return null; }
		if (hint) {
			var m = r.match(/[\u27E6\[]\s*98\s*[\u27E7\]]/g);
			if (!m || m.length !== 1) { return null; }
			r = r.slice(r.search(/[\u27E6\[]\s*98\s*[\u27E7\]]/) + m[0].length);
		}
		var parts = r.split(/\s*[|\uFF5C\u00A6]\s*/).map(function (x) { return x.trim(); });
		if (parts.length !== n || parts.some(function (x) { return !x || /[\u27E6\u27E7]/.test(x); })) { return null; }
		return key ? tidyParts(groupItems(key, hint), parts) : parts;
	}
	function sameWord(part, item) {  // перевод подписи совпал с оригиналом (английское слово так и осталось)
		if (!part || !item || !WORD.test(item)) { return false; }
		return part.replace(/[\s.\u3002;,]+$/, "").trim().toLowerCase() === item.trim().toLowerCase();
	}
	/* Ссылка в строке, которую переводчик оставил как было, хотя остальное перевёл:
	   «Губы: Лицокиска. Тонкие | … | Огромные | Facepussy» — это слово переводится ещё раз отдельно,
	   с самой строкой как подсказкой, и подставляется на место (в памяти — тоже). */
	function loneLinks(key, r, st) {
		if (typeof r !== "string" || r.toLowerCase() === key.toLowerCase()) { return []; }
		var out = [];
		Object.keys(st.pairs).forEach(function (a) {
			var b = st.pairs[a], s0 = inner(key, a, b), r0 = inner(r, a, b);
			if (s0 === null || r0 === null || /\u27E6/.test(s0) || /\u27E6/.test(r0)) { return; }
			if (sameWord(r0, s0) && s0.trim().length > 2 && !codes(s0.trim()).length) { out.push({ a: a, b: b, word: s0.trim() }); }
		});
		return out.length <= 3 ? out : [];
	}
	function fixLone(rec, kk, r) {
		var lone = loneLinks(kk, r, rec.st);
		if (!lone.length) { return; }
		var ctx = kk.replace(/\u27E6\d+\u27E7/g, " ").replace(/[|\s]+$/, "").replace(/\s+/g, " ").trim();
		if (ctx.length > 140) { ctx = ctx.slice(0, 140); }
		lone.forEach(function (L) {
			var sk = ctx + " \u27E698\u27E7 " + L.word, job = { rec: rec, kk: kk, a: L.a, b: L.b, word: L.word };
			if (!known(sk)) { need(sk, { lone: job, passage: false }); }
			else if (mem()[sk] !== null) { finishLone(job, mem()[sk]); }
		});
	}
	function finishLone(L, r) {
		var parts = groupParts(r, 1, true, null), t = parts && parts[0], M = mem(), cur = M[L.kk];
		if (!t || sameWord(t, L.word) || typeof cur !== "string" || /[|\u27E6\u27E7]/.test(t)) { return; }
		var re = new RegExp("\u27E6" + L.a + "\u27E7[^\u27E6\u27E7]*\u27E6" + L.b + "\u27E7");
		var nv = cur.replace(re, "\u27E6" + L.a + "\u27E7" + t.replace(/[\s.]+$/, "") + "\u27E6" + L.b + "\u27E7");
		if (nv === cur) { return; }
		M[L.kk] = nv;
		if (!SERVER) { dbPut(LANG, [[L.kk, nv]]); }
		var rec = L.rec;
		if (!recLive(rec) || rec.lang !== LANG) { return; }
		var rr = L.kk !== rec.key ? fromStand(nv, keyInfo(rec.st, LANG)) : nv;
		if (rr !== null && reapply(rec, rr, LANG)) { rec.lang = LANG; }
	}
	function finishGroup(g, r) {
		var parts = groupParts(r, g.keys.length, g.hint, g.gkey), M = mem();
		if (!parts && !RETRIED[g.gkey] && g.runs.some(runNew)) {  // подписи перепутаны (F → «FF»): ещё раз, мимо кэша
			RETRIED[g.gkey] = 1;
			RETRY[g.gkey] = 1;
			need(g.gkey, { group: g, passage: false });
			return;
		}
		var items = parts && !g.single ? groupItems(g.gkey, g.hint) : null;
		var head = g.hint ? g.gkey.split(/\s*\u27E698\u27E7\s*/)[0] : "";
		g.runs.forEach(function (run, i) {
			var key = g.keys[i], part = parts && parts[i], wrap = g.wraps[i];
			if (items && sameWord(part, items[i]) && runNew(run)) {
				/* Google иногда оставляет слово из списка как было (чаще последнее: «… | Huge | Facepussy»):
				   эту подпись — ещё раз отдельно, с тем же заголовком («Lips: … ⟦98⟧ Facepussy») */
				var sk = (head ? head + " \u27E698\u27E7 " : "") + items[i];
				var sg = { runs: [run], keys: [key], hint: !!head, gkey: sk, wraps: [wrap], single: true };
				if (!known(sk)) { need(sk, { group: sg, passage: false }); return; }
				if (M[sk] !== null) { finishGroup(sg, M[sk]); return; }
			}
			var full = part && (wrap ? "\u27E60\u27E7" + part + "\u27E61\u27E7" : part);
			if (part && part.length <= 4 * key.length + 14 && apply(run, key, full, { key: g.gkey, i: i, n: g.keys.length, hint: g.hint, wrap: wrap })) { return; }
			if (!runNew(run)) { return; }  // подсказка не помогла — как обычно, по одному
			if (known(key)) { if (M[key] !== null) { apply(run, key, M[key]); } }
			else { need(key, { run: run, key: key, passage: false }); }
		});
	}
	function finish(job, r) {
		quiet(function () {
			if (job.group) { finishGroup(job.group, r); return; }
			if (job.lone) { finishLone(job.lone, r); return; }
			if (job.grec) {
				var g = job.grec.group, parts = groupParts(r, g.n, g.hint, g.key);
				var part = parts && (g.wrap ? "\u27E60\u27E7" + parts[g.i] + "\u27E61\u27E7" : parts[g.i]);
				if (part && reapply(job.grec, part, LANG)) { job.grec.lang = LANG; return; }
				if (known(job.grec.key)) { var v = mem()[job.grec.key]; if (v !== null && reapply(job.grec, v, LANG)) { job.grec.lang = LANG; } }
				else { need(job.grec.key, { rec: job.grec }); }
				return;
			}
			if (job.rec) {
				var rec = job.rec, rr = r, used = job.k !== undefined ? job.k : rec.key;
				if (used !== rec.key) {
					rr = fromStand(r, keyInfo(rec.st, LANG));
					if (rr === null) {  // переводчик испортил числа — вариант с метками
						if (rec.lang === LANG) { return; }  // на экране уже есть перевод — оставляем его
						if (typeof mem()[rec.key] !== "string") {
							if (!known(rec.key)) { need(rec.key, { rec: rec, k: rec.key }); }
							return;
						}
						rr = mem()[rec.key];
						used = rec.key;
					}
				}
				if (reapply(rec, rr, LANG)) { rec.lang = LANG; rec.kk = used; }
				return;
			}
			if (job.nrec) { applyNode(job.nrec.node, job.nrec.k, r, LANG, true); job.nrec.lang = LANG; return; }
			if (job.node) { applyNode(job.node, job.k, r, LANG, job.again); return; }
			var got = apply(job.run, job.key, r, null, job.k);
			var kk = job.k !== undefined ? job.k : job.key;
			if (!got && !job.run.every(function (n) { return n.isConnected; })) { return; }  // это место уже заменено (повтор той же фразы)
			if (!got && lastBad && !job.retried && !RETRIED[kk] && !serverMode() && runNew(job.run)) {
				/* метки испорчены: сначала ещё раз эту фразу отдельно (в пачке переводчик иногда сбивается),
				   и только если снова не вышло — по кусочкам (тогда теряется связь между частями фразы) */
				RETRIED[kk] = 1;  // один раз за игру
				RETRY[kk] = 1;
				need(kk, { run: job.run, key: job.key, k: job.k, passage: false, retried: true });
				return;
			}
			if (got && got !== "wait") { fixLone(got, kk, r); }
			if (got && got !== "wait" && job.upgrade && !known(job.upgrade)) {
				need(job.upgrade, { rec: got, k: job.upgrade });  // старый перевод уже на экране; с правильными формами — следом
			}
			if (!got && runNew(job.run)) {
				textJobs(job.run).forEach(function (t) {
					var k = nodeKey(t);
					if (!WORD.test(k.key)) { return; }
					if (known(k.key)) { if (mem()[k.key] !== null) { applyNode(t, k, mem()[k.key], LANG); } }
					else { need(k.key, { node: t, k: k, passage: job.passage }); }
				});
			}
		});
	}
	function pump() {  // до 3 запросов одновременно: пассаж не ждёт, пока переведётся боковая панель и т.п.
		pumpT = null;
		while (sendQ.length && inflight < 3) { sendBatch(); }
		badge();
	}
	function sendBatch() {
		var viaServer = SERVER && Date.now() >= serverDownUntil;
		var maxN = viaServer ? 300 : 40, maxC = viaServer ? 40000 : 4000;  // окно скрипта само делит на части
		var batch = [], size = 0, lang = LANG, g = gen, f = force, W = waiting, redo = !!REDO[sendQ[0]];
		var retry = !redo && !!RETRY[sendQ[0]];
		force = false;
		if (redo || retry) {  // заново — по одной фразе: переводчик видит её без соседних строк
			batch.push(sendQ.shift());
			delete REDO[batch[0]];
			delete RETRY[batch[0]];
		}
		while (!redo && !retry && sendQ.length && !REDO[sendQ[0]] && !RETRY[sendQ[0]] && batch.length < maxN && (size + sendQ[0].length < maxC || !batch.length)) {
			var k = sendQ.shift();
			batch.push(k);
			size += k.length + 1;
		}
		inflight++;
		backend(batch, lang, f, redo || retry, function (res) {
			inflight--;
			var M = MEMS[lang] || (MEMS[lang] = Object.create(null)), F = FAILS[lang] || (FAILS[lang] = Object.create(null));
			for (var i = 0; i < batch.length; i++) {
				var key = batch[i], r = res && typeof res[i] === "string" && res[i] ? res[i] : null, old = M[key];
				if (redo) {
					redoLeft--;
					if (r !== null && typeof old === "string" && r !== old) { redoChanged++; }
					if (r === null) { r = typeof old === "string" ? old : null; }  // не вышло — оставляем прежний перевод
					if (redoLeft <= 0 && g === gen) {
						redoLeft = 0;
						note(U("redo_done", { n: redoTotal, m: redoChanged }));
					}
				}
				M[key] = r;
				if (r === null) { F[key] = Date.now(); } else { delete F[key]; }
				var jobs = W[key] || [];  // W — очередь того языка, для которого был запрос
				delete W[key];
				if (g !== gen) { continue; }
				for (var j = 0; j < jobs.length; j++) {
					if (jobs[j].passage) { pendingPassage--; }
					if (r !== null) { finish(jobs[j], r); }
				}
			}
			if (pendingPassage <= 0) { pendingPassage = 0; setWait(false); }
			pump();
		});
	}

	/* --- что переводить --- */
	function translateRoot(root, passage) {
		if (LANG === "off" || !root || (root.closest && root.closest(NO_SEL))) { return 0; }
		var runs = [];
		collect(root, runs);
		var n = 0, cands = [];
		var single = function (run, st) {
			var K = keyInfo(st, LANG).key, M = mem(), hasCore = K !== st.core && typeof M[st.core] === "string";
			if (redoRuns) {  // «Перевести страницу заново»: мимо кэша, по одной фразе
				if (!waiting[K]) { REDO[K] = 1; redoRunsN++; }
				need(K, { run: run, key: st.core, k: K, passage: false, st: st });
				return;
			}
			if (known(K)) {
				if (M[K] !== null) { finish({ run: run, key: st.core, k: K, passage: false }, M[K]); }
				else if (hasCore) { finish({ run: run, key: st.core, k: st.core, passage: false }, M[st.core]); }
				return;
			}
			if (hasCore) {  // перевод из прошлых версий (числа метками) — сразу, а с правильными формами — следом
				finish({ run: run, key: st.core, k: st.core, upgrade: K, passage: false }, M[st.core]);
				return;
			}
			need(K, { run: run, key: st.core, k: K, passage: passage });
			n++;
		};
		runs.forEach(function (run) {
			if (!runNew(run)) { return; }
			var st = serialize(run);
			if (!WORD.test(st.core.replace(/⟦\d+⟧/g, ""))) { return; }
			var item = shortItem(run, st);
			if (item) { cands.push({ run: run, st: st, item: item }); return; }
			single(run, st);
		});
		/* короткие подписи рядом (кнопки «Round», «Pointy», «Perky» …) — одним запросом, с заголовком раздела:
		   «Breast shape. The shape of your breasts. ⟦98⟧ Round | Pointy | Perky» → переводчик понимает, о чём речь */
		var boxes = [], kinds = [], lists = [];  // группа — одинаковые элементы (тег и класс) в одном блоке
		cands.forEach(function (c) {
			var box = c.item.parentElement, kind = c.item.tagName + "." + String(c.item.className || "").split(/\s+/)[0], k = -1;
			for (var i = 0; i < boxes.length; i++) { if (boxes[i] === box && kinds[i] === kind) { k = i; break; } }
			if (k < 0) { boxes.push(box); kinds.push(kind); lists.push([c]); } else { lists[k].push(c); }
		});
		lists.forEach(function (list, k) {
			var lh = list.length === 1 ? labelHint(list[0].item) : "";
			if ((list.length < 2 && !lh) || list.length > 30) { list.forEach(function (c) { single(c.run, c.st); }); return; }
			var hint = lh || hintFor(boxes[k], list[0].item, list);
			var keys = list.map(function (c) { return c.st.core; });
			var gkey = (hint ? hint + " \u27E698\u27E7 " : "") + list.map(function (c) { return c.st.inner; }).join(" | ");
			var job = { group: { runs: list.map(function (c) { return c.run; }), keys: keys, hint: !!hint, gkey: gkey,
				wraps: list.map(function (c) { return c.st.wrap; }) }, passage: passage };
			if (redoRuns && !waiting[gkey]) { REDO[gkey] = 1; redoRunsN++; job.passage = false; need(gkey, job); return; }
			if (known(gkey)) {
				if (mem()[gkey] !== null) { finish(job, mem()[gkey]); } else { list.forEach(function (c) { single(c.run, c.st); }); }
				return;
			}
			need(gkey, job);
			n++;
		});
		return n;
	}
	function shortItem(run, st) {  // одна короткая подпись, которая целиком занимает свой элемент (кнопку и т.п.)
		var w = st.core.match(/^\u27E60\u27E7([^\u27E6\u27E7]*)\u27E61\u27E7$/);  // <span>round</span> — обёртка не мешает
		var core = w ? w[1] : st.core;
		st.inner = core;
		st.wrap = !!w;
		if (/[\u27E6\u27E7|]/.test(core) || core.length > 40 || core.split(/\s+/).length > 4 || /[.!?\u2026:;,]$/.test(core)) { return null; }
		var item = run[0].parentNode;
		if (!item || item.nodeType !== 1 || !item.parentElement || item.matches(ROOT_SEL)) { return null; }
		if ((item.textContent || "").replace(/\s+/g, " ").trim() !== run.map(function (x) { return x.textContent; }).join("").replace(/\s+/g, " ").trim()) { return null; }
		return item;
	}
	function labelHint(item) {  // подпись прямо перед одиночным значением: <td>Breasts:</td><td>Perky</td>
		var e = item.previousElementSibling;
		if (!e || skipEl(e) || isBlock(item) !== isBlock(e)) { return ""; }
		var t = srcText(e).replace(/[|\u27E6\u27E7]/g, " ").replace(/\s+/g, " ").trim();
		if (!t || t.length > 40 || !WORD.test(t) || /[.!?\u2026]$/.test(t)) { return ""; }
		var cls = String(e.className || "");
		var labelish = /:$/.test(t) || /^(TH|DT|LABEL|LEGEND)$/.test(up(e)) || /label|title|name|key|caption|head/i.test(cls);
		return labelish ? (/:$/.test(t) ? t : t + ":") : "";
	}
	function hintFor(box, first, list) {  // заголовок раздела: текст перед первой кнопкой (или перед всем блоком)
		var items = list.map(function (c) { return c.item; }), parts = [];
		var take = function (start) {
			for (var e = start; e && parts.length < 2; e = e.previousElementSibling) {
				if (items.indexOf(e) >= 0 || skipEl(e)) { continue; }
				var t = srcText(e);
				if (t && WORD.test(t)) { parts.unshift(t); }
				if (parts.join(" ").length > 90) { break; }
			}
		};
		take(first.previousElementSibling);
		if (!parts.length && box) { take(box.previousElementSibling); }
		var h = parts.map(function (x, i) { return i < parts.length - 1 && !/[.!?:]$/.test(x) ? x + "." : x; })  // «Start Date. Select …»
			.join(" ").replace(/\s+/g, " ").replace(/[|\u27E6\u27E7]/g, " ").trim();
		if (h.length > 100) { h = h.slice(-100); h = h.slice(h.indexOf(" ") + 1); }
		if (h && !/[.!?:]$/.test(h)) { h += ":"; }
		return WORD.test(h) ? h : "";
	}
	function allRoots() { document.querySelectorAll(ROOT_SEL).forEach(function (r) { translateRoot(r, false); }); }

	/* --- переводчик: наш сервер (python ... -c) или Google напрямую из браузера --- */
	var SERVER = !!C.server && /^https?:$/.test(location.protocol) && /^(127\.0\.0\.1|localhost|\[::1\])$/.test(location.hostname);
	var serverDownUntil = 0, serverEps = null, serverEngine = "", serverWhy = null;
	function xhr(method, url, body, headers, cb, timeout) {
		try {
			var x = new XMLHttpRequest();
			x.open(method, url, true);
			x.timeout = timeout || 240000;
			Object.keys(headers || {}).forEach(function (h) { x.setRequestHeader(h, headers[h]); });
			x.onload = function () { cb(x.status >= 200 && x.status < 300 ? null : x.status, x.responseText); };
			x.onerror = function () { cb("net", null); };
			x.ontimeout = function () { cb("timeout", null); };
			x.send(body);
		} catch (e) { cb("exc", null); }
	}
	function serverMode() { return SERVER && Date.now() >= serverDownUntil; }
	function backend(keys, lang, f, redo, cb) {
		if (SERVER && (Date.now() >= serverDownUntil || f)) {
			xhr("POST", C.server, JSON.stringify({ t: keys, lang: lang, force: !!f, redo: !!redo, h: keys.map(function (k) { return HINFO[k] || null; }) }), { "Content-Type": "application/json" }, function (err, txt) {
				var d = null;
				if (!err) { try { d = JSON.parse(txt); } catch (e) { d = null; } }
				if (!d || !d.t) {  // окно скрипта закрыто — переводим прямо из браузера
					serverDownUntil = Date.now() + 30000;
					problem("srv_down");
					if (!probed) { probeAll(); }
					direct(keys, lang, f, redo, cb);
					return;
				}
				if (d.eps !== undefined) { serverEps = d.eps; serverWhy = d.why || null; }
				if (d.err === "lang") {
					badLang(lang);
				} else if (d.t.some(function (r) { return r === null; })) {
					note(U("part_late"));
					problem("late");
				} else { problem(""); }
				cb(d.t);
			});
			return;
		}
		direct(keys, lang, f, redo, cb);
	}
	function serverStatus() {
		xhr("GET", "/__rut/status", null, {}, function (err, txt) {
			if (!err) {
				try { var d = JSON.parse(txt); serverEps = d.eps || null; serverEngine = d.engine || ""; serverWhy = d.why || null; } catch (e) { /* старый скрипт */ }
			}
			showStatus();
		}, 10000);
	}
	function badLang(lang) {
		note(U("badlang_n", { l: lang }));
		problem("badlang", { l: lang });
		var r = recent();
		if (r.indexOf(lang) >= 0) {  // неверный код не держим в списке
			store("rut-live-langs", JSON.stringify(r.filter(function (c) { return c !== lang; })));
			if (sel) { fillSelect(); }
		}
	}

	/* Google из браузера: 19 адресов. Перед игрой проверяем, какие отвечают; запросы идут по кругу на
	   рабочие (разные части пассажа — на разные адреса сразу); неответивший адрес отдыхает. */
	var PA_KEY = "AIzaSyATBXajvzQLTDHEQbcpq0Ihe0vWDHmO520";
	var DEPS = [], RR = 0, probed = false, probing = false;
	function addEp(k, host, max, n) { DEPS.push({ k: k, host: host, max: max, n: n, until: 0, busy: 0, ok: null, i: DEPS.length }); }
	["translate.googleapis.com", "translate.google.com", "clients5.google.com", "translate.google.com.ua", "translate.google.de"]
		.forEach(function (h) { addEp("gtx", h, 4500, 60); });
	addEp("pa", "translate-pa.googleapis.com", 4500, 100);
	["translate.googleapis.com", "clients5.google.com", "translate.google.com"].forEach(function (h) { addEp("gtxt", h, 1500, 25); });
	["clients5.google.com", "translate.googleapis.com", "translate.google.com", "clients1.google.com", "clients2.google.com",
		"clients4.google.com", "clients6.google.com"].forEach(function (h) { addEp("dict", h, 1500, 25); });
	["translate.googleapis.com", "translate.google.com", "clients5.google.com"].forEach(function (h) { addEp("gtxget", h, 1500, 25); });
	function decodeHtml(t) { var ta = document.createElement("textarea"); ta.innerHTML = t; return ta.value; }
	function escHtml(t) { return t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
	function gtxText(txt) {
		var d = JSON.parse(txt);
		return (d[0] || []).map(function (seg) { return seg && typeof seg[0] === "string" ? seg[0] : ""; }).join("");
	}
	function tText(txt) {  // ответ translate_a/t
		var d = JSON.parse(txt);
		if (d && !Array.isArray(d)) { return (d.sentences || []).map(function (x) { return x.trans || ""; }).join(""); }
		var first = d[0];
		return Array.isArray(first) ? String(first[0]) : String(first);
	}
	function callEp(ep, lines, lang, cb) {  // cb(массив переводов | null | "split", код ошибки)
		var q = lines.join("\n"), sl = encodeURIComponent(SRC), tl = encodeURIComponent(lang), T = 20000;
		var base = "https://" + ep.host;
		var lines2 = function (out) {
			var a = out.split("\n");
			return a.length === lines.length ? a : (lines.length > 1 ? "split" : [out.replace(/\n/g, " ")]);
		};
		var done = function (fn) {
			return function (err, txt) {
				if (err) { cb(null, err); return; }
				var r = null;
				try { r = fn(txt); } catch (e) { r = null; }
				cb(r, r ? null : "bad");
			};
		};
		if (ep.k === "gtx") {
			xhr("POST", base + "/translate_a/single?client=gtx&dt=t&sl=" + sl + "&tl=" + tl,
				"q=" + encodeURIComponent(q), { "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8" },
				done(function (txt) { return lines2(gtxText(txt)); }), T);
		} else if (ep.k === "gtxget") {
			xhr("GET", base + "/translate_a/single?client=gtx&dt=t&sl=" + sl + "&tl=" + tl + "&q=" + encodeURIComponent(q),
				null, {}, done(function (txt) { return lines2(gtxText(txt)); }), T);
		} else if (ep.k === "pa") {
			xhr("POST", base + "/v1/translateHtml", JSON.stringify([[lines.map(escHtml), SRC, lang], "wt_lib"]),
				{ "Content-Type": "application/json+protobuf", "X-Goog-API-Key": PA_KEY },
				done(function (txt) {
					var d = JSON.parse(txt)[0];
					if (!d || d.length !== lines.length) { return null; }
					return d.map(function (x) { return decodeHtml(String(x || "").replace(/\s*<br\s*\/?>\s*/gi, " ")); });
				}), T);
		} else {
			xhr("GET", base + "/translate_a/t?client=" + (ep.k === "dict" ? "dict-chrome-ex" : "gtx") + "&sl=" + sl + "&tl=" + tl +
				"&q=" + encodeURIComponent(q), null, {}, done(function (txt) { return lines2(tText(txt)); }), T);
		}
	}
	function runEp(ep, lines, lang, cb) {  // все строки через один адрес, кусками по его размеру
		var chunks = [], cur = [], size = 0, out = [];
		lines.forEach(function (l) {
			if (cur.length && (size + l.length + 1 > ep.max || cur.length >= ep.n)) { chunks.push(cur); cur = []; size = 0; }
			cur.push(l);
			size += l.length + 1;
		});
		if (cur.length) { chunks.push(cur); }
		(function next(i) {
			if (i >= chunks.length) { cb(out); return; }
			callEp(ep, chunks[i], lang, function (r, err) {
				if (r === "split") {  // строки склеились — этот кусок по одной
					var one = [];
					(function each(j) {
						if (j >= chunks[i].length) { out = out.concat(one); next(i + 1); return; }
						callEp(ep, [chunks[i][j]], lang, function (r1, err1) {
							if (!r1 || r1 === "split") { cb(null, err1); return; }
							one.push(r1[0]);
							each(j + 1);
						});
					})(0);
					return;
				}
				if (!r) { cb(null, err); return; }
				out = out.concat(r);
				next(i + 1);
			});
		})(0);
	}
	function alive() { var now = Date.now(); return DEPS.filter(function (e) { return e.ok !== false && e.until <= now; }); }
	function pick(tried) {  // следующий по кругу адрес: сначала проверенные, потом непроверенные, свободные — раньше
		var now = Date.now(), n = DEPS.length, best = null, bestScore = 1e9;
		for (var i = 0; i < n; i++) {
			var e = DEPS[(RR + i) % n];
			if (tried[e.i] || e.until > now) { continue; }
			var score = (e.ok === true ? 0 : e.ok === null ? 100 : 200) + e.busy;
			if (score < bestScore) { best = e; bestScore = score; }
		}
		if (best) { RR = (best.i + 1) % n; }
		return best;
	}
	function reprobe() {  // в фоне: не ответившие адреса — снова «Hello», чтобы список был свежим
		var now = Date.now(), tl = SRC === "ru" ? "en" : "ru";
		DEPS.forEach(function (ep) {
			if (ep.ok !== false || ep.until > now || ep.busy) { return; }
			ep.busy++;
			callEp(ep, ["Hello"], tl, function (r, err) {
				ep.busy--;
				if (r && r !== "split" && r[0] && r[0].trim() && r[0].trim() !== "Hello") { ep.ok = ep.ever = true; ep.until = 0; ep.err = null; }
				else if (err !== 400) { fail(ep, err || "bad"); }
				showStatus();
			});
		});
	}
	function fail(ep, err) {  // неответивший адрес отдыхает: минуту, а если ни разу не ответил — 10 минут
		ep.until = Date.now() + (ep.ever ? 60000 : 600000);
		ep.ok = false;
		ep.err = err;
	}
	var WHY_KEY = { "429": "w429", "403": "w403", net: "wnet", timeout: "wtimeout", bad: "wbad", "5xx": "w5xx", rate: "w429",
		quota: "w403", other: "wother" };
	function whyText(k) { return WHY_KEY[k] ? U(WHY_KEY[k]) : k; }
	function whyKey(err) {
		if (err === 429 || err === 403 || err === "timeout" || err === "bad") { return String(err); }
		if (typeof err === "number") { return err >= 500 ? "5xx" : "other"; }
		return "net";
	}
	function google(lines, lang, cb) {
		var tried = {}, n400 = 0, nerr = 0;
		(function attempt() {
			var ep = pick(tried);
			if (!ep) { cb(null, n400 && n400 === nerr ? "lang" : "down"); return; }
			ep.busy++;
			runEp(ep, lines, lang, function (out, err) {
				ep.busy--;
				if (out) {
					ep.ok = ep.ever = true;
					ep.until = 0;
					ep.err = null;
					problem("");
					cb(out);
					return;
				}
				tried[ep.i] = 1;
				nerr++;
				if (err === 400) { n400++; } else { fail(ep, err); }
				showStatus();
				attempt();
			});
		})();
	}
	function probeAll() {  // какие адреса Google отвечают браузеру (на «Hello»)
		if (probing) { return; }
		probing = true;
		probed = true;
		var left = DEPS.length, tl = SRC === "ru" ? "en" : "ru";
		showStatus();
		DEPS.forEach(function (ep) {
			ep.busy++;
			callEp(ep, ["Hello"], tl, function (r, err) {
				ep.busy--;
				var ok = !!(r && r !== "split" && r[0] && r[0].trim() && r[0].trim() !== "Hello");
				if (ok) { ep.ok = ep.ever = true; ep.until = 0; ep.err = null; } else if (err !== 400) { fail(ep, err || "bad"); }
				if (--left === 0) { probing = false; }
				showStatus();
			});
		});
	}
	function direct(keys, lang, f, redo, cb) {
		if (f) { DEPS.forEach(function (e) { e.until = 0; e.ok = e.ever ? true : null; }); }
		var res = new Array(keys.length);
		(redo ? function (k, fn) { fn([]); } : function (k, fn) { dbGet(lang, k, fn); })(keys, function (cached) {
			var todo = [];
			for (var i = 0; i < keys.length; i++) { if (typeof cached[i] === "string") { res[i] = cached[i]; } else { todo.push(i); } }
			if (!todo.length) { cb(res); return; }
			var pa = paEp(), hIdx = pa ? todo.filter(function (i) { return HINFO[keys[i]] && toHtml(keys[i], HINFO[keys[i]]) !== null; }) : [];
			if (hIdx.length) {  // с тегами — HTML-ом через translate-pa; что не вышло — как обычно, метками
				paHtml(pa, hIdx.map(function (i) { return keys[i]; }), lang, function (out) {
					var put = [], left = [];
					hIdx.forEach(function (i, k) { if (typeof out[k] === "string" && out[k]) { res[i] = out[k]; put.push([keys[i], out[k]]); } else { left.push(i); } });
					dbPut(lang, put);
					var rest = todo.filter(function (i) { return hIdx.indexOf(i) < 0; }).concat(left);
					if (!rest.length) { cb(res); return; }
					plain(rest);
				});
				return;
			}
			plain(todo);
		});
		function plain(todo) {
			google(todo.map(function (i) { return keys[i]; }), lang, function (out, why) {
				if (!out) {
					if (why === "lang") { badLang(lang); } else {
						down(U("gdown_n"));
						problem("gdown");
					}
					cb(res);
					return;
				}
				var put = [];
				todo.forEach(function (i, k) { if (typeof out[k] === "string" && out[k]) { res[i] = out[k]; put.push([keys[i], out[k]]); } });
				dbPut(lang, put);
				cb(res);
			});
		}
	}
	function paEp() {  // адрес translate-pa (HTML), если он сейчас не отдыхает
		var now = Date.now();
		for (var i = 0; i < DEPS.length; i++) { var e = DEPS[i]; if (e.k === "pa" && e.ok !== false && e.until <= now) { return e; } }
		return null;
	}
	function paHtml(ep, keys, lang, cb, sep) {  // cb(массив: перевод в нашем формате | null)
		var out = new Array(keys.length), chunks = [], cur = [], size = 0;
		var done = function () {  // список подписей не вышел (Google перепутал «F-cup» и «FF-cup») — ещё раз, через «|»
			var again = sep ? [] : keys.filter(function (k, i) { return out[i] == null && HINFO[k].g; });
			if (!again.length) { cb(out); return; }
			paHtml(ep, again, lang, function (o2) {
				again.forEach(function (k, j) { out[keys.indexOf(k)] = o2[j]; });
				cb(out);
			}, " | ");
		};
		keys.forEach(function (k, i) {
			var h = toHtml(k, HINFO[k], sep);
			if (cur.length && (size + h.length > ep.max || cur.length >= ep.n)) { chunks.push(cur); cur = []; size = 0; }
			cur.push([i, h]);
			size += h.length + 1;
		});
		if (cur.length) { chunks.push(cur); }
		(function next(c) {
			if (c >= chunks.length) { done(); return; }
			var ch = chunks[c];
			ep.busy++;
			xhr("POST", "https://" + ep.host + "/v1/translateHtml", JSON.stringify([[ch.map(function (x) { return x[1]; }), SRC, lang], "wt_lib"]),
				{ "Content-Type": "application/json+protobuf", "X-Goog-API-Key": PA_KEY }, function (err, txt) {
					ep.busy--;
					var d = null;
					if (!err) { try { d = JSON.parse(txt)[0]; } catch (e) { d = null; } }
					if (!d || d.length !== ch.length) {
						if (err !== 400) { fail(ep, err || "bad"); showStatus(); }
						cb(out);  // остальное — обычным способом
						return;
					}
					ep.ok = ep.ever = true;
					ep.until = 0;
					ch.forEach(function (x, k) { var key = keys[x[0]]; out[x[0]] = fromHtml(d[k], key, HINFO[key]); });
					next(c + 1);
				}, 20000);
		})(0);
	}
	var dbs = Object.create(null);
	function db(lang, cb) {
		if (dbs[lang] === false || typeof indexedDB === "undefined") { cb(null); return; }
		if (dbs[lang]) { cb(dbs[lang]); return; }
		try {
			var rq = indexedDB.open("rut-live-" + SRC + "-" + lang, 1);
			rq.onupgradeneeded = function () { rq.result.createObjectStore("t"); };
			rq.onsuccess = function () { dbs[lang] = rq.result; cb(dbs[lang]); };
			rq.onerror = function () { dbs[lang] = false; cb(null); };
		} catch (e) { dbs[lang] = false; cb(null); }
	}
	function dbGet(lang, keys, cb) {
		db(lang, function (d) {
			var out = [], left = keys.length;
			if (!d || !left) { cb(out); return; }
			try {
				var s = d.transaction("t").objectStore("t");
				keys.forEach(function (k, i) {
					var r = s.get(k);
					r.onsuccess = function () { out[i] = dbVal(r.result); if (--left === 0) { cb(out); } };
					r.onerror = function () { if (--left === 0) { cb(out); } };
				});
			} catch (e) { cb([]); }
		});
	}
	function dbVal(x) { return typeof x === "string" ? x : (x && typeof x.v === "string" ? x.v : undefined); }
	function dbAll(lang, cb, since) {  // все переводы этого браузера (since — только новее этого времени)
		db(lang, function (d) {
			if (!d) { cb(null); return; }
			try {
				var o = {}, rq = d.transaction("t").objectStore("t").openCursor();
				rq.onsuccess = function () {
					var c = rq.result;
					if (c) {
						var v = dbVal(c.value), t = c.value && c.value.t ? c.value.t : 0;
						if (typeof v === "string" && (since === undefined || t > since)) { o[c.key] = v; }
						c["continue"]();
					} else { cb(o); }
				};
				rq.onerror = function () { cb(o); };
			} catch (e) { cb(null); }
		});
	}
	function dbPut(lang, pairs) {
		db(lang, function (d) {
			if (!d || !pairs.length) { return; }
			try {
				var s = d.transaction("t", "readwrite").objectStore("t"), now = Date.now();
				pairs.forEach(function (p) { s.put({ v: p[1], t: now }, p[0]); });
			} catch (e) { /* без кэша */ }
		});
	}

	/* --- интерфейс SugarCube (Сохранения, Настройки ...) на выбранном языке --- */
	var L10N = null;
	try { L10N = typeof l10nStrings !== "undefined" ? l10nStrings : null; } catch (e) { L10N = null; }
	var ORIG_UI = L10N ? Object.assign({}, L10N) : null, UI_MAPS = Object.create(null), OURS = {};
	Object.keys(C.ui || {}).forEach(function (lang) { if (C.ui[lang] && typeof C.ui[lang] === "object") { UI_MAPS[lang] = C.ui[lang]; } });
	function uiViaTranslator(lang, cb) {  // меню SugarCube через тот же переводчик (запоминается, как и текст)
		var keys = Object.keys(ORIG_UI).filter(function (k) { return typeof ORIG_UI[k] === "string" && LAT.test(ORIG_UI[k]); });
		var phs = [];
		var texts = keys.map(function (k) {
			var p = [];
			phs.push(p);
			return ORIG_UI[k].replace(/\{\w+\}/g, function (m) { p.push(m); return "\u27E6" + (p.length - 1) + "\u27E7"; });
		});
		backend(texts, lang, false, false, function (res) {
			var map = {}, n = 0;
			keys.forEach(function (k, i) {
				var r = res && res[i], ok = true;
				if (typeof r !== "string" || !r) { return; }
				r = r.replace(/[\u27E6\[]\s*(\d+)\s*[\u27E7\]]/g, function (m, d) {
					if (phs[i][+d] === undefined) { ok = false; return ""; }
					return phs[i][+d];
				});
				if (ok && !/[\u27E6\u27E7]/.test(r)) { map[k] = r; n++; }
			});
			cb(n ? map : null);
		});
	}
	function relabel() {
		if (!L10N) { return; }
		var m = { "menu-item-saves": "savesTitle", "menu-item-settings": "settingsTitle", "menu-item-restart": "restartTitle", "menu-item-share": "shareTitle" };
		Object.keys(m).forEach(function (id) {
			var a = document.querySelector("#" + id + " a");
			if (a && L10N[m[id]]) { quiet(function () { a.textContent = L10N[m[id]]; }); }
		});
	}
	function applyUI(lang) {
		if (!L10N || !ORIG_UI) { return; }
		var setMap = function (map) {
			Object.keys(L10N).forEach(function (k) {  // строки, которые игра поменяла сама, не трогаем
				if (HAS.call(OURS, k) && L10N[k] !== OURS[k]) { ORIG_UI[k] = L10N[k]; OURS[k] = "\u0000"; }
			});
			Object.keys(ORIG_UI).forEach(function (k) { if (OURS[k] !== "\u0000") { L10N[k] = ORIG_UI[k]; OURS[k] = L10N[k]; } });
			if (map) { Object.keys(map).forEach(function (k) { if (OURS[k] !== "\u0000" && typeof map[k] === "string") { L10N[k] = OURS[k] = map[k]; } }); }
			relabel();
		};
		if (lang === "off") { setMap(null); return; }
		if (UI_MAPS[lang]) { setMap(UI_MAPS[lang]); return; }
		var got = function (map) {
			if (map) { UI_MAPS[lang] = map; }
			if (lang === LANG) { setMap(map); }
		};
		if (!serverMode()) { uiViaTranslator(lang, got); return; }
		xhr("GET", "/__rut/ui?lang=" + encodeURIComponent(lang), null, {}, function (err, txt) {
			var map = null;
			if (!err) { try { map = JSON.parse(txt).ui; } catch (e) { map = null; } }
			if (map && !Object.keys(map).length) { map = null; }
			if (!map && err) { uiViaTranslator(lang, got); return; }
			got(map);
		});
	}

	/* --- смена языка и ручное обновление --- */
	function setLang(lang) {
		if (lang === LANG) { return; }
		LANG = lang;
		gen++;
		store("rut-live-lang", lang);
		overlayDb(lang);
		sendQ = [];
		waiting = Object.create(null);
		pendingPassage = 0;
		setWait(false);
		if (lang === "off" || UI_MAPS[lang]) { applyUI(lang); }
		else { setTimeout(function () { if (LANG === lang) { applyUI(lang); } }, 700); }  // сначала текст, потом меню
		RECS = RECS.filter(recLive);
		RECS.forEach(showRec);  // то, что уже на экране, — сразу на новый язык
		allRoots();
		panelSync();
		relabelLater();  // панель — на языке, который теперь на экране
		badge();
	}
	function recLive(r) { return r.node ? r.node.isConnected : r.nodes.some(function (n) { return n.isConnected; }); }
	function showRec(rec) {  // переведённое место на экране → на текущий язык (сразу или когда придёт перевод)
		var lang = LANG;
		if (rec.node) {
			if (lang === "off") { quiet(function () { applyNode(rec.node, rec.k, null, "off", true); }); rec.lang = "off"; return; }
			if (known(rec.k.key)) {
				var v = mem()[rec.k.key];
				if (v !== null) { quiet(function () { applyNode(rec.node, rec.k, v, lang, true); }); rec.lang = lang; }
			} else { need(rec.k.key, { nrec: rec }); }
			return;
		}
		if (lang === "off") { quiet(function () { if (reapply(rec, null, "off")) { rec.lang = "off"; } }); return; }
		if (rec.group) {  // подпись из группы — переводим вместе с группой (с подсказкой)
			if (known(rec.group.key)) { if (mem()[rec.group.key] !== null) { finish({ grec: rec }, mem()[rec.group.key]); } }
			else { need(rec.group.key, { grec: rec }); }
			return;
		}
		var K = keyInfo(rec.st, lang).key, t = trFor(rec.st, lang);
		if (t !== undefined) {
			quiet(function () { if (reapply(rec, t[0], lang)) { rec.lang = lang; rec.kk = t[1]; } });
			if (t[1] !== K && !known(K)) { need(K, { rec: rec, k: K }); }  // с правильными формами чисел — следом
			return;
		}
		if (!known(K)) { need(K, { rec: rec, k: K }); }
		else if (K !== rec.key && !known(rec.key)) { need(rec.key, { rec: rec, k: rec.key }); }  // с числами не вышло
	}
	function redoPage() {  // «Перевести страницу заново»: всё переведённое на экране — ещё раз, по одной фразе
		if (LANG === "off") { note(U("orig_first")); return; }
		var seen = Object.create(null), n = 0, blocks = [];
		RECS.forEach(function (rec) {
			if (n >= 150 || !recLive(rec) || rec.lang !== LANG) { return; }
			if (rec.node && !isManual(LANG, rec.k.key)) {
				/* кусок фразы, которая раньше развалилась на отдельные слова («Perky» → «Весёлый»):
				   возвращаем оригинал и переводим всю фразу целиком заново */
				var t = rec.node;
				quiet(function () { t.nodeValue = rec.k.orig; });
				DONE["delete"](t);
				rec.dead = true;
				var b = t.parentNode;
				while (b && b.parentNode && b.nodeType === 1 && !isBlock(b) && !(b.matches && b.matches(ROOT_SEL))) { b = b.parentNode; }
				if (b && blocks.indexOf(b) < 0) { blocks.push(b); }
				return;
			}
			var key = rec.node ? rec.k.key : rec.group ? rec.group.key : (rec.kk || rec.key);
			if (isManual(LANG, key)) { return; }  // исправлено вручную
			if (seen[key]) { if (rec.group) { need(key, { grec: rec }); } return; }
			if (waiting[key]) { return; }  // уже переводится прямо сейчас
			seen[key] = 1;
			n++;
			REDO[key] = 1;
			need(key, rec.node ? { nrec: rec } : rec.group ? { grec: rec } : { rec: rec, k: key });
		});
		RECS = RECS.filter(function (r) { return !r.dead; });
		redoRuns = true;
		redoRunsN = 0;
		try { blocks.forEach(function (b) { translateRoot(b, false); }); } finally { redoRuns = false; }
		n += redoRunsN;
		if (!n) { note(U("none_screen")); return; }
		redoLeft += n;
		redoTotal = n;
		redoChanged = 0;
		note(U("redo_n", { n: n }));
	}
	function retryRecs() {  // места, оставшиеся на прошлом языке из-за обрыва связи
		if (LANG === "off") { return; }
		RECS.forEach(function (rec) { if (rec.lang !== LANG && recLive(rec)) { showRec(rec); } });
	}
	function refresh() {  // «Обновить перевод»: повторить то, что не пришло, прямо сейчас
		var M = mem(), F = fails();
		Object.keys(F).forEach(function (k) { delete F[k]; if (M[k] === null) { delete M[k]; } });
		serverDownUntil = 0;
		DEPS.forEach(function (e) { e.until = 0; });
		problem("");
		if (SERVER) { serverStatus(); } else { probeAll(); }
		if (LANG !== "off" && !UI_MAPS[LANG]) { applyUI(LANG); }
		force = true;
		noteText = "";
		var before = sendQ.length;
		retryRecs();
		allRoots();
		if (sendQ.length === before && !Object.keys(waiting).length) { note(LANG === "off" ? U("orig_shown") : U("all_done")); force = false; }
		else { badge(); }
	}
	setInterval(function () {  // автоматически: раз в минуту пробуем то, что не перевелось
		if (LANG === "off" || document.hidden) { return; }
		var F = fails();
		if (Object.keys(F).length) { retryRecs(); allRoots(); }
	}, 60000);

	/* --- «✎ Исправить фразу»: свой вариант перевода (запоминается и попадает в «Сохранить переводы в файл») --- */
	var MANUAL = Object.create(null);  // язык → { ключ: 1 } — исправлено вручную: «Перевести заново» не трогает
	function manualMap(lang) {
		if (MANUAL[lang]) { return MANUAL[lang]; }
		var m = MANUAL[lang] = Object.create(null);
		try { (JSON.parse(store("rut-live-manual-" + SRC + "-" + lang) || "[]") || []).forEach(function (k) { if (typeof k === "string") { m[k] = 1; } }); } catch (e) { /* пусто */ }
		(EMBED_MANUAL[lang] || []).forEach(function (k) { if (typeof k === "string") { m[k] = 1; } });
		return m;
	}
	function setManual(lang, key, on) {
		var m = manualMap(lang);
		if (on) { m[key] = 1; } else { delete m[key]; }
		var own = [];
		try { own = JSON.parse(store("rut-live-manual-" + SRC + "-" + lang) || "[]") || []; } catch (e) { own = []; }
		own = own.filter(function (k) { return k !== key; });
		if (on) { own.push(key); }
		store("rut-live-manual-" + SRC + "-" + lang, JSON.stringify(own.slice(-3000)));
	}
	function isManual(lang, key) { return !!manualMap(lang)[key]; }
	function toStand(text, info) {  // перевод с метками → с числами-заместителями (для ключа с числами)
		if (!info.map) { return text; }
		var rev = Object.create(null);
		Object.keys(info.map).forEach(function (n) { rev[info.map[n]] = n; });
		return text.replace(/⟦(\d+)⟧/g, function (m, i) { return HAS.call(rev, i) ? rev[i] : m; });
	}
	var editMode = false, editBanner = null, editBox = null;
	function nodeRec(t) {
		for (var i = RECS.length - 1; i >= 0; i--) { if (RECS[i].node === t) { return RECS[i]; } }
		return null;
	}
	function recAt(ev) {  // переведённая фраза под пальцем / курсором
		var node = null, rec = null;
		try {
			if (document.caretPositionFromPoint) { var cp = document.caretPositionFromPoint(ev.clientX, ev.clientY); node = cp && cp.offsetNode; }
			else if (document.caretRangeFromPoint) { var cr = document.caretRangeFromPoint(ev.clientX, ev.clientY); node = cr && cr.startContainer; }
		} catch (e) { node = null; }
		if (node && node.nodeType === 3) { rec = ORIG_OF.get(node) || nodeRec(node); }
		if (!rec && ev.target && ev.target.nodeType === 1) {
			var w = document.createTreeWalker(ev.target, 4 /* текст */);
			for (var t = w.nextNode(); t && !rec; t = w.nextNode()) { rec = ORIG_OF.get(t) || nodeRec(t); }
		}
		return rec && recLive(rec) && rec.lang === LANG ? rec : null;
	}
	function editStop() {
		editMode = false;
		if (editBanner && editBanner.parentNode) { quiet(function () { editBanner.parentNode.removeChild(editBanner); }); }
	}
	function editStart() {
		if (LANG === "off") { note(U("orig_first")); return; }
		if (editMode) { editStop(); return; }
		editMode = true;
		if (!editBanner) {
			editBanner = document.createElement("div");
			editBanner.className = "rut-edit rut-edit-banner notranslate";
			editBanner.setAttribute("translate", "no");
			editBanner.setAttribute("style", "position:fixed;left:50%;bottom:10px;transform:translateX(-50%);z-index:2147483001;" +
				"background:#2a3560;color:#fff;font:14px/1.4 sans-serif;padding:7px 12px;border-radius:6px;box-shadow:0 2px 10px rgba(0,0,0,.5);" +
				"max-width:92vw;text-align:center");
			var t = document.createElement("span");
			lab(t, "tap", "textContent", "\u270E ");
			var x = document.createElement("button");
			x.type = "button";
			lab(x, "cancel");
			x.setAttribute("style", "margin-left:6px;font:inherit;padding:2px 8px");
			x.addEventListener("click", function (ev) { ev.stopPropagation(); editStop(); });
			editBanner.appendChild(t);
			editBanner.appendChild(x);
		}
		quiet(function () { document.body.appendChild(editBanner); });
	}
	function ours(t) {  // наши окна и кнопка «свернуть боковую панель» SugarCube — нажимаются как обычно
		return !!(t && t.closest && t.closest(".rut-panel, .rut-edit, .rut-badge, .rut-float, #ui-bar-tray, #ui-bar-toggle"));
	}
	["mousedown", "pointerdown", "touchstart", "mouseup", "pointerup", "touchend"].forEach(function (type) {
		window.addEventListener(type, function (ev) {  // в режиме исправления нажатие не должно уходить в игру
			if (editMode && !ours(ev.target)) { ev.stopPropagation(); ev.stopImmediatePropagation(); }
		}, true);
	});
	window.addEventListener("click", function (ev) {
		if (!editMode || ours(ev.target)) { return; }
		ev.preventDefault();
		ev.stopPropagation();
		ev.stopImmediatePropagation();
		var rec = recAt(ev);
		if (!rec) { note(U("no_here")); return; }
		editStop();
		openEditor(rec);
	}, true);
	function editInfo(rec) {  // что показывать и как сохранять
		var lang = LANG, M = mem();
		if (rec.node) {
			return { src: rec.k.key, cur: typeof M[rec.k.key] === "string" ? M[rec.k.key] : rec.node.nodeValue.trim(), key: rec.k.key, kind: "node" };
		}
		if (rec.group) {
			var G = M[rec.group.key], parts = groupParts(G, rec.group.n, rec.group.hint, rec.group.key);
			if (!parts) { return null; }
			var inner = rec.key.replace(/^⟦0⟧([\s\S]*)⟦1⟧$/, "$1");
			return { src: inner, cur: parts[rec.group.i], key: rec.group.key, kind: "group", parts: parts, G: G };
		}
		var info = keyInfo(rec.st, lang), t = trFor(rec.st, lang);
		return { src: rec.key, cur: t ? t[0] : "", key: info.key, kind: "run", info: info };
	}
	function preview(rec, text, kind) {  // как фраза будет выглядеть (метки — ссылки, выделение, числа)
		if (kind === "group") { return text; }
		if (kind === "node") {
			return text.replace(/⟦\s*(\d+)\s*⟧/g, function (m, i) { return rec.k.nums[+i] !== undefined ? rec.k.nums[+i] : m; });
		}
		var toks = parse(text, rec.st);
		if (!toks) { return null; }
		return toks.map(function (tk) {
			if (tk.t !== undefined) { return tk.t; }
			var it = rec.st.items[tk.id];
			if (it.lz) { return ""; }
			if (it.text !== undefined) { return it.text; }
			if (it.node) { return it.node.textContent; }
			return it.open ? "[" : "]";
		}).join("");
	}
	function saveManual(rec, e, text, remove) {
		var lang = LANG, M = mem();
		if (remove) {  // вернуть перевод Google: заново, по одной фразе
			setManual(lang, e.key, false);
			if (SERVER) { xhr("POST", "/__rut/manual", JSON.stringify({ lang: lang, key: e.key, remove: true }), { "Content-Type": "application/json" }, function () { }, 15000); }
			RETRY[e.key] = 1;  // мимо кэша, по одной фразе
			need(e.key, e.kind === "node" ? { nrec: rec } : e.kind === "group" ? { grec: rec } : { rec: rec, k: e.key });
			return;
		}
		var val = text;
		if (e.kind === "run") { val = toStand(text, e.info); }
		if (e.kind === "group") {
			var parts = e.parts.slice(), m = e.G.match(/[⟦\[]\s*98\s*[⟧\]]/);
			parts[rec.group.i] = text.replace(/[⟦⟧|]/g, " ").replace(/\s+/g, " ").trim();
			val = (rec.group.hint && m ? e.G.slice(0, m.index + m[0].length) + " " : "") + parts.join(" | ");
		}
		M[e.key] = val;
		delete fails()[e.key];
		setManual(lang, e.key, true);
		if (SERVER) { xhr("POST", "/__rut/manual", JSON.stringify({ lang: lang, key: e.key, value: val }), { "Content-Type": "application/json" }, function () { }, 15000); }
		else { dbPut(lang, [[e.key, val]]); }
		RECS.forEach(function (r) {  // эта же фраза везде на экране
			if (!recLive(r)) { return; }
			var k = r.node ? r.k.key : r.group ? r.group.key : keyInfo(r.st, lang).key;
			if (k === e.key) { r.lang = null; showRec(r); }
		});
		note(U("fix_saved"));
	}
	function openEditor(rec) {
		var e = editInfo(rec);
		if (!e) { note(U("cant_fix")); return; }
		if (editBox && editBox.parentNode) { editBox.parentNode.removeChild(editBox); }
		var box = editBox = document.createElement("div");
		box.className = "rut-edit notranslate";
		box.setAttribute("translate", "no");
		box.setAttribute("style", "position:fixed;inset:0;z-index:2147483002;background:rgba(0,0,0,.55);display:flex;align-items:center;" +
			"justify-content:center;font:14px/1.4 sans-serif;color:#eee");
		var win = document.createElement("div");
		win.setAttribute("style", "background:#1d2133;border:1px solid #4a5590;border-radius:8px;padding:12px;width:min(36em,94vw);" +
			"box-sizing:border-box;max-height:90vh;overflow-y:auto;overflow-x:hidden;box-shadow:0 4px 24px rgba(0,0,0,.6)");
		var h = function (txt, st) { var d = document.createElement("div"); d.textContent = txt; d.setAttribute("style", st || ""); win.appendChild(d); return d; };
		h(U("fix_title"), "font-weight:bold;margin-bottom:6px");
		h(U("orig_lbl"), "font-size:.85em;opacity:.7");
		h(e.src.replace(/\s+/g, " ").trim(), "white-space:pre-wrap;overflow-wrap:anywhere;background:#262b42;padding:5px 7px;" +
			"border-radius:4px;margin-bottom:8px;user-select:text");
		h(U("tr_lbl"), "font-size:.85em;opacity:.7");
		var ta = document.createElement("textarea");
		ta.value = e.cur;
		ta.setAttribute("rows", String(Math.min(8, Math.max(2, Math.ceil(e.cur.length / 50)))));
		ta.setAttribute("style", "display:block;width:100% !important;max-width:100% !important;min-width:0 !important;" +
			"box-sizing:border-box !important;white-space:pre-wrap;overflow-wrap:anywhere;font:16px/1.4 sans-serif;color:#111;" +
			"background:#f4f4f4;border-radius:4px;padding:5px;margin:0");
		win.appendChild(ta);
		if (/⟦/.test(e.src) || /⟦/.test(e.cur)) {
			h(U("marks_hint"), "font-size:.78em;opacity:.75;margin-top:4px");
		}
		var pv = h("", "font-size:.85em;margin-top:6px;padding:5px 7px;border-left:3px solid #5a6aa0;white-space:pre-wrap");
		var upd = function () {
			var r = preview(rec, ta.value, e.kind);
			pv.textContent = r === null ? U("marks_bad") : U("will_be", { t: r });
			pv.style.color = r === null ? "#e0a040" : "";
			return r !== null;
		};
		ta.addEventListener("input", upd);
		var row = document.createElement("div");
		row.setAttribute("style", "display:flex;gap:6px;justify-content:flex-end;flex-wrap:wrap;margin-top:10px");
		var btn = function (txt, fn, main) {
			var b = document.createElement("button");
			b.type = "button";
			b.textContent = txt;
			b.setAttribute("style", "font:inherit;padding:4px 10px;border-radius:4px;border:1px solid #5a6aa0;color:#fff;background:" + (main ? "#3a5ad0" : "#3a4a7a"));
			b.addEventListener("click", function (ev) { ev.stopPropagation(); fn(); });
			row.appendChild(b);
		};
		var close = function () { quiet(function () { if (box.parentNode) { box.parentNode.removeChild(box); } }); };
		if (isManual(LANG, e.key)) { btn(U("google_back"), function () { close(); saveManual(rec, e, null, true); }); }
		btn(U("cancel"), close);
		btn(U("save"), function () {
			if (!upd() || !ta.value.trim()) { return; }
			close();
			quiet(function () { saveManual(rec, e, ta.value.trim(), false); });
		}, true);
		win.appendChild(row);
		box.appendChild(win);
		["keydown", "keyup", "keypress"].forEach(function (t) { box.addEventListener(t, function (ev) { ev.stopPropagation(); if (t === "keydown" && ev.key === "Escape") { close(); } }); });
		box.addEventListener("click", function (ev) { if (ev.target === box) { close(); } });
		quiet(function () { document.body.appendChild(box); });
		upd();
		try { ta.focus(); } catch (err) { /* телефон */ }
	}

	/* --- панель в боковом меню: язык, «Обновить перевод», состояние; значок «Перевод…» --- */
	var panel = null, sel = null, statEl = null, custBox = null, custIn = null, probKey = "", probVars = null, whyBox = null, whyEl = null;
	function problem(k, vars) { probKey = k || ""; probVars = vars || null; showStatus(); }  // ключ подписи: язык панели может смениться
	function epsText() {  // [текст, всё ли хорошо]
		if (serverMode()) {
			var t = U("via_srv");
			if (serverEps) { t += " \u00b7 " + U("eps", { a: serverEps[0], b: serverEps[1] }); }
			else if (serverEngine && serverEngine !== "free" && serverEngine !== "google") { t += " \u00b7 " + U("srv_eng", { e: serverEngine }); }
			return [t, !serverEps || serverEps[0] > 0];
		}
		if (!probed) { return [U("not_probed"), true]; }
		var now = Date.now(), ok = DEPS.filter(function (e) { return e.ok === true && e.until <= now; }).length;
		if (probing && !ok) { return [U("probing"), true]; }
		return [U("eps", { a: ok, b: DEPS.length }) + (probing ? "…" : ""), ok > 0 || probing];
	}
	function whyLines() {  // почему не отвечают: по причинам, с адресами
		var groups = {}, order = [], now = Date.now(), lines = [];
		if (serverMode()) {
			Object.keys(serverWhy || {}).forEach(function (k) {
				if (serverWhy[k] > 0) { lines.push("\u2022 " + whyText(k) + ": " + serverWhy[k]); }
			});
			return lines;
		}
		DEPS.forEach(function (e) {
			if (e.ok !== false) { return; }
			var k = whyKey(e.err);
			if (!groups[k]) { groups[k] = []; order.push(k); }
			groups[k].push(e);
		});
		order.forEach(function (k) {
			var list = groups[k], wait = Math.max(0, Math.min.apply(null, list.map(function (e) { return e.until; })) - now);
			lines.push("\u2022 " + whyText(k) + ": " + list.length +
				(wait > 0 ? " (" + U("retry_in", { m: Math.ceil(wait / 60000) }) + ")" : ""));
			lines.push("   " + list.map(function (e) { return e.host.replace(/^translate\./, "") + " " + e.k; }).join(", "));
		});
		return lines;
	}
	function showStatus() {
		if (!statEl) { return; }
		var wl = whyLines(), wt = wl.join("\n"), ee = epsText();
		var probText = probKey ? U(probKey, probVars) : "";
		pillBad = !ee[1] || !!probText;
		pillSync();
		if (whyBox && (whyEl.textContent !== wt || (whyBox.style.display === "none") !== !wt)) {
			quiet(function () { whyEl.textContent = wt; whyBox.style.display = wt ? "" : "none"; });
		}
		var e = epsText(), t = e[0] + (probText ? "\n" + probText : ""), bad = !e[1] || !!probText;
		if (statEl.textContent !== t || statEl.getAttribute("data-ok") !== String(!bad)) {
			quiet(function () {
				statEl.textContent = t;
				statEl.setAttribute("data-ok", String(!bad));
				statEl.style.color = bad ? "#e0a040" : "";
			});
		}
	}
	function recent() {
		try { return (JSON.parse(store("rut-live-langs") || "[]") || []).filter(function (c) { return LANG_RE.test(c); }); } catch (e) { return []; }
	}
	function remember(code) {  // выбранные «другие» языки — наверх списка
		if (code === "off" || code === "+" || FAV.indexOf(code) >= 0) { return; }
		var r = recent().filter(function (c) { return c !== code; });
		r.unshift(code);
		store("rut-live-langs", JSON.stringify(r.slice(0, 8)));
	}
	function nativeName(code) { var g = GL[code.toLowerCase()]; return g ? g[2] : code; }
	function fillSelect() {
		quiet(function () {
			while (sel.firstChild) { sel.removeChild(sel.firstChild); }
			var opt = function (parent, code, text) {
				var o = document.createElement("option");
				o.value = code;
				o.textContent = text;
				parent.appendChild(o);
			};
			opt(sel, "off", langName("off"));
			var favs = recent().concat(FAV), seen = { off: 1 };
			Object.keys(EMBED).concat([C.lang, LANG]).forEach(function (l) { if (l && favs.indexOf(l) < 0) { favs.unshift(l); } });
			var g1 = document.createElement("optgroup");
			g1.label = U("fav");
			favs.forEach(function (code) {
				if (seen[code] || code === SRC || !LANG_RE.test(code)) { return; }
				seen[code] = 1;
				opt(g1, code, nativeName(code) + " (" + code + ")");
			});
			sel.appendChild(g1);
			var g2 = document.createElement("optgroup");
			g2.label = U("all");
			var ru = uiBase() === "ru";
			GLANGS.slice().sort(function (a, b) { return ru ? a[1].localeCompare(b[1], "ru") : a[2].localeCompare(b[2]); }).forEach(function (x) {
				if (x[0] !== SRC) { opt(g2, x[0], langName(x[0]) + " (" + x[0] + ")"); }
			});
			sel.appendChild(g2);
			opt(sel, "+", "\uFF0B " + U("own"));
			sel.value = LANG;
		});
	}
	function normCode(t) {  // «hy», «Армянский», «Հայերեն», «sr-Latn» → код языка
		t = String(t || "").trim();
		if (!t) { return ""; }
		var low = t.toLowerCase();
		if (GL[low]) { return GL[low][0]; }
		for (var i = 0; i < GLANGS.length; i++) {
			if (GLANGS[i][1].toLowerCase() === low || GLANGS[i][2].toLowerCase() === low) { return GLANGS[i][0]; }
		}
		if (!LANG_RE.test(t)) { return ""; }
		var p = t.split("-");
		return p[0].toLowerCase() + (p[1] ? "-" + p[1] : "");
	}
	function customOk() {
		var code = normCode(custIn.value);
		if (!code || code === SRC) {
			custIn.style.outline = "2px solid #e0a040";
			custIn.value = "";
			custIn.placeholder = U("code_bad");
			return;
		}
		custIn.style.outline = "";
		custBox.style.display = "none";
		remember(code);
		setLang(code);
		fillSelect();
	}
	function exportAll() {  // «Сохранить переводы в файл»: всё, что этот браузер перевёл сам (для --import на ПК)
		var prefix = "rut-live-" + SRC + "-", out = { format: "sugarcube_translate-live", version: 1, src: SRC, game: document.title, langs: {} };
		var finish = function () {
			var n = 0;
			Object.keys(out.langs).forEach(function (l) { n += Object.keys(out.langs[l]).length; });
			if (!n) { note(U("nothing_save")); return; }
			var name = (document.title || "game").replace(/[\\\/:*?"<>|]+/g, "_").slice(0, 60) + " - " + U("file_name") + ".json";
			try {
				var blob = new Blob([JSON.stringify(out)], { type: "application/json" });
				var a = document.createElement("a");
				a.href = URL.createObjectURL(blob);
				a.download = name;
				a.style.display = "none";
				document.body.appendChild(a);
				a.click();
				setTimeout(function () { URL.revokeObjectURL(a.href); if (a.parentNode) { a.parentNode.removeChild(a); } }, 5000);
				note(U("saved_n", { n: n, f: name }));
			} catch (e) { note(U("save_fail")); }
		};
		var withLangs = function (cb) {
			var fallback = function () { cb(Object.keys(MEMS)); };
			try {
				if (typeof indexedDB !== "undefined" && indexedDB.databases) {
					indexedDB.databases().then(function (list) {
						cb(list.map(function (d) { return d.name || ""; }).filter(function (n) { return n.indexOf(prefix) === 0; })
							.map(function (n) { return n.slice(prefix.length); }));
					}, fallback);
					return;
				}
			} catch (e) { /* старый браузер */ }
			fallback();
		};
		withLangs(function (list) {
			list = list.filter(function (l) { return l !== "off" && LANG_RE.test(l); });
			var left = list.length;
			if (!left) { finish(); return; }
			list.forEach(function (lang) {
				dbAll(lang, function (obj) {
					if (obj && Object.keys(obj).length) {
						out.langs[lang] = obj;
						var man = Object.keys(manualMap(lang)).filter(function (k) { return HAS.call(obj, k); });
						if (man.length) { (out.manual || (out.manual = {}))[lang] = man; }
					}
					if (--left === 0) { finish(); }
				});
			});
		});
	}
	function barHost() {  // стандартная боковая панель SugarCube, если она есть и видна
		var host = document.getElementById("ui-bar-body");
		return host && host.getClientRects().length ? host : null;
	}
	function mkButton(icon, k, tk, fn) {  // подпись и подсказка — ключи UIS (меняются вместе с языком)
		var btn = document.createElement("button");
		btn.type = "button";
		lab(btn, k, "textContent", icon);
		lab(btn, tk, "title");
		btn.setAttribute("style", "width:100%;font-size:.9em;margin-top:.25em");
		btn.addEventListener("click", fn);
		return btn;
	}
	/* значок «🌐 RU» в правом верхнем углу; по нажатию раскрывается та же панель */
	var wrap = null, pill = null, pillTxt = null, pillDot = null, pillBad = false, pillRe = null;
	function stopKeys(ev) { ev.stopPropagation(); }  // клавиши в панели не должны уходить в игру (горячие клавиши)
	function makeFloat() {
		wrap = document.createElement("div");
		wrap.className = "rut-panel rut-float notranslate";
		wrap.setAttribute("translate", "no");
		wrap.setAttribute("style", "position:fixed;top:6px;right:6px;z-index:2147483000;display:flex;flex-direction:column;" +
			"align-items:flex-end;font:12px/1.35 sans-serif;color:#eee");
		pill = document.createElement("div");
		pill.setAttribute("role", "button");
		pill.setAttribute("tabindex", "0");
		lab(pill, "pill_t", "title");
		pill.setAttribute("style", "cursor:pointer;user-select:none;background:rgba(18,18,24,.88);border:1px solid rgba(255,255,255,.28);" +
			"border-radius:12px;padding:2px 9px;display:flex;align-items:center;gap:6px");
		pillDot = document.createElement("span");
		pillDot.setAttribute("style", "width:8px;height:8px;border-radius:50%;background:#888;display:inline-block");
		pillTxt = document.createElement("span");
		pill.appendChild(pillDot);
		pill.appendChild(pillTxt);
		var toggle = function (ev) {
			ev.preventDefault();
			ev.stopPropagation();
			floatOpen(panel.style.display === "none");
		};
		pill.addEventListener("click", toggle);
		pill.addEventListener("keydown", function (ev) { if (ev.key === "Enter" || ev.key === " ") { toggle(ev); } });
		var head = document.createElement("div");  // «⟳ Обновить» — прямо рядом со значком, без раскрытия панели
		head.setAttribute("style", "display:flex;align-items:center;gap:4px");
		pillRe = document.createElement("div");
		pillRe.setAttribute("role", "button");
		pillRe.setAttribute("tabindex", "0");
		pillRe.textContent = "\u27F3";
		lab(pillRe, "refresh_t", "title");
		pillRe.setAttribute("style", "cursor:pointer;user-select:none;background:rgba(18,18,24,.88);border:1px solid rgba(255,255,255,.28);" +
			"border-radius:12px;padding:2px 8px;font-size:13px;line-height:1.35");
		var re = function (ev) { ev.preventDefault(); ev.stopPropagation(); refresh(); };
		pillRe.addEventListener("click", re);
		pillRe.addEventListener("keydown", function (ev) { if (ev.key === "Enter" || ev.key === " ") { re(ev); } });
		head.appendChild(pillRe);
		head.appendChild(pill);
		wrap.appendChild(head);
		wrap.addEventListener("keydown", stopKeys);
		wrap.addEventListener("keyup", stopKeys);
	}
	function floatOpen(open) {
		if (!panel || !wrap) { return; }
		quiet(function () { panel.style.display = open ? "" : "none"; });
		store("rut-live-open", open ? "1" : "0");
		pillSync();
	}
	function pillSync() {
		if (!pillTxt) { return; }
		var t = "\uD83C\uDF10 " + (LANG === "off" ? SRC.toUpperCase() + " (" + U("orig_short") + ")" : LANG) +
			(panel && panel.style.display !== "none" ? " \u25B4" : " \u25BE");
		var c = pillBad ? "#e0a040" : (LANG === "off" ? "#888" : "#5c5");
		if (pillTxt.textContent !== t || pillDot.style.background !== c) {
			quiet(function () { pillTxt.textContent = t; pillDot.style.background = c; });
		}
		if (pillRe) {
			var d = LANG === "off" ? "none" : "", st = d + (pillBad ? "1" : "0");
			if (pillRe.getAttribute("data-st") !== st) {
				quiet(function () {
					pillRe.setAttribute("data-st", st);
					pillRe.style.display = d;
					pillRe.style.background = pillBad ? "rgba(184,101,12,.9)" : "rgba(18,18,24,.88)";
				});
			}
		}
	}
	function makePanel() {
		if (!document.body) { return; }
		showStatus();
		var host = FLOAT ? null : barHost();
		if (!host && !wrap) { makeFloat(); }
		if (panel && panel.isConnected && (host ? panel.parentNode === host : (panel.parentNode === wrap && wrap.parentNode === document.body))) {
			return;
		}
		if (!panel) {
			panel = document.createElement("div");
			panel.className = "rut-panel notranslate";
			panel.setAttribute("translate", "no");
			var label = document.createElement("div");
			lab(label, "label");
			label.setAttribute("style", "font-size:.8em;opacity:.7;margin-bottom:.2em");
			sel = document.createElement("select");
			sel.setAttribute("style", "width:100%;font-size:.9em");
			panel.addEventListener("keydown", stopKeys);
			panel.addEventListener("keyup", stopKeys);
			sel.addEventListener("change", function () {
				if (sel.value === "+") {  // свой язык: поле для кода
					sel.value = LANG;
					custBox.style.display = "flex";
					custIn.focus();
					return;
				}
				remember(sel.value);
				setLang(sel.value);
			});
			custBox = document.createElement("div");
			custBox.setAttribute("style", "display:none;gap:.25em;margin-top:.25em");
			custIn = document.createElement("input");
			custIn.type = "text";
			lab(custIn, "code_ph", "placeholder");
			custIn.setAttribute("style", "flex:1;min-width:0;font-size:.9em");
			custIn.addEventListener("keydown", function (ev) {
				if (ev.key === "Enter") { ev.preventDefault(); customOk(); }
				if (ev.key === "Escape") { custBox.style.display = "none"; }
				ev.stopPropagation();  // клавиши не должны уходить в игру
			});
			var ok = document.createElement("button");
			ok.type = "button";
			ok.textContent = "OK";
			ok.addEventListener("click", customOk);
			custBox.appendChild(custIn);
			custBox.appendChild(ok);
			statEl = document.createElement("div");
			statEl.setAttribute("style", "font-size:.72em;opacity:.8;margin-top:.35em;line-height:1.25;white-space:pre-line");
			panel.appendChild(label);
			panel.appendChild(sel);
			panel.appendChild(custBox);
			panel.appendChild(mkButton("\u27F3 ", "refresh", "refresh_t", refresh));
			panel.appendChild(mkButton("\u270E ", "redo", "redo_t", redoPage));
			panel.appendChild(mkButton("\u270D ", "fix", "fix_t", editStart));
			if (!SERVER) {
				panel.appendChild(mkButton("\u2B07 ", "export", "export_t", exportAll));
			}
			panel.appendChild(statEl);
			whyBox = document.createElement("div");  // «Почему не отвечают» — раскрывается по нажатию
			whyBox.setAttribute("style", "font-size:.72em;opacity:.85;margin-top:.2em;display:none");
			var sum = document.createElement("span");
			sum.className = "rut-why-toggle";
			sum.textContent = "\u25B8 " + U("why");
			sum.setAttribute("role", "button");
			sum.setAttribute("tabindex", "0");
			sum.setAttribute("style", "cursor:pointer;text-decoration:underline dotted");
			whyEl = document.createElement("div");
			whyEl.setAttribute("style", "white-space:pre-wrap;line-height:1.3;margin-top:.2em;word-break:break-word;text-align:left;display:none");
			var toggle = function (ev) {
				if (ev) { ev.preventDefault(); ev.stopPropagation(); }
				var open = whyEl.style.display === "none";
				quiet(function () {
					whyEl.style.display = open ? "" : "none";
					sum.textContent = (open ? "\u25BE" : "\u25B8") + " " + U("why");
				});
			};
			sum.addEventListener("click", toggle);
			sum.addEventListener("keydown", function (ev) { if (ev.key === "Enter" || ev.key === " ") { toggle(ev); } });
			whyBox.appendChild(sum);
			whyBox.appendChild(whyEl);
			panel.appendChild(whyBox);
			fillSelect();
			showStatus();
		}
		if (host) {
			panel.setAttribute("style", "margin-top:1.5em;padding-top:.6em;border-top:1px solid rgba(128,128,128,.35)");
			quiet(function () {
				if (wrap && wrap.parentNode) { wrap.parentNode.removeChild(wrap); }
				host.appendChild(panel);
			});
		} else {  // нет видимой боковой панели SugarCube (или это другая игра) — значок в углу
			panel.setAttribute("style", "margin-top:4px;width:15.5em;background:rgba(18,18,24,.96);padding:8px 9px;border-radius:6px;" +
				"box-shadow:0 2px 12px rgba(0,0,0,.55);border:1px solid rgba(255,255,255,.15);text-align:left");
			quiet(function () {
				wrap.appendChild(panel);
				if (wrap.parentNode !== document.body) { document.body.appendChild(wrap); }
			});
			floatOpen(store("rut-live-open") === "1");
		}
		placeBadge();
		panelSync();
	}
	var BADGE_FIXED = "position:fixed;right:8px;bottom:8px;z-index:100000;font:12px/1.4 sans-serif;max-width:24em;" +
		"background:rgba(0,0,0,.72);color:#fff;padding:3px 9px;border-radius:4px;pointer-events:none;display:";
	function placeBadge() {  // подсказка: под значком в углу или внизу справа
		if (!badgeEl) { return; }
		var inWrap = !!(wrap && wrap.parentNode === document.body);
		if (inWrap && badgeEl.parentNode !== wrap) { floatBadgeStyle(); quiet(function () { wrap.appendChild(badgeEl); }); }
		if (!inWrap && badgeEl.parentNode !== document.body) {
			badgeEl.setAttribute("style", BADGE_FIXED + (badgeEl.style.display || "none"));
			quiet(function () { document.body.appendChild(badgeEl); });
		}
	}
	function panelSync() {
		pillSync();
		if (!sel) { return; }
		var has = false;
		for (var i = 0; i < sel.options.length; i++) { if (sel.options[i].value === LANG) { has = true; break; } }
		if (!has) { fillSelect(); } else if (sel.value !== LANG) { quiet(function () { sel.value = LANG; }); }
	}
	var badgeEl = null, noteT = null, noteText = "";
	function badge() {
		if (!document.body) { return; }
		if (!badgeEl) {
			badgeEl = document.createElement("div");
			badgeEl.className = "rut-badge";
			badgeEl.setAttribute("style", BADGE_FIXED + "none");
			quiet(function () { document.body.appendChild(badgeEl); });
			placeBadge();
		}
		var n = Object.keys(waiting).length;
		var txt = n ? U("busy", { n: n }) : noteText;
		if (badgeEl.textContent !== txt || badgeEl.style.display !== (txt ? "block" : "none")) {
			quiet(function () { badgeEl.textContent = txt; badgeEl.style.display = txt ? "block" : "none"; });
		}
	}
	function floatBadgeStyle() {  // в «плавающем» режиме подсказка — под значком
		badgeEl.setAttribute("style", "margin-top:3px;font:12px/1.4 sans-serif;max-width:22em;background:rgba(0,0,0,.78);color:#fff;" +
			"padding:3px 9px;border-radius:4px;pointer-events:none;display:" + (badgeEl.style.display || "none"));
	}
	function note(t) {
		noteText = t;
		badge();
		clearTimeout(noteT);
		noteT = setTimeout(function () { noteText = ""; badge(); }, 7000);
	}
	function down(t) { note(U("unavail", { t: t })); }
	function setWait(on) {  // новый текст прячем, пока не придёт перевод (не дольше WAIT мс)
		if (!WAIT_SEL) { return; }
		var els = document.querySelectorAll(WAIT_SEL);
		if (!els.length) { return; }
		clearTimeout(waitTimer);
		quiet(function () { Array.prototype.forEach.call(els, function (e) { e.classList.toggle("rut-wait", !!on); }); });
		if (on) { waitTimer = setTimeout(function () { setWait(false); }, WAIT); }
	}

	/* --- шепелявость: помечаем вывод виджетов-букв (<<s>> → «s» или «th») --- */
	function wrapLisp() {
		var Mc = typeof Macro !== "undefined" ? Macro : (window.SugarCube && window.SugarCube.Macro);
		if (!Mc || !Mc.get) { return; }
		(C.lispWidgets || []).forEach(function (name) {
			var m;
			try { m = Mc.get(name); } catch (e) { m = null; }
			if (!m || m.__rut || typeof m.handler !== "function") { return; }
			var orig = m.handler;
			try {
				m.handler = function () {
					var out = this.output, before = out ? out.lastChild : null;
					var r = orig.apply(this, arguments);
					if (!out) { return r; }
					var start = before ? before.nextSibling : out.firstChild;
					if (!start) { return r; }
					var span = document.createElement("span"), txt = "";
					span.className = "rut-l";
					span.setAttribute("data-rul", name);
					while (start) { var nx = start.nextSibling; txt += start.textContent; span.appendChild(start); start = nx; }
					span.setAttribute("data-rul-on", txt.replace(/\s+/g, "").toLowerCase() !== name.toLowerCase() ? "1" : "0");
					out.appendChild(span);
					return r;
				};
				m.__rut = true;
			} catch (e) { /* не вышло — шепелявость останется английской */ }
		});
	}

	/* --- наблюдение за изменениями страницы (<<replace>>, боковая панель, окна) --- */
	var obs = null, dirty = [], dirtyT = null, flushing = false, OBS_OPT = { childList: true, subtree: true, characterData: true };
	function onMut(list) {
		for (var i = 0; i < list.length; i++) {
			var m = list[i];
			if (m.type === "characterData") { if (!DONE.has(m.target)) { dirty.push(m.target.parentNode); } continue; }
			for (var j = 0; j < m.addedNodes.length; j++) {
				var a = m.addedNodes[j];
				if (HANDLED.has(a) || (a.nodeType === 3 && DONE.has(a)) || (a.classList && (a.classList.contains("rut-badge") || a.classList.contains("rut-panel")))) { continue; }
				dirty.push(m.target);
				break;
			}
		}
		if (!dirty.length) { return; }
		if (ENGINE === "web") {  // сразу, до отрисовки: уже переведённое не мелькает по-английски
			if (!flushing) {
				flushing = true;
				try { while (dirty.length) { flushDirty(); } } finally { flushing = false; }
			}
			return;
		}
		if (!dirtyT) { dirtyT = setTimeout(flushDirty, 0); }
	}
	function flushDirty() {
		dirtyT = null;
		var list = dirty, seen = [];
		dirty = [];
		if (ENGINE !== "web") { makePanel(); }
		list.forEach(function (t) {
			if (t && t.nodeType !== 1) { t = t.parentNode; }
			if (!t || !t.isConnected || !t.closest || !t.closest(ROOT_SEL) || t.closest(NO_SEL)) { return; }
			if (seen.indexOf(t) >= 0) { return; }
			seen.push(t);
			translateRoot(t, ENGINE === "web" && !!WAIT_SEL && !!t.closest(WAIT_SEL));
		});
		if (ENGINE === "web" && pendingPassage > 0 && LANG !== "off") { setWait(true); }
	}
	function quiet(fn) {  // наши изменения страницы не должны снова запускать перевод
		if (!obs) { fn(); return; }
		onMut(obs.takeRecords());
		obs.disconnect();
		try { fn(); } finally { obs.observe(document.body, OBS_OPT); }
	}

	function boot() {  // общее для SugarCube и других игр
		var css = document.createElement("style");
		css.textContent = ".rut-wait{visibility:hidden!important}.rut-panel select,.rut-panel button{cursor:pointer}" +
			".rut-float .rut-panel button{display:block;width:100%;margin-top:.3em;padding:.25em .4em;font:inherit;" +
			"color:#eee;background:#3a4a7a;border:1px solid #5a6aa0;border-radius:4px}" +
			".rut-float select,.rut-float input{font:inherit;color:#111;background:#f4f4f4;border:1px solid #888;border-radius:3px}";
		(document.head || document.documentElement).appendChild(css);
		applyUI(LANG);
		var go = function () {
			if (typeof MutationObserver !== "undefined") { obs = new MutationObserver(onMut); obs.observe(document.body, OBS_OPT); }
			if (SERVER) { serverStatus(); } else { probeAll(); overlayDb(LANG); }
			setInterval(function () { if (!document.hidden && !serverMode() && probed && !probing) { reprobe(); } }, 120000);
			makePanel();
			setInterval(function () {  // боковая панель могла появиться (или пропасть) позже
				makePanel();
				if (RECS.length > 400) { RECS = RECS.filter(recLive); }
			}, 1500);
			allRoots();
		};
		if (document.body) { go(); } else { document.addEventListener("DOMContentLoaded", go); }
	}
	function start($) {
		boot();
		wrapLisp();
		$(document).on(":passagestart", wrapLisp);
		var onRender = function (content) {
			if (!content || HANDLED.has(content)) { return; }
			HANDLED.add(content);
			translateRoot(content, true);
		};
		$(document).on(":passagerender", function (ev) { onRender(ev && ev.content); });
		if (typeof window.postrender === "object" && window.postrender) {
			window.postrender["rut-live"] = function (content) { onRender(content); };
		}
		$(document).on(":passagedisplay", function () {
			if (pendingPassage > 0 && LANG !== "off") { setWait(true); }
			makePanel();
			relabel();
		});
	}
	if (ENGINE === "web") { boot(); }  // другая игра на HTML: всё через наблюдение за страницей
	else { (function wait() { if (window.jQuery) { start(window.jQuery); } else { setTimeout(wait, 30); } })(); }
	window.RUT = { mems: MEMS, setLang: setLang, refresh: refresh, lang: function () { return LANG; }, eps: function () { return DEPS; }, debug: { collect: collect, serialize: serialize, shortItem: shortItem, keyInfo: keyInfo, fromStand: fromStand, plural: plural, toHtml: toHtml, fromHtml: fromHtml, hinfo: HINFO } };
})();
'''


LANG_RE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,4})?$")
LIVE_KEY = "\u0001live"  # в кэше: какие фразы просила игра (короткие отпечатки) — их встраиваем в файл
LIVE_MARK = re.compile(r"\u27E6\s*(\d+)\s*\u27E7")
LIVE_MANUAL = "\u0001manual"  # в кэше: фразы, исправленные вручную в игре («Исправить фразу») — заново не переводим


def live_manual(tr):
    m = tr.cache.get(LIVE_MANUAL)
    if not isinstance(m, dict):
        m = tr.cache[LIVE_MANUAL] = {}
    return m


def live_hash(s):
    import hashlib
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:10]


def live_tune(tr, workers):
    """Настройки переводчика для игры: без пауз, параллельно, при обрыве связи — недолгий отдых адресов."""
    tr.max_wait, tr.cache_old, tr.workers = 0, False, workers
    tr.net_rest, tr.fast_fail = 30, True
    tr.delay = tr.base_delay = min(tr.delay, tr.base_delay)


def cached_langs(game_path):
    """Языки, для которых у этой игры уже есть кэш переводов (<игра>.<язык>.cache.json)."""
    base = os.path.basename(game_path.rstrip("/\\")) + "."
    folder = os.path.dirname(os.path.abspath(game_path.rstrip("/\\")))
    out = []
    try:
        names = os.listdir(folder)
    except OSError:
        return out
    for n in sorted(names):
        if n.startswith(base) and n.endswith(".cache.json"):
            lang = n[len(base):-len(".cache.json")]
            if LANG_RE.match(lang):
                out.append(lang)
    return out


class LivePool:
    """Переводчики для режима -c (--console-live): по одному на язык (язык выбирают прямо в игре, в боковой панели)."""

    def __init__(self, args, engine, key, glossary, game_path, cache_fn=None, langs_fn=None):
        self.args, self.engine, self.key, self.glossary = args, engine, key, glossary
        self.game_path = game_path
        self.cache_fn, self.langs_fn = cache_fn, langs_fn  # Ren'Py: кэш rut_cache.<язык>.json в папке игры
        # «проверочный» переводчик: проверка адресов Google; его список адресов общий для всех языков
        self.prober = Translator(args.src, "ru", "", engine, key, args.region, args.delay, {}, 0, 0)
        live_tune(self.prober, 1)
        self.trs = {}
        self.st = {}
        self.ui = {}
        self.lock = threading.Lock()  # переводим по очереди: общий пул адресов Google не перегружаем

    def cache_path(self, lang):
        if self.cache_fn:
            return self.cache_fn(lang)
        if self.args.cache and self.args.dst and lang.lower() == self.args.dst.lower():
            return self.args.cache
        return self.game_path.rstrip("/\\") + "." + lang + ".cache.json"

    def get(self, lang, quiet=False):
        k = lang.lower()
        if k not in self.trs:
            path = self.cache_path(lang)
            tr = Translator(self.args.src, lang, path, self.engine, self.key, self.args.region, self.args.delay,
                            self.glossary if self.args.dst and k == self.args.dst.lower() else {}, 0, 0)
            live_tune(tr, self.prober.workers)
            if self.engine in ("free", "google"):  # те же адреса Google и их «отдых»
                tr.eps, tr.rr = self.prober._pool(), 0
            if not quiet:
                n = sum(1 for x in tr.cache if not x.startswith("\u0001"))
                print(f"\nЯзык перевода в игре: {lang} (в кэше {n:,} переводов: {path})", file=sys.stderr)
            self.trs[k] = tr
        return self.trs[k]

    def eps(self):
        """[сколько адресов Google сейчас отвечает, сколько всего] или None (переводчик по ключу)."""
        if self.engine not in ("free", "google"):
            return None
        eps, now = self.prober._pool(), time.time()
        return [sum(1 for e in eps if e["until"] <= now), len(eps)]

    def why(self):
        """Сколько адресов Google сейчас не отвечает — по причинам."""
        if self.engine not in ("free", "google"):
            return None
        now, out = time.time(), {}
        for e in self.prober._pool():
            if e["until"] > now:
                k = e.get("why") or "other"
                out[k] = out.get(k, 0) + 1
        return out

    def state(self, lang):
        return self.st.setdefault(lang.lower(), {"blocked_until": 0.0, "count": 0, "chars": 0, "err": ""})

    def translate(self, texts, lang, force, redo=False, hinfo=None):
        with self.lock:
            tr, st = self.get(lang), self.state(lang)
            if force or redo:
                st["blocked_until"] = 0.0
            if redo:
                live_redo(tr, texts, hinfo)
            return live_translate(tr, texts, st, force, hinfo), st["err"]

    def manual(self, lang, key, value, remove=False):
        """«✎ Исправить фразу» в игре: свой перевод фразы (или «Вернуть перевод Google»)."""
        with self.lock:
            tr = self.get(lang)
            man = live_manual(tr)
            if remove:
                man.pop(key, None)
            else:
                tr.cache[key] = value
                man[key] = 1
                seen = tr.cache.setdefault(LIVE_KEY, {})
                if isinstance(seen, dict):
                    seen[live_hash(key)] = 1
                print(f"  [{lang}] исправлено вручную: {value[:70]}", file=sys.stderr)
            tr.save(force=True)

    def ui_map(self, lang):
        if self.args.no_ui:
            return {}
        with self.lock:
            k = lang.lower()
            if k not in self.ui:
                tr = self.get(lang)
                tr.offline, tr.stop_reason = False, ""
                tr.halt.clear()  # после параллельного перевода флаг остановки поднят — снимаем
                m = ui_strings(tr, lang)
                if m or not self.get(lang).offline:
                    self.ui[k] = m
                return m or {}
            return self.ui[k]

    def langs(self):
        """Все языки этой игры: с кэшем на диске и открытые в этом сеансе."""
        out = {x.lower(): x for x in (self.langs_fn() if self.langs_fn else cached_langs(self.game_path))}
        out.update({k: tr.dst for k, tr in self.trs.items()})
        return list(out.values())

    def save_all(self):
        for tr in self.trs.values():
            try:
                tr.save(force=True)
            except OSError as e:
                print(f"Не удалось сохранить {tr.cache_path}: {e}", file=sys.stderr)


def live_marks_ok(src, res):
    """Перевод сохранил все метки ⟦n⟧ (ссылки, выделение, числа) — иначе игра переведёт кусок по частям."""
    if not isinstance(res, str):
        return False
    if "[" not in src:
        res = re.sub(r"\[\s*(\d+)\s*\]", "\u27E6\\1\u27E7", res)
    return sorted(LIVE_MARK.findall(src)) == sorted(LIVE_MARK.findall(res))


PA_OPEN = re.compile(r"<a\s+i\s*=\s*[\"']?(\d+)[\"']?\s*>|</a\s*>", re.I)
PA_ITEM = re.compile(r"<a\s+i\s*=\s*[\"']?(\d+)[\"']?\s*>([\s\S]*?)</a\s*>", re.I)


def html_info(h):
    """Описание фразы из игры для HTML-режима: {"p": {открывающая метка: закрывающая}} или {"g": число подписей,
    "hint": есть ли заголовок}. Всё остальное — None."""
    if not isinstance(h, dict):
        return None
    if isinstance(h.get("g"), int) and 0 < h["g"] <= 40:
        return {"g": h["g"], "hint": bool(h.get("hint"))}
    p = h.get("p")
    if isinstance(p, dict) and p and all(str(k).isdigit() and isinstance(v, int) for k, v in p.items()):
        return {"p": {str(k): v for k, v in p.items()}}
    return None


CODE_RE = re.compile(r"(?<![A-Za-z0-9])(?:[A-Z]{2,4}|[A-Z](?=-)|\d+)(?![A-Za-z0-9])")


def tidy_parts(items, parts):
    """Подписи списка: убрать точку, которую Google ставит в конце; «F-cup» должно остаться с F (а не «FF»)."""
    if len(items) != len(parts):
        return None
    out = []
    for it, p in zip(items, parts):
        if not re.search(r"[.!?\u2026]$", it):
            p = re.sub(r"[\s.\u3002;,]+$", "", p)
        if not p or any(not re.search(r"(?<![A-Za-z0-9])" + re.escape(c) + r"(?![A-Za-z0-9])", p)
                        for c in CODE_RE.findall(it)):
            return None
        out.append(p)
    return out


def to_html(key, info, sep=", "):
    """Фраза → HTML для translate-pa (как у встроенного переводчика Chrome): ссылки и выделение — <a i=N>…</a>,
    короткие подписи — списком через запятую после заголовка."""
    import html as htmlmod
    if "g" in info:
        m = re.split(r"\s*\u27E698\u27E7\s*", key)
        hint = m[0] if info["hint"] and len(m) == 2 else ""
        items = (m[1] if info["hint"] and len(m) == 2 else key).split(" | ")
        if len(items) != info["g"]:
            return None
        head = htmlmod.escape(re.sub(r"[\s.:;,]+$", "", hint), quote=False) + ": " if hint else ""
        return head + sep.join(f"<a i={i}>{htmlmod.escape(x, quote=False)}</a>" for i, x in enumerate(items))
    closes = {str(v) for v in info["p"].values()}

    def tag(m):
        d = m.group(1)
        return f"<a i={d}>" if d in info["p"] else "</a>" if d in closes else m.group(0)
    return re.sub(r"\u27E6(\d+)\u27E7", tag, htmlmod.escape(key, quote=False))


def from_html(res, key, info):
    """Ответ translate-pa → наш формат с метками (None — теги перепутаны)."""
    import html as htmlmod
    if not isinstance(res, str):
        return None
    res = re.sub(r"\s*<br\s*/?>\s*", " ", res)
    if "g" in info:
        parts, first = {}, None
        for m in PA_ITEM.finditer(res):
            i = int(m.group(1))
            if i >= info["g"] or i in parts:
                return None
            txt = htmlmod.unescape(re.sub(r"<[^>]*>", "", m.group(2)))
            parts[i] = re.sub(r"\s+", " ", re.sub(r"[|\u27E6\u27E7]", " ", txt)).strip()
            first = m.start() if first is None else first
        if len(parts) != info["g"] or not all(parts.values()):
            return None
        m = re.split(r"\s*\u27E698\u27E7\s*", key)
        fixed = tidy_parts((m[1] if info["hint"] and len(m) == 2 else key).split(" | "), [parts[i] for i in range(info["g"])])
        if fixed is None:
            return None
        out = " | ".join(fixed)
        if info["hint"]:
            h = htmlmod.unescape(re.sub(r"<[^>]*>", "", res[:first]))
            h = re.sub(r"[|\u27E6\u27E7]", " ", re.sub(r"[\s:\uFF1A,\u060C\u3001]+$", "", h)).strip()
            out = (h or "-") + " \u27E698\u27E7 " + out
        return out
    stack, bad = [], []

    def tag(m):
        d = m.group(1)
        if d is not None:
            if d not in info["p"]:
                bad.append(d)
                return ""
            stack.append(d)
            return f"\u27E6{d}\u27E7"
        if not stack:
            bad.append("/")
            return ""
        return f"\u27E6{info['p'][stack.pop()]}\u27E7"
    out = PA_OPEN.sub(tag, res)
    if bad or stack:
        return None
    out = htmlmod.unescape(re.sub(r"<[^>]*>", "", out))
    return out if live_marks_ok(key, out) else None


def live_pa_html(tr, items, sep=", "):
    """Фразы с тегами — HTML-ом через translate-pa (с контекстом, как Chrome). Возвращает {фраза: перевод}."""
    got = {}
    if tr.engine not in ("free", "google") or not items or not hasattr(tr, "eps"):
        return got
    ep = next((e for e in tr.eps if e["kind"] == "pa" and e["until"] <= time.time()), None)
    if ep is None:
        return got
    todo = [(k, h) for k, h in ((k, to_html(k, i, sep)) for k, i in items) if h]
    chunks, cur, size = [], [], 0
    for k, h in todo:
        if cur and (size + len(h) > 4500 or len(cur) >= 100):
            chunks.append(cur)
            cur, size = [], 0
        cur.append((k, h))
        size += len(h) + 1
    if cur:
        chunks.append(cur)
    info = dict(items)
    for ch in chunks:
        try:
            body = [[[h for _, h in ch], tr.src, tr.dst], "wt_lib"]
            r = tr._http().post(f"https://{ep['host']}/v1/translateHtml", data=json.dumps(body, ensure_ascii=False).encode(),
                                headers={"Content-Type": "application/json+protobuf", "X-Goog-API-Key": tr.PA_KEY,
                                         "User-Agent": tr.UA}, timeout=60)
            r.raise_for_status()
            res = r.json()[0]
            if not isinstance(res, list) or len(res) != len(ch):
                raise ValueError("неожиданный ответ")
        except Exception as e:  # noqa: BLE001 — остальное переведётся обычным способом
            if getattr(getattr(e, "response", None), "status_code", None) != 400:
                ep["until"], ep["why"] = time.time() + 60, why_of(e)
            break
        for (k, _), x in zip(ch, res):
            out = from_html(x, k, info[k])
            if out:
                got[k] = out
    again = [(k, i) for k, i in items if k not in got and "g" in i] if sep == ", " else []
    if again:  # список подписей перепутан («F-cup» → «FF») — ещё раз, через «|»
        got.update(live_pa_html(tr, again, " | "))
    return got


def live_redo(tr, texts, hinfo=None):
    """«Перевести страницу заново»: каждая фраза ещё раз, отдельно; новый перевод заменяет старый.
    Не вышло — остаётся прежний."""
    man = live_manual(tr)
    todo = [t for t in dict.fromkeys(texts) if t and t.strip() and isinstance(tr.peek(t), str) and t not in man][:150]
    if not todo:
        return
    tr.offline, tr.stop_reason = False, ""
    tr.halt.clear()
    html = live_pa_html(tr, [(t, (hinfo or {})[t]) for t in todo if (hinfo or {}).get(t)])

    def again(t):
        if t in html:
            return t, html[t]
        try:
            return t, tr.translate_batch([t])[0]
        except Exception:  # noqa: BLE001
            return t, None
    changed = done = 0
    for t, r in Translator._parallel(again, todo):
        if isinstance(r, str) and r.strip() and (not LIVE_MARK.search(t) or live_marks_ok(t, r)):
            done += 1
            if r != tr.cache.get(t):
                changed += 1
            tr.cache[t] = r
            tr.cache.pop(SAME_MARK + t, None)
    tr.save(force=True)
    print(f"  [{tr.dst}] страница переведена заново: {done} из {len(todo)} фраз, изменилось {changed}",
          file=sys.stderr)


def live_translate(tr, texts, st, force=False, hinfo=None):
    """Запрос из игры: переводы для строк (None — пока недоступно). Новое переводим через общий пул."""
    seen = tr.cache.setdefault(LIVE_KEY, {})
    if not isinstance(seen, dict):
        seen = tr.cache[LIVE_KEY] = {}
    for t in texts:
        if t:
            seen[live_hash(t)] = 1
    missing = [t for t in dict.fromkeys(texts) if t.strip() and not tr.has(t)]
    if missing and time.time() >= st["blocked_until"]:
        tr.offline, tr.stop_reason = False, ""
        tr.halt.clear()
        if force and hasattr(tr, "eps"):  # «Обновить перевод» в игре: дать адресам Google ещё шанс
            now = time.time()
            for ep in tr.eps:
                if ep["until"] > now:
                    ep["until"] = now
        st["err"] = ""
        try:
            html = live_pa_html(tr, [(t, hinfo[t]) for t in missing if hinfo and hinfo.get(t)])
            for t, r in html.items():  # с тегами — HTML-ом, как Chrome; остальное — обычным путём
                tr.cache[t] = r
            tr.prefetch([t for t in missing if t not in html], quiet=True)
            # испорченные метки сразу переводим заново по одной (параллельно) — игре не нужен второй запрос
            bad = [t for t in missing if tr.has(t) and LIVE_MARK.search(t) and not live_marks_ok(t, tr.peek(t))][:24]
            if bad and not tr.offline:
                tr.halt.clear()  # после параллельной пачки флаг остановки поднят — снимаем

                def again(t):
                    try:
                        return t, tr.translate_batch([t])[0]
                    except Exception:  # noqa: BLE001
                        return t, None
                for t, r in Translator._parallel(again, bad):
                    if live_marks_ok(t, r):
                        tr.cache[t] = r
        except Halted:
            pass
        except BadLanguage:
            st["err"] = "lang"
            print(f"\n  Google не знает язык «{tr.dst}» — выберите в игре другой код языка", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f"\n  ошибка переводчика: {e!r}", file=sys.stderr)
        got = [t for t in missing if tr.has(t)]
        if got:
            st["count"] += len(got)
            st["chars"] += sum(map(len, got))
            print(f"  [{tr.dst}] переведено новых фраз: {len(got)} (за сеанс: {st['count']:,} фраз, "
                  f"{st['chars']:,} симв.)", file=sys.stderr)
        if len(got) < len(missing) and not st["err"]:
            st["blocked_until"] = time.time() + 60
            why = (tr.stop_reason or "не отвечает").replace("дольше 0 мин ", "")
            print(f"  переводчик сейчас недоступен ({why}): новый текст пока остаётся английским; "
                  f"попробую снова через минуту или по кнопке «Обновить перевод» в игре", file=sys.stderr)
        tr.save()
    out = []
    for t in texts:
        r = tr.peek(t) if t and t.strip() else None
        out.append(r if isinstance(r, str) else None)
    return out


def live_dict(tr, budget=3_000_000):
    """Переводы, которые встраиваются в файл игры: всё, что игра уже показывала (-c и -i), и
    простые фразы без кода из обычного перевода — их не больше ~budget символов (файл не раздувается)."""
    seen = tr.cache.get(LIVE_KEY)
    seen = seen if isinstance(seen, dict) else {}
    first, extra = {}, []
    for k, v in list(tr.cache.items()):
        if not isinstance(v, str) or not k or k[0] in "\u0001\u0002\u0003" or v == k or not v.strip():
            continue
        if live_hash(k) in seen:
            first[k] = v
        elif "\u27E6" not in k and len(k) <= 2000 and len(k.split()) >= 4:
            extra.append((k, v))
    out = dict((k, v) for k, v in tr.glossary.items() if isinstance(v, str))
    out.update(first)  # всё, что вы уже видели в игре, — целиком
    size = 0
    for k, v in extra:
        if size + len(k) + len(v) > budget:
            break
        out[k] = v
        size += len(k) + len(v)
    return out


def live_page(game, cfg, embed=None, web=False, manual=None):
    """HTML игры со встроенным переводом на лету (сама игра не меняется — только добавлен скрипт).
    embed — {язык: {фраза: перевод}}: готовые переводы прямо в файле (для запуска без окна скрипта).
    web — не SugarCube: скрипт перевода — отдельным <script> в конце страницы."""
    js = ("/* === Добавлено sugarcube_translate: перевод на лету === */\nwindow.RUT_CFG = "
          + json.dumps(cfg, ensure_ascii=False) + ";\n" + LIVE_JS + "/* === конец добавленного === */\n")
    game.reset()
    injected = (not web) and game.inject(js)
    html = game.render()
    tags = ""
    if embed:  # переводы — раньше скрипта: он читает их сразу при запуске
        data = json.dumps(dict({"langs": embed}, **({"manual": manual} if manual else {})),
                          ensure_ascii=False, separators=(",", ":"))
        tags += '<script type="application/json" id="rut-dict">' + data.replace("<", "\\u003c") + "</script>"
    if not injected:
        safe = re.sub(r"</(script)", r"<\\/\1", js, flags=re.I).replace("<!--", "<\\!--")  # не закрыть <script> раньше времени
        tags += "<script>" + safe + "</script>"
    if tags:
        i = html.lower().rfind("</body>")
        html = html[:i] + tags + html[i:] if i >= 0 else html + tags
    return html


MIME_FIX = {  # в Windows реестр иногда даёт .js тип text/plain — браузер может такой скрипт не запустить
    ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8", ".html": "text/html; charset=utf-8", ".htm": "text/html; charset=utf-8",
    ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
    ".webp": "image/webp", ".ttf": "font/ttf", ".woff": "font/woff", ".woff2": "font/woff2", ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg", ".wav": "audio/wav", ".mp4": "video/mp4", ".webm": "video/webm", ".txt": "text/plain; charset=utf-8"}


def live_server(pool, html, root, page_name, port):
    """HTTP-сервер перевода на лету на 127.0.0.1 (порт port или следующий свободный). html=None — без страницы
    игры (Ren'Py: игра сама присылает фразы на /__rut/translate)."""
    import http.server
    import mimetypes
    import urllib.parse
    page = html.encode("utf-8") if html is not None else None
    root = os.path.realpath(root) if root else None

    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "sugarcube-translate"

        def log_message(self, *a):  # без лишнего шума в окне
            pass

        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, obj):
            self._send(200, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            parts = urllib.parse.urlsplit(self.path)
            path = urllib.parse.unquote(parts.path)
            if page is None and path == "/":
                return self._send(200, "sugarcube_translate: перевод на лету работает".encode("utf-8"),
                                  "text/plain; charset=utf-8")
            if page is not None and path in ("/", "/" + page_name):
                return self._send(200, page, "text/html; charset=utf-8")
            if path == "/__rut/status":
                return self._json({"eps": pool.eps(), "why": pool.why(), "engine": pool.engine})
            if path == "/__rut/ui":
                lang = (urllib.parse.parse_qs(parts.query).get("lang") or [""])[0]
                if not LANG_RE.match(lang):
                    return self._send(400, b"bad lang", "text/plain")
                return self._json({"ui": pool.ui_map(lang)})
            if root is None:
                return self._send(404, b"not found", "text/plain")
            full = os.path.realpath(os.path.join(root, path.lstrip("/")))
            if not full.startswith(root + os.sep) or not os.path.isfile(full):
                return self._send(404, b"not found", "text/plain")
            ext = os.path.splitext(full)[1].lower()
            ctype = MIME_FIX.get(ext) or mimetypes.guess_type(full)[0] or "application/octet-stream"
            try:
                with open(full, "rb") as f:
                    data = f.read()
            except OSError:
                return self._send(404, b"not found", "text/plain")
            self._send(200, data, ctype)

        def do_POST(self):
            route = urllib.parse.urlsplit(self.path).path
            if route == "/__rut/manual":  # «✎ Исправить фразу» в игре
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    data = json.loads(self.rfile.read(min(n, 2_000_000)).decode("utf-8"))
                    lang, key, value = data.get("lang") or "", data.get("key"), data.get("value")
                    remove = bool(data.get("remove"))
                except (ValueError, AttributeError):
                    return self._send(400, b"bad request", "text/plain")
                if (not isinstance(lang, str) or not LANG_RE.match(lang) or not isinstance(key, str) or not key.strip()
                        or not (remove or (isinstance(value, str) and value.strip()))):
                    return self._send(400, b"bad request", "text/plain")
                pool.manual(lang, key, value, remove)
                return self._json({"ok": True})
            if route != "/__rut/translate":
                return self._send(404, b"not found", "text/plain")
            try:
                n = int(self.headers.get("Content-Length") or 0)
                data = json.loads(self.rfile.read(min(n, 20_000_000)).decode("utf-8"))
                texts = [t if isinstance(t, str) else "" for t in data.get("t", [])][:500]
                lang = data.get("lang") or ""
                force = bool(data.get("force"))
                redo = bool(data.get("redo"))
                hraw = data.get("h") if isinstance(data.get("h"), list) else []
                hinfo = {t: html_info(h) for t, h in zip(texts, hraw) if t and html_info(h)}
            except (ValueError, AttributeError):
                return self._send(400, b"bad request", "text/plain")
            if not isinstance(lang, str) or not LANG_RE.match(lang):
                return self._send(400, b"bad lang", "text/plain")
            res, err = pool.translate(texts, lang, force, redo, hinfo)
            self._json({"t": res, "eps": pool.eps(), "why": pool.why(), "err": err})

    srv = None
    for p in range(port, port + 20):
        try:
            srv = http.server.ThreadingHTTPServer(("127.0.0.1", p), Handler)
            break
        except OSError:
            continue
    if srv is None:
        raise SystemExit(f"Не удалось открыть порт {port}–{port + 19}: возможно, игра уже запущена в другом окне.")
    srv.daemon_threads = True
    return srv


def live_loop(srv, pool, on_exit=None):
    """Работает, пока не введут exit (или не нажмут Ctrl+C); потом сохраняет кэши и вызывает on_exit()."""
    try:
        srv.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
        pool.save_all()
        print("\nОстановлено. Переводы сохранены: "
              + ", ".join(tr.cache_path for tr in pool.trs.values()), file=sys.stderr)
        if on_exit:
            on_exit()


def serve_live(pool, html, root, page_name, port, open_browser, on_exit=None, where="боковая панель → «Перевод»"):
    import webbrowser
    srv = live_server(pool, html, root, page_name, port)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print(f"\nИгра с переводом на лету: {url}", file=sys.stderr)
    if srv.server_address[1] != port:
        print(f"  (порт {port} занят, взял {srv.server_address[1]}: сохранения в браузере у этого адреса свои)",
              file=sys.stderr)
    print(f"Язык можно сменить в игре: {where}. Там же кнопки «Обновить перевод», «Перевести страницу заново»\n"
          "и «Исправить фразу» (свой вариант перевода — запоминается).\n"
          "Не закрывайте это окно, пока играете. Выход — введите exit и нажмите Enter (или Ctrl+C).", file=sys.stderr)
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    live_loop(srv, pool, on_exit)


def live_import(pool, paths):
    """--import: переводы, сохранённые в игре кнопкой «Сохранить переводы в файл» (с телефона и т.п.)."""
    for path in paths:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            langs = data["langs"]
            assert isinstance(langs, dict)
        except (OSError, ValueError, KeyError, AssertionError, TypeError) as e:
            raise SystemExit(f"Не получилось прочитать {path}: это не файл переводов из игры ({e})")
        if data.get("src") and data["src"] != pool.args.src:
            print(f"  {path}: переводы с языка «{data['src']}», а игра — «{pool.args.src}»; пропускаю",
                  file=sys.stderr)
            continue
        manual = data.get("manual") if isinstance(data.get("manual"), dict) else {}
        for lang, items in langs.items():
            if not LANG_RE.match(str(lang)) or not isinstance(items, dict):
                continue
            tr = pool.get(lang, quiet=True)
            fixed = [k for k in (manual.get(lang) or []) if isinstance(k, str) and isinstance(items.get(k), str)]
            if fixed:
                man = live_manual(tr)
                for k in fixed:
                    man[k] = 1
            seen = tr.cache.setdefault(LIVE_KEY, {})
            new = upd = 0
            for k, v in items.items():
                if not isinstance(k, str) or not isinstance(v, str) or not k.strip() or not v.strip():
                    continue
                if k[0] in "\u0001\u0002\u0003":
                    continue
                seen[live_hash(k)] = 1
                old = tr.peek(k)
                if old == v:
                    continue
                if isinstance(old, str):
                    upd += 1  # переведено в игре заново («Перевести страницу заново») — новый вариант главнее
                else:
                    new += 1
                tr.cache[k] = v
            tr.save(force=True)
            print(f"Добавлено из {os.path.basename(path)}: язык {lang} — {new:,} новых переводов, {upd:,} обновлено "
                  f"(всего в файле {len(items):,})" + (f", исправлено вручную: {len(fixed):,}" if fixed else ""),
                  file=sys.stderr)


def run_live(args, game, game_path, engine, key, glossary):
    if not isinstance(game, (HtmlFile, WebApp)):
        raise SystemExit("Для -l (--live) и -c (--console-live) нужна собранная игра .html (тот файл, что открывается в браузере) "
                         "или папка с ней.")
    web = isinstance(game, WebApp) or "sugarcube" not in (game.format() or "").lower()
    where = "значок \U0001F310 в правом верхнем углу игры" if web else "боковая панель → «Перевод»"
    widgets, pairs = LISP_SCAN["widgets"], LISP_SCAN["pairs"]
    pool = LivePool(args, engine, key, glossary, game_path)
    if args.import_files:
        live_import(pool, args.import_files)
    default = args.dst or "auto"  # без флага — язык браузера (если это не язык оригинала), дальше — выбор игрока
    cfg = {"lang": default, "src": args.src, "server": "/__rut/translate", "wait": int(args.live_wait * 1000),
           "lispWidgets": [] if args.no_lisp else sorted(widgets), "lispWords": {} if args.no_lisp else pairs}
    if web:  # не SugarCube: переводим всё, что появляется на странице
        prof = web_profile(game.text)
        cfg.update(engine="web", roots=prof["roots"], noSel=prof["noSel"], waitSel=prof["waitSel"],
                   lispWidgets=[], lispWords={})
        print(f"Игра: {prof['name']} — перевод на лету того, что на экране.", file=sys.stderr)
    stem, ext = os.path.splitext(game_path)
    live_path = f"{stem}_live{ext or '.html'}"

    def ui_maps(fetch):
        if args.no_ui:
            return {}
        maps = {"ru": L10N_RU}
        for lang in pool.langs() + ([args.dst] if args.dst else []):
            if not lang.lower().startswith("ru"):
                m = ui_strings(pool.get(lang, quiet=True), lang, fetch=fetch)
                if m:
                    maps[lang] = m
        return maps

    def write_portable():
        """Файл для запуска без окна скрипта (ПК — двойной щелчок, Android): переводы встроены в него."""
        emb, man, n, mb = {}, {}, 0, 0.0
        for lang in pool.langs():
            tr = pool.get(lang, quiet=True)
            d = live_dict(tr)
            if d:
                emb[lang] = d
                n += len(d)
                mb += sum(len(k) + len(v) for k, v in d.items()) * 2 / 1e6
                fixed = [k for k in live_manual(tr) if k in d]
                if fixed:
                    man[lang] = fixed
        html = live_page(game, dict(cfg, server="", ui=ui_maps(False), built=int(time.time() * 1000)), emb, web, man)
        write_text(live_path, html, game.crlf)
        langs = ", ".join(f"{lang} {len(d):,}" for lang, d in emb.items()) or "пока нет"
        print(f"Файл игры со встроенным переводом: {live_path}\n  встроено готовых переводов: {langs} "
              f"(~{mb:.1f} МБ); новое браузер переводит через Google сам и запоминает.", file=sys.stderr)

    if widgets or pairs:
        print(f"Шепелявость: виджеты {', '.join('<<' + w + '>>' for w in sorted(widgets)) or '—'}; "
              f"слова {', '.join(f'{v}→{w}' for v, w in list(pairs.items())[:6]) or '—'}", file=sys.stderr)
    if not args.console:  # -l / --live или --import: только файл
        write_portable()
        print("\nКак играть:\n  • ПК: откройте этот файл двойным щелчком (окно скрипта не нужно).\n"
              "  • Android: скопируйте на телефон этот файл вместе с папками игры (картинки и т.п.) и откройте "
              f"его браузером или JoiPlay.\n  Язык выбирается в игре: {where}. Там же «Исправить фразу» — "
              "свой вариант перевода, если Google ошибся.\n"
              "  Нужен интернет для нового текста. Если Google не пускает браузер, в боковой панели будет "
              "«нет связи с Google» — тогда играйте через -c (--console-live) на ПК.\n"
              "  Переведённое на телефоне: «Перевод» → «Сохранить переводы в файл», затем на ПК\n"
              f"      python sugarcube_translate.py \"{args.input}\" -i <этот файл>\n"
              "  — всё попадёт в этот файл игры.", file=sys.stderr)
        return
    print("Режим «перевод на лету»." + (f" Язык по умолчанию: {args.dst}." if args.dst else
                                        f" Язык выбирается в игре ({where})."), file=sys.stderr)
    if engine in ("free", "google"):
        n_ok = pool.prober.probe()
        if not n_ok:
            print("Сейчас ни один адрес Google не отвечает: уже переведённое будет показано переведённым, новое — "
                  "пока на английском (скрипт будет пробовать снова).", file=sys.stderr)
        pool.prober.workers = max(1, min(n_ok, 6 if args.fast else 4))  # части пассажа — на разные адреса сразу
    elif args.fast:
        pool.prober.workers = 3
    cfg["ui"] = ui_maps(True)
    for lang, m in cfg["ui"].items():
        pool.ui[lang.lower()] = m
    write_portable()
    print("  (он открывается и без этого окна — на ПК двойным щелчком или на Android; при выходе из этого "
          "режима файл обновится всеми новыми переводами)", file=sys.stderr)
    html = live_page(game, cfg, None, web)
    serve_live(pool, html, os.path.dirname(os.path.abspath(game_path)), os.path.basename(live_path),
               args.port, not args.no_browser, on_exit=write_portable, where=where)


# ==== ENGINES BEGIN ====

# ===========================================================================
# Ren'Py: перевод при показе текста — словарь + маленький модуль в папке игры (код игры не меняется)
# ===========================================================================

import copyreg as _copyreg
import hashlib as _hashlib
import io as _io
import pickle as _pickle
import struct as _struct
import zlib as _zlib


def _rpy_state_dicts(st):
    if isinstance(st, dict):
        return [st]
    if isinstance(st, tuple):
        return [d for d in st if isinstance(d, dict)]
    return []


class RpyNode:
    """Любой объект Ren'Py из .rpyc (узел сценария, экран...) — без самого Ren'Py. Записывается обратно как был."""
    _rmod, _rname = "", ""

    def __new__(cls, *args, **kwargs):
        o = object.__new__(cls)
        o.__dict__["_rnew"] = args
        return o

    def __init__(self, *args, **kwargs):
        self.__dict__["_rargs"] = args

    def __setstate__(self, state):
        self.__dict__["_rstate"] = state
        for d in _rpy_state_dicts(state):
            self.__dict__.update(d)

    def __reduce_ex__(self, proto):
        d = self.__dict__
        st = d.get("_rstate")
        if "_rargs" in d:
            rv = (type(self), tuple(d["_rargs"]))
        else:
            rv = (_copyreg.__newobj__, (type(self),) + tuple(d.get("_rnew", ())))
        return rv + (st,) if st is not None else rv

    def __repr__(self):
        return f"<{self._rname}>"


class RpyStr(str):
    """PyExpr и подобные: строка с кодом и доп. данными (файл, строка...)."""
    _rmod, _rname = "", ""

    def __new__(cls, s="", *args, **kwargs):
        o = str.__new__(cls, s if isinstance(s, str) else str(s))
        o._rargs = (s,) + args
        return o

    def __init__(self, *args, **kwargs):
        self._rcall = True

    def __setstate__(self, state):
        self._rstate = state

    def __reduce_ex__(self, proto):
        st = self.__dict__.get("_rstate")
        if self.__dict__.get("_rcall"):
            rv = (type(self), tuple(self._rargs))
        else:
            rv = (_copyreg.__newobj__, (type(self),) + tuple(self._rargs))
        return rv + (st,) if st is not None else rv


class _RpyList(list):
    _rmod, _rname = "", ""

    def __setstate__(self, state):
        self._rstate = state
        if isinstance(state, dict):
            self.__dict__.update(state)

    def __reduce_ex__(self, proto):
        return (_copyreg.__newobj__, (type(self),), self.__dict__.get("_rstate"), iter(self))


class _RpyDict(dict):
    _rmod, _rname = "", ""

    def __setstate__(self, state):
        self._rstate = state
        if isinstance(state, dict):
            self.__dict__.update(state)

    def __reduce_ex__(self, proto):
        return (_copyreg.__newobj__, (type(self),), self.__dict__.get("_rstate"), None, iter(self.items()))


class _RpySet(set):
    _rmod, _rname = "", ""

    def __setstate__(self, state):
        self._rstate = state

    def __reduce_ex__(self, proto):
        return (type(self), (list(self),), self.__dict__.get("_rstate"))


_RPY_CLASSES = {}


def _rpy_class(module, name):
    key = (module, name)
    if key not in _RPY_CLASSES:
        if name == "PyExpr" or name.endswith("Str") and module.startswith("renpy.ast"):
            base = RpyStr
        elif "List" in name:
            base = _RpyList
        elif "Dict" in name:
            base = _RpyDict
        elif "Set" in name and "Settings" not in name:
            base = _RpySet
        else:
            base = RpyNode
        _RPY_CLASSES[key] = type(name, (base,), {"_rmod": module, "_rname": name})
    return _RPY_CLASSES[key]


class RpyUnpickler(_pickle.Unpickler):
    SAFE = {("collections", "OrderedDict"), ("collections", "defaultdict"), ("copy_reg", "_reconstructor"),
            ("copyreg", "_reconstructor"), ("__builtin__", "set"), ("builtins", "set"), ("__builtin__", "frozenset"),
            ("builtins", "frozenset"), ("__builtin__", "object"), ("builtins", "object"), ("builtins", "list"),
            ("builtins", "dict"), ("builtins", "tuple"), ("__builtin__", "list"), ("__builtin__", "dict"),
            ("datetime", "date"), ("datetime", "datetime"), ("datetime", "time"), ("builtins", "bytearray"),
            ("__builtin__", "bytearray"), ("builtins", "complex"), ("__builtin__", "complex"),
            ("copyreg", "__newobj__"), ("copy_reg", "__newobj__"), ("_codecs", "encode")}

    def find_class(self, module, name):
        if (module, name) in self.SAFE:
            return super().find_class(module, name)
        return _rpy_class(module, name)  # всё остальное — пустышки: никакой код из файла не выполняется


def rpy_loads(data):
    return RpyUnpickler(_io.BytesIO(data), encoding="utf-8", errors="surrogateescape").load()


class _RpyPickler(_pickle._Pickler):
    """Записывает пустышки под их настоящими именами (renpy.ast.Init ...) — для .rpyc, который прочтёт сам Ren'Py."""

    def save_global(self, obj, name=None):
        if isinstance(obj, type) and obj.__dict__.get("_rname"):
            self.write(_pickle.GLOBAL + (obj._rmod + "\n" + obj._rname + "\n").encode("utf-8"))
            self.memoize(obj)
            return
        return _pickle._Pickler.save_global(self, obj, name)


def rpy_dumps(obj):
    f = _io.BytesIO()
    _RpyPickler(f, 2).dump(obj)  # протокол 2 — читают и Ren'Py 6/7 (Python 2), и Ren'Py 8
    return f.getvalue()


RPC2 = b"RENPY RPC2"


def rpyc_read(data, slot=1):
    """Содержимое .rpyc: (данные, узлы сценария). Старые и новые версии Ren'Py."""
    if data[:10] == RPC2:
        pos = 10
        while pos + 12 <= len(data):
            s, start, length = _struct.unpack("III", data[pos:pos + 12])
            if s == 0:
                break
            if s == slot:
                return rpy_loads(_zlib.decompress(data[start:start + length]))
            pos += 12
        return None
    return rpy_loads(_zlib.decompress(data))


def rpyc_pack(blob, rpc2=True):
    z = _zlib.compress(blob, 9)
    if not rpc2:
        return z
    start = len(RPC2) + 24
    return (RPC2 + _struct.pack("III", 1, start, len(z)) + _struct.pack("III", 0, 0, 0) + z
            + _hashlib.md5(blob).digest())


def rpa_index(path):
    """Архив .rpa (RPA-2.0/3.0/3.2): {имя файла: (смещение, длина, префикс)}. None — формат не знаем."""
    with open(path, "rb") as f:
        head = f.readline(200)
        parts = head.split()
        if not parts:
            return None
        ver = parts[0]
        try:
            if ver in (b"RPA-3.0", b"RPA-3.2"):
                offset = int(parts[1], 16)
                key = 0
                for k in parts[2:]:
                    key ^= int(k, 16)
            elif ver == b"RPA-2.0":
                offset, key = int(parts[1], 16), 0
            else:
                return None
            f.seek(offset)
            raw = _pickle.loads(_zlib.decompress(f.read()), encoding="bytes")
        except Exception:  # noqa: BLE001 — формат, изменённый автором игры
            return None
    out = {}
    for name, entries in raw.items():
        if isinstance(name, bytes):
            name = name.decode("utf-8", "replace")
        if not entries:
            continue
        e = entries[0]
        off, length = e[0] ^ key, e[1] ^ key
        prefix = e[2] if len(e) > 2 else b""
        if isinstance(prefix, str):
            prefix = prefix.encode("latin-1")
        out[name.replace("\\", "/")] = (off, length, prefix or b"")
    return out


def rpa_read(path, entry):
    off, length, prefix = entry
    with open(path, "rb") as f:
        f.seek(off)
        return prefix + f.read(length)


# ---------------------------------------------------------------------------
# Какие строки показываются игроку
# ---------------------------------------------------------------------------

# Вызовы, первая строка которых — текст на экране
RPY_TEXT_CALLS = set(("_ __ _p ___ renpy.notify Notify renpy.input ui.text ui.textbutton ui.label Text Character "
                      "ADVCharacter NVLCharacter DynamicCharacter Confirm renpy.confirm layout.yesno_screen Tooltip "
                      "renpy.display_notify narrator centered extend renpy.say renpy.display_say "
                      "ParameterizedText").split())
# Вызовы, строки которых — не текст (метки, картинки, звуки, переменные...)
RPY_CODE_CALLS = set(("renpy.jump renpy.call renpy.show renpy.hide renpy.scene renpy.music.play renpy.music.queue "
                      "renpy.sound.play renpy.sound.queue renpy.play renpy.music.stop renpy.music.set_volume "
                      "renpy.music.register_channel renpy.image renpy.movie_cutscene renpy.seen_label renpy.has_label "
                      "renpy.get_screen renpy.showing renpy.loadable renpy.exists renpy.file renpy.open_file "
                      "renpy.call_screen renpy.show_screen renpy.hide_screen renpy.transition renpy.save renpy.load "
                      "renpy.can_load renpy.list_saved_games renpy.seen_image renpy.has_screen renpy.get_attributes "
                      "renpy.music.get_playing renpy.music.is_playing renpy.restart_interaction renpy.full_restart "
                      "renpy.call_in_new_context renpy.invoke_in_new_context renpy.add_layer renpy.register_statement "
                      "Jump Call Show Hide ShowMenu ShowTransient ToggleScreen Play Queue Stop SetVariable "
                      "SetScreenVariable SetField SetDict SetLocalVariable ToggleVariable ToggleField ToggleDict "
                      "Preference FileSave FileLoad FileAction FileSlotName FilePage FileTime FileScreenshot "
                      "FileSaveName Image im.Image im.Scale im.Composite im.MatrixColor Movie Transform At "
                      "getattr setattr hasattr delattr isinstance open os.path.join os.path.exists re.compile "
                      "re.match re.search re.sub re.split re.findall style.rebuild config.keymap.get "
                      "persistent._clear renpy.get_widget renpy.get_displayable renpy.variant renpy.mobile "
                      "build.classify build.archive build.documentation gui.init Style Fixed Solid Frame "
                      "renpy.random.choice renpy.easy.displayable renpy.display.im.Image MusicRoom Gallery "
                      "renpy.pause renpy.with_statement renpy.music.set_queue_empty_callback "
                      "renpy.store.__dict__.get globals locals vars".split()))

RPY_STR_LIT = r"""(?:[uUbBfF]?[rR]?|[rR][uUbBfF]?)(?:\"\"\"(?:\\.|(?!\"\"\")[\s\S])*\"\"\"|'''(?:\\.|(?!''')[\s\S])*'''|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*')"""
_RPY_LIT_ONLY = re.compile(r"^\s*(?:(_p|__|_)\s*\(\s*)?(" + RPY_STR_LIT + r")\s*\)?\s*$")


def _py_literal(src):
    import ast as _ast
    if re.match(r"[bBfF]|[rR][bBfF]", src):
        return None
    try:
        v = _ast.literal_eval(src)
    except Exception:  # noqa: BLE001
        return None
    return v if isinstance(v, str) else None


def rpy_underscore_p(s):
    """Как _p() в Ren'Py: строки склеиваются в абзацы, пустая строка — новый абзац."""
    lines = [i.strip() for i in s.split("\n")]
    if lines and not lines[0]:
        lines.pop(0)
    if lines and not lines[-1]:
        lines.pop()
    rv, para = "", []
    for line in lines:
        if not line:
            rv += " ".join(para) + "\n\n"
            para = []
        elif re.search(r"\{p[^}]*\}$", line):
            para.append(line)
            rv += " ".join(para)
            para = []
        else:
            para.append(line)
    return rv + " ".join(para)


def rpy_literal_arg(code):
    """Аргумент экрана: "Hello" или _("Hello") → Hello (иначе None)."""
    m = _RPY_LIT_ONLY.match(code or "")
    if not m:
        return None
    v = _py_literal(m.group(2))
    if v is not None and m.group(1) == "_p":
        v = rpy_underscore_p(v)
    return v


def rpy_prose(s):
    """Строка из кода Python похожа на текст для игрока (а не на имя картинки, метку, путь, ключ)."""
    t = s.strip()
    if not t or len(t) > 6000:
        return False
    plain = re.sub(r"\{[^{}]*\}|\[[^\[\]]*\]", " ", t).strip()
    if not re.search(r"[^\W\d_]{2,}", plain):
        return False
    if FILEY.search(t) or re.search(r"\.(?:rpym?c?|rpa|py|txt|png|jpe?g|webp|avif|ogg|mp3|wav|opus|webm|mkv|"
                                   r"ttf|otf|json|ttc|svg)\b", t, re.I):
        return False
    if re.search(r"[^\x00-\x7f]", plain) and re.search(r"[^\W\d_]", plain):
        return True  # текст не на английском (кириллица, иероглифы...) — точно не ключ
    if "/" in t and " " not in t or re.fullmatch(r"#[0-9a-fA-F]{3,8}", t):
        return False
    words = plain.split()
    if len(words) >= 2:
        if looks_code(t) or re.search(r"[{}]\s*$|^\s*[\[{(]|==|!=|\w\(|\bdef\b|\bimport\b|\blambda\b", plain):
            return False
        if plain == plain.lower() and len(words) <= 3 and not re.search(r"[.!?…:,;'\"]", plain):
            return False  # "bg room", "sylvie green smile" — имена картинок
        return True
    w = words[0] if words else ""
    return bool(re.fullmatch(r"[A-Z][a-z]+(?:[-'][A-Za-z]+)*[.!?…:,]*|[A-Za-z]+[.!?…]+", w))


def rpy_py_strings(code):
    """Строковые литералы из кода Python: [(значение, имя вызова, в который передан, номер аргумента)]."""
    import tokenize as _tok
    out = []
    try:
        toks = [t for t in _tok.generate_tokens(_io.StringIO(code).readline)
                if t.type not in (_tok.NL, _tok.NEWLINE, _tok.COMMENT, _tok.INDENT, _tok.DEDENT)]
    except Exception:  # noqa: BLE001 — не Python 3 (старый код Python 2) — по регулярке
        for m in re.finditer(r"(?<![\w.])([A-Za-z_][\w.]*)?\s*(\()?\s*(" + RPY_STR_LIT + ")", code or ""):
            v = _py_literal(m.group(3))
            if v is not None:
                out.append((v, m.group(1) if m.group(2) else "", 0))
        return out
    stack = []  # открытые скобки: [имя вызова, номер аргумента]
    i, n = 0, len(toks)
    while i < n:
        t = toks[i]
        if t.type == _tok.OP:
            if t.string in "([{":
                name = ""
                if t.string == "(" and i > 0 and toks[i - 1].type == _tok.NAME:
                    j = i - 1
                    parts = [toks[j].string]
                    while j >= 2 and toks[j - 1].string == "." and toks[j - 2].type == _tok.NAME:
                        parts.insert(0, toks[j - 2].string)
                        j -= 2
                    name = ".".join(parts)
                stack.append([name, 0, t.string])
            elif t.string in ")]}":
                if stack:
                    stack.pop()
            elif t.string == "," and stack:
                stack[-1][1] += 1
            i += 1
            continue
        if t.type == _tok.STRING:
            vals = []
            while i < n and toks[i].type == _tok.STRING:  # "abc" "def" — одна строка
                vals.append(_py_literal(toks[i].string))
                i += 1
            if all(v is not None for v in vals):
                kw = i - len(vals) - 1  # аргумент вида name="..." — имя
                key = toks[kw - 1].string if kw >= 1 and toks[kw].string == "=" and toks[kw - 1].type == _tok.NAME else ""
                call, argn = (stack[-1][0], stack[-1][1]) if stack else ("", 0)
                out.append(("".join(vals), call if not key else call + ":" + key, argn))
            continue
        i += 1
    return out


def rpy_scan_python(code, ui):
    """Подписи из кода Python: _("…"), __(), _p(), Notify, Character("Имя"), renpy.input... + строки, похожие на текст."""
    for v, call, argn in rpy_py_strings(code or ""):
        base, _, kw = call.partition(":")
        if kw in ("tooltip", "alt", "text", "caption", "prompt", "message", "title", "label", "what"):
            ok = True
        elif kw:
            ok = rpy_prose(v) and base not in RPY_CODE_CALLS
        elif base in ("_", "__", "_p", "___"):
            ok = True
            if base == "_p":
                v = rpy_underscore_p(v)
        elif base in RPY_TEXT_CALLS:
            ok = argn == 0 or rpy_prose(v)
            if base in ("renpy.say", "renpy.display_say") and argn == 0:
                ok = rpy_prose(v)
        elif base in RPY_CODE_CALLS or base.startswith(("renpy.music.", "renpy.sound.", "renpy.audio.", "im.",
                                                         "os.", "re.", "json.", "persistent.")):
            ok = False
        else:
            ok = rpy_prose(v)
        if ok and v.strip():
            ui.append(v)


# --- .rpyc: обход дерева без Ren'Py ---
SL_TEXT_DISPLAYABLES = ("Text", "text", "textbutton", "label", "Label", "TextButton")


def rpy_scan_nodes(stmts, say, ui):
    """Обход дерева из .rpyc: реплики и пункты меню — в say (их пропускает say_menu_text_filter), подписи — в ui."""
    seen, stack = set(), [(stmts, False)]
    while stack:
        o, in_screen = stack.pop()
        if o is None or isinstance(o, (int, float, bytes)):
            continue
        if isinstance(o, str):
            if isinstance(o, RpyStr):
                rpy_scan_python(str(o), ui)
            continue
        if id(o) in seen:
            continue
        seen.add(id(o))
        if isinstance(o, dict):
            stack.extend((v, in_screen) for v in list(o.values()))
            continue
        if isinstance(o, (list, tuple, set, frozenset)):
            stack.extend((v, in_screen) for v in o)
            continue
        if not isinstance(o, RpyNode):
            continue
        name, mod = o._rname, o._rmod
        d = o.__dict__
        if name in ("Translate", "TranslateSay") and d.get("language") not in (None, ""):
            continue  # готовый перевод игры на другой язык (tl/…)
        if name in ("TranslateString", "TranslateBlock", "TranslateEarlyBlock", "TranslatePython", "Testcase"):
            continue
        if name in ("Say", "TranslateSay"):
            w = d.get("what")
            if isinstance(w, str) and w.strip():
                say.append(str(w))
            who = d.get("who")
            if isinstance(who, str) and not d.get("who_fast"):
                v = rpy_literal_arg(who)
                if v:
                    ui.append(v)
        elif name == "Menu":
            for it in d.get("items") or []:
                if isinstance(it, (list, tuple)) and it and isinstance(it[0], str) and it[0].strip():
                    say.append(str(it[0]))
        elif name == "PyCode":
            st = d.get("_rstate")
            src = st[1] if isinstance(st, tuple) and len(st) > 1 else d.get("source")
            if isinstance(src, str):
                rpy_scan_python(str(src), ui)
            continue
        elif name == "UserStatement":
            line = d.get("line")
            if isinstance(line, str):
                rpy_scan_python(re.sub(r"^\s*[\w.]+", "", line), ui)
        scr = in_screen or mod.startswith(("renpy.sl2", "renpy.screenlang"))
        if scr:
            disp = d.get("displayable")
            dname = getattr(disp, "_rname", "") or str(disp or "")
            texty = any(x in dname for x in SL_TEXT_DISPLAYABLES) or d.get("style") in ("text", "button", "label")
            lang_btn = any(isinstance(kv, (list, tuple)) and len(kv) == 2 and "Language(" in str(kv[1])
                           for kv in d.get("keyword") or [])
            for code in d.get("positional") or []:
                if isinstance(code, str):
                    v = rpy_literal_arg(code)
                    if v and lang_btn:
                        continue  # «日本語», «Русский» — названия языков в меню выбора не переводим
                    if v and (texty or rpy_prose(v)):
                        ui.append(v)
                    elif not v:
                        rpy_scan_python(str(code), ui)
            for kv in d.get("keyword") or []:
                if isinstance(kv, (list, tuple)) and len(kv) == 2 and isinstance(kv[1], str):
                    v = rpy_literal_arg(kv[1]) if kv[0] in ("text", "tooltip", "alt", "caption") else None
                    if v:
                        ui.append(v)
                    else:
                        rpy_scan_python(str(kv[1]), ui)
        stack.extend((v, scr) for k, v in list(d.items())
                     if k not in ("_rstate", "_rnew", "_rargs", "filename", "_name", "name", "positional", "keyword"))


# --- .rpy: исходники (если .rpyc нет или он старее) ---
_RPY_Q = {q: re.compile(q + (r"(?:[^\\%s]|\\[\s\S]|%s(?!%s))*" % (q[0], q[0], q[0] * 2) if len(q) == 3 else
                             r"(?:[^\\%s]|\\[\s\S])*" % q) + q)
          for q in ('"""', "'''", "```", '"', "'", "`")}


def rpy_logical_lines(text):
    """[(отступ, текст, номер строки)] — как list_logical_lines в Ren'Py: строки и скобки склеивают строки файла."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff") + "\n"
    out, buf, depth, i, n = [], [], 0, 0, len(text)
    seg, lineno, start_no = 0, 1, 1
    while i < n:
        c = text[i]
        if c in "\"'`":
            m = None
            for q in (c * 3, c):
                if text.startswith(q, i):
                    m = _RPY_Q[q].match(text, i)
                    if m:
                        break
            if m:
                lineno += text.count("\n", i, m.end())
                i = m.end()
            else:
                i += 1
            continue
        if c == "#":
            buf.append(text[seg:i])
            i = seg = text.find("\n", i)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth = max(0, depth - 1)
        elif c == "\\" and text.startswith("\\\n", i):
            buf.append(text[seg:i])
            i = seg = i + 2
            lineno += 1
            continue
        elif c == "\n":
            lineno += 1
            if depth == 0:
                buf.append(text[seg:i])
                line = "".join(buf)
                if line.strip():
                    out.append((len(line) - len(line.lstrip(" ")), line.strip(), start_no))
                buf, seg, start_no = [], i + 1, lineno
        i += 1
    return out


def _rpy_dequote(m):
    c = m.group(1)
    if c[0] == "u" and m.group(2):
        return chr(int(m.group(2), 16))
    return {"{": "{{", "[": "[[", "%": "%%", "n": "\n"}.get(c, c)


def rpy_lexer_string(inner, raw=False):
    """Строка реплики так, как её видит Ren'Py (lexer.string): пробелы/переносы → пробел, \\n, \\{ ... """
    if raw:
        return [inner]
    out = [re.sub(r"\\(u([0-9a-fA-F]{1,4})|.)", _rpy_dequote, re.sub(r"[ \n]+", " ", inner))]
    if re.search(r"[\t\r\f\v]", inner):  # Ren'Py 7 сжимал любые пробельные символы
        out.append(re.sub(r"\\(u([0-9a-fA-F]{1,4})|.)", _rpy_dequote, re.sub(r"\s+", " ", inner)))
    return out


def rpy_lexer_triple(inner, raw=False, mondel="\n\n"):
    """Строка в тройных кавычках (Ren'Py 8: «монолог» — абзацы становятся отдельными репликами)."""
    if raw:
        return [inner]
    s = re.sub(r" *\n *", "\n", inner)
    out = []
    for part in (s.split(mondel) if mondel else [s]):
        part = part.strip()
        if not part or part == "{clear}":
            continue
        part = re.sub(r"[ \n]+", " ", part) if mondel else re.sub(r" +", " ", part)
        out.append(re.sub(r"\\(u([0-9a-fA-F]{1,4})|.)", _rpy_dequote, part))
    return out


def rpy_read_string(line, pos):
    """Строка Ren'Py в позиции pos: (сырая?, тройная?, содержимое, конец) или None."""
    raw = line[pos:pos + 1] == "r" and line[pos + 1:pos + 2] in "\"'`" and line[pos + 1:pos + 2] != ""
    p = pos + 1 if raw else pos
    c = line[p:p + 1]
    if not c or c not in "\"'`":
        return None
    for q in (c * 3, c):
        if line.startswith(q, p):
            m = _RPY_Q[q].match(line, p)
            if m:
                return raw, len(q) == 3, m.group(0)[len(q):-len(q)], m.end()
    return None


RPY_KEYWORDS = set(("label jump call return show scene hide with play queue stop voice pause window image transform "
                    "style init define default python translate menu if elif else while for pass nvl camera screen "
                    "layeredimage testcase rpy early at onlayer expression zorder behind as contains parallel block "
                    "choice on function time event repeat").split())


def rpy_parse_say(line, mondel):
    """Реплика: [персонаж] [атрибуты] "текст" [with ... / id ... / (аргументы)] → (имя-строка или None, [тексты])."""
    s0 = rpy_read_string(line, 0)
    who = None
    if s0:
        rest = line[s0[3]:].lstrip()
        s1 = rpy_read_string(rest, 0)
        if s1 and not s0[1]:
            who = _py_literal(line[:s0[3]])  # "Эйлин" "Привет" — имя строкой
            s0, line = s1, rest
    else:
        m = re.match(r"[A-Za-z_]\w*(?:\.\w+)*", line)
        if not m or m.group(0) in RPY_KEYWORDS:
            return None
        pos = m.end()
        while True:
            m2 = re.compile(r"\s*(?:@\s*)?").match(line, pos)
            pos = m2.end()
            s0 = rpy_read_string(line, pos)
            if s0:
                break
            m3 = re.compile(r"-?[\w.]+").match(line, pos)
            if not m3 or m3.end() == pos:
                return None
            pos = m3.end()
    raw, triple, inner, end = s0
    rest = line[end:].strip()
    if rest and not re.match(r"(?:with|id|nointeract)\b|\(", rest):
        return None
    texts = rpy_lexer_triple(inner, raw, mondel) if triple else rpy_lexer_string(inner, raw)
    return who, texts


def rpy_scan_source(text, say, ui):
    """Тексты из исходника .rpy (без Ren'Py): реплики, меню, экраны, код Python."""
    lines = rpy_logical_lines(text)
    stack, i, mondel = [], 0, "\n\n"
    while i < len(lines):
        ind, L, _ = lines[i]
        while stack and ind <= stack[-1][0]:
            stack.pop()
        ctx = stack[-1][1] if stack else "script"
        if ctx == "skip":
            i += 1
            continue
        new = None
        w = re.match(r"\$|[A-Za-z_]\w*", L)
        w = w.group(0) if w else ""
        if ctx == "screen":
            new = _rpy_sl_line(L, w, ui)
        elif ctx == "style":  # свойства стиля: alt _("…") и т.п.
            rpy_scan_python(re.sub(r"^\w+", "", L).rstrip(":"), ui)
            new = "style"
        else:
            if ctx == "menu":
                s = rpy_read_string(L, 0)
                if s and L.endswith(":"):
                    say.extend(rpy_lexer_string(s[2], s[0]))  # пункт меню
                    stack.append((ind, "script"))
                    i += 1
                    continue
            new = _rpy_script_line(L, w, say, ui, mondel)
            if new == "monologue":
                m = re.search(r"monologue\s+(\w+)", L)
                mondel = {"single": "\n", "none": None}.get(m.group(1) if m else "", "\n\n")
                new = None
        if new == "python":  # блок кода Python — целиком
            j, block = i + 1, []
            while j < len(lines) and lines[j][0] > ind:
                block.append(lines[j])
                j += 1
            if block:
                base = min(b[0] for b in block)
                rpy_scan_python("\n".join(" " * (b[0] - base) + b[1] for b in block), ui)
            i = j
            continue
        if new and L.endswith(":"):
            stack.append((ind, new))
        i += 1


def _rpy_script_line(L, w, say, ui, mondel="\n\n"):
    if w == "$":
        rpy_scan_python(L[1:], ui)
        return None
    if w == "init":
        m = re.match(r"init(?:\s+-?\d+)?\s*(.*)$", L, re.S)
        rest = m.group(1) if m else ""
        if rest.startswith("python"):
            return "python" if L.endswith(":") else None
        if rest in ("", ":"):
            return "script"
        if rest.startswith("offset"):
            return None
        w2 = re.match(r"\$|[A-Za-z_]\w*", rest)
        return _rpy_script_line(rest, w2.group(0) if w2 else "", say, ui, mondel)
    if w == "python":
        return "python" if L.endswith(":") else None
    if w in ("define", "default"):
        m = re.match(r"\w+\s+(?:-?\d+\s+)?[\w.]+\s*(?:\[[^\]]*\])?\s*[+|]?=\s*([\s\S]*)$", L)
        if m:
            rpy_scan_python(m.group(1), ui)
        return None
    if w == "image":
        if "=" in L and not L.endswith(":"):
            rpy_scan_python(L.split("=", 1)[1], ui)
            return None
        return "skip"
    if w == "screen":
        return "screen"
    if w == "menu":
        return "menu"
    if w in ("label", "if", "elif", "else", "while", "for"):
        return "script"
    if w == "translate":
        m = re.match(r"translate\s+(\w+)\s+(\w+)", L)
        return "script" if m and m.group(1) == "None" and m.group(2) not in ("strings", "python", "style") else "skip"
    if w == "rpy":
        return "monologue" if "monologue" in L else None
    if w == "style":
        return "style"
    if w in ("show", "scene"):
        m = re.match(r"show\s+text\s+(" + RPY_STR_LIT + ")", L)
        if m:
            v = _py_literal(m.group(1))
            if v:
                ui.append(v)
            return "skip"
    if w in RPY_KEYWORDS:  # show screen x(_("…")), call screen confirm(message="…") ...
        rpy_scan_python(L[len(w):].rstrip(":"), ui)
        return "skip"
    r = rpy_parse_say(L, mondel)
    if r:
        who, texts = r
        say.extend(t for t in texts if t.strip())
        if who:
            ui.append(who)
        return "skip"
    return "script"  # свой оператор игры (renpy.register_statement) — в его блоке обычно обычный сценарий


def _rpy_sl_line(L, w, ui):
    if w == "$":
        rpy_scan_python(L[1:], ui)
        return None
    if w == "python":
        return "python" if L.endswith(":") else None
    if w in ("default", "define"):
        m = re.match(r"\w+\s+[\w.]+\s*=\s*([\s\S]*)$", L)
        if m:
            rpy_scan_python(m.group(1), ui)
        return None
    rest = L[len(w):]
    if "Language(" in L:  # кнопки выбора языка: названия языков не переводим
        return "screen"
    if w in ("text", "textbutton", "label"):
        m = re.match(r"\s*((?:(?:_p|__|_)\s*\(\s*)?" + RPY_STR_LIT + r"\s*\)?)", rest)
        if m:
            v = rpy_literal_arg(m.group(1))
            if v:
                ui.append(v)
            rest = rest[m.end():]
    for m in re.finditer(r"\b(?:tooltip|alt|caption)\s+(" + RPY_STR_LIT + ")", rest):
        v = _py_literal(m.group(1))
        if v:
            ui.append(v)
    rpy_scan_python(rest.rstrip(":"), ui)
    return "screen"


# ---------------------------------------------------------------------------
# Где игра: папка ПК (game/) или распакованный APK (assets/x-game)
# ---------------------------------------------------------------------------

RPY_EXTS = (".rpy", ".rpyc", ".rpym", ".rpymc", ".rpa", ".rpi")
RUT_RPY = "zz_rut_translate"
RUT_JSON = "rut_translation.json"


def _rpy_has_scripts(d, pre=""):
    try:
        names = os.listdir(d)
    except OSError:
        return False
    return any(n.lower().endswith(RPY_EXTS) and n.startswith(pre) for n in names)


def rpy_find_game(path):
    """Папка игры Ren'Py → {"root", "game", "pre" ("x-" в APK), "apk", "common"}; None — это не Ren'Py."""
    p = os.path.abspath(path)
    if os.path.isfile(p):
        p = os.path.dirname(p)
    for base in (p, os.path.dirname(p), os.path.dirname(os.path.dirname(p))):
        for sub, pre in (("assets/x-game", "x-"), ("assets/game", "")):
            g = os.path.join(base, *sub.split("/"))
            if os.path.isdir(g) and _rpy_has_scripts(g, pre):
                common = os.path.join(base, "assets", "x-renpy", "x-common") if pre else ""
                return {"root": base, "game": g, "pre": pre, "apk": True, "common": common}
        if os.path.basename(base).lower() in ("x-game",) and _rpy_has_scripts(base, "x-"):
            return {"root": os.path.dirname(os.path.dirname(base)), "game": base, "pre": "x-", "apk": True,
                    "common": os.path.join(os.path.dirname(base), "x-renpy", "x-common")}
        g = os.path.join(base, "game")
        if os.path.isdir(g) and _rpy_has_scripts(g):
            return {"root": base, "game": g, "pre": "", "apk": False,
                    "common": os.path.join(base, "renpy", "common")}
        if os.path.basename(base).lower() == "game" and _rpy_has_scripts(base):
            return {"root": os.path.dirname(base), "game": base, "pre": "", "apk": False,
                    "common": os.path.join(os.path.dirname(base), "renpy", "common")}
    # macOS (.app/Contents/Resources/autorun/game) и прочие вложенные папки — ищем неглубоко
    for dirpath, dirs, _files in os.walk(p):
        if dirpath[len(p):].count(os.sep) >= 4:
            dirs[:] = []
            continue
        dirs[:] = [x for x in dirs if not x.startswith(".") and x not in ("saves", "cache", "tl", "renpy", "lib")]
        for x in dirs:
            if x.lower() == "game" and _rpy_has_scripts(os.path.join(dirpath, x)):
                return rpy_find_game(os.path.join(dirpath, x))
    return None


def _rpy_logical(rel, pre):
    """Имя файла так, как его видит Ren'Py (в APK у каждой части пути приставка «x-»)."""
    parts = rel.replace("\\", "/").split("/")
    if pre:
        parts = [x[len(pre):] if x.startswith(pre) else x for x in parts]
    return "/".join(parts)


def rpy_list_scripts(g):
    """Сценарии игры: {логическое имя без расширения: {"rpy": путь, "rpyc": (откуда, как прочитать)}}."""
    scripts, archives = {}, []
    for dirpath, dirs, files in os.walk(g["game"]):
        rel_dir = os.path.relpath(dirpath, g["game"])
        ldir = "" if rel_dir == "." else _rpy_logical(rel_dir, g["pre"])
        top = ldir.split("/")[0]
        if top in ("tl", "saves", "cache", "__pycache__"):
            dirs[:] = []
            continue
        for fn in files:
            lname = _rpy_logical(fn, g["pre"])
            low = lname.lower()
            full = os.path.join(dirpath, fn)
            if low.startswith((RUT_RPY.lower(), "rut_translation")):
                continue
            logical = (ldir + "/" if ldir else "") + lname
            if low.endswith((".rpa", ".rpi")):
                archives.append(full)
            elif low.endswith((".rpyc", ".rpymc")):
                scripts.setdefault(logical.rsplit(".", 1)[0], {})["rpyc"] = ("file", full)
            elif low.endswith((".rpy", ".rpym")):
                scripts.setdefault(logical.rsplit(".", 1)[0], {})["rpy"] = full
    for arc in sorted(archives):
        idx = rpa_index(arc)
        if not idx:
            if arc.lower().endswith(".rpa"):
                print(f"  архив {os.path.basename(arc)}: формат не распознан (изменён автором игры) — пропущен",
                      file=sys.stderr)
            continue
        for name, entry in idx.items():
            low = name.lower()
            if name.split("/")[0] == "tl" or RUT_RPY in low:
                continue
            if low.endswith((".rpyc", ".rpymc")):
                scripts.setdefault(name.rsplit(".", 1)[0], {}).setdefault("rpyc", ("rpa", arc, entry))
            elif low.endswith((".rpy", ".rpym")):
                scripts.setdefault(name.rsplit(".", 1)[0], {}).setdefault("rpy_arc", (arc, entry))
    return scripts


def _rpy_load_rpyc(src):
    if src[0] == "file":
        with open(src[1], "rb") as f:
            return f.read()
    return rpa_read(src[1], src[2])


def rpy_collect(g):
    """Все тексты игры: (реплики и пункты меню, подписи интерфейса, статистика)."""
    say, ui = [], []
    st = {"rpyc": 0, "rpy": 0, "bad": []}
    for name, info in sorted(rpy_list_scripts(g).items()):
        rpy, rpyc = info.get("rpy"), info.get("rpyc")
        use_rpy = bool(rpy) and (not rpyc or rpyc[0] == "file" and
                                 os.path.getmtime(rpy) > os.path.getmtime(rpyc[1]) + 2)
        if rpyc and not use_rpy:
            try:
                res = rpyc_read(_rpy_load_rpyc(rpyc))
                stmts = res[1] if isinstance(res, tuple) and len(res) == 2 else None
                rpy_scan_nodes(stmts, say, ui)
                st["rpyc"] += 1
                continue
            except Exception as e:  # noqa: BLE001 — тогда из исходника, если он есть
                st["bad"].append(f"{name}.rpyc ({e.__class__.__name__})")
                if not rpy:
                    continue
        src = None
        if rpy:
            with open(rpy, "rb") as f:
                src = f.read()
        elif info.get("rpy_arc"):
            src = rpa_read(*info["rpy_arc"])
        if src is not None:
            rpy_scan_source(src.decode("utf-8", "replace"), say, ui)
            st["rpy"] += 1
    return say, ui, st


# ---------------------------------------------------------------------------
# Перевод строки Ren'Py: теги {b}…{/b}, подстановки [name], {{ [[ \n — защищены
# ---------------------------------------------------------------------------

RPY_SOLO_TAGS = set("w p nw fast done image space vspace clear k".split())
RPY_PCT = re.compile(r"%(?:\([\w.]+\))?[-+#0]*\d*(?:\.\d+)?[A-Za-z%]")  # %s, %(name)s, %A (дата), %%


def rpy_mark(s):
    """Текст Ren'Py → (текст с метками ⟦n⟧, куски по номерам, {открывающая: закрывающая}) или None (нечего переводить)."""
    toks, out, pairs, stack = [], [], {}, []
    i, n = 0, len(s)

    def tok(x):
        toks.append(x)
        out.append(f"⟦{len(toks) - 1}⟧")
        return len(toks) - 1
    while i < n:
        c = s[i]
        if c == "{":
            if s.startswith("{{", i):
                tok("{{")
                i += 2
                continue
            j = s.find("}", i)
            if j < 0:
                out.append(s[i:])
                break
            tag = s[i + 1:j]
            k = tok(s[i:j + 1])
            name = re.match(r"/?([^=\s}]*)", tag).group(1)
            if tag.startswith("/"):
                for x in range(len(stack) - 1, -1, -1):
                    if stack[x][0] == name:
                        pairs[stack[x][1]] = k
                        del stack[x:]
                        break
            elif name and not name.startswith("#") and name not in RPY_SOLO_TAGS:
                stack.append((name, k))
            i = j + 1
        elif c == "[":
            if s.startswith("[[", i):
                tok("[[")
                i += 2
                continue
            depth, j = 0, i
            while j < n:
                if s[j] == "[":
                    depth += 1
                elif s[j] == "]":
                    depth -= 1
                    if depth == 0:
                        break
                elif s[j] in "\"'":
                    q = s[j]
                    j += 1
                    while j < n and s[j] != q:
                        j += 2 if s[j] == "\\" else 1
                j += 1
            if j >= n:
                out.append(s[i:])
                break
            tok(s[i:j + 1])
            i = j + 1
        elif c == "\n":
            tok("\n")
            i += 1
        elif c == "%" and RPY_PCT.match(s, i):
            m = RPY_PCT.match(s, i)
            tok(m.group(0))
            i = m.end()
        else:
            out.append(c)
            i += 1
    text = "".join(out)
    plain = re.sub(r"⟦\d+⟧", " ", text)
    if not re.search(r"[^\W\d_]{2}|[^\W\d_\x00-ɏ]", plain):
        return None  # нет слов: «H», «<», «[name]», «{#quick_page}Q»
    return text, toks, {str(a): b for a, b in pairs.items()}


def rpy_unmark(res, toks):
    """Перевод с метками → текст Ren'Py. Новые { [ из переводчика экранируются."""
    res = re.sub(r"\s*\n\s*", " ", res)  # переносы — только там, где они были (метка)
    res = res.replace("{", "{{").replace("[", "[[")
    res = re.sub(r"⟦\s*(\d+)\s*⟧", lambda m: toks[int(m.group(1))], res)
    return res


def _rpy_fix_spaces(src, res, toks):
    """Пробелы у меток как в оригинале: «{b}Слово{/b}» без лишних пробелов внутри тегов."""
    for k, t in enumerate(toks):
        m = f"⟦{k}⟧"
        if t.startswith("{") and not t.startswith("{/") and t not in ("{{",):
            res = re.sub(re.escape(m) + r"\s+", m, res) if not re.search(re.escape(m) + r"\s", src) else res
        if t.startswith("{/"):
            res = re.sub(r"\s+" + re.escape(m), m, res) if not re.search(r"\s" + re.escape(m), src) else res
    return res


def translate_marked(tr, items):
    """Фразы с метками ⟦n⟧ → переводы (кэш). items: [(фраза, {"p": пары тегов} или None)].
    Фразы с парными тегами — HTML-ом (как Chrome), остальные — обычным путём; испорченные метки — ещё раз по одной."""
    todo = [(k, h) for k, h in dict(items).items() if not tr.has(k)]
    if not todo:
        return
    tr._pool() if tr.engine in ("free", "google") else None
    html = live_pa_html(tr, [(k, {"p": h["p"]}) for k, h in todo if h and h.get("p")])
    for k, r in html.items():
        tr.cache[k] = r
    tr.prefetch([k for k, _ in todo if k not in html])
    bad = [k for k, _ in todo if tr.has(k) and LIVE_MARK.search(k) and not live_marks_ok(k, tr.peek(k))]
    if bad and not tr.offline:
        tr.halt.clear()

        def again(t):
            try:
                return t, tr.translate_batch([t])[0]
            except Exception:  # noqa: BLE001
                return t, None
        for t, r in Translator._parallel(again, bad[:400]):
            if live_marks_ok(t, r):
                tr.cache[t] = r
    tr.save(force=True)


# ---------------------------------------------------------------------------
# Модуль для игры: перевод подставляется при показе текста
# ---------------------------------------------------------------------------

RPY_RUNTIME = r'''
def _rut_setup():
    import json
    import renpy as R
    E = R.exports
    try:
        f = E.file("rut_translation.json")
        try:
            raw = f.read()
        finally:
            f.close()
        if not isinstance(raw, type(u"")):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
    except Exception:
        return
    T = data.get("t") or {}
    if not T:
        return

    state = {"off": False}

    def tr(s):
        try:
            if state["off"]:
                return s
            v = T.get(s)
        except Exception:
            return s
        return s if v is None else v

    # Подписи интерфейса и всё, что показывает Text: renpy.translation.translate_string
    TL = R.translation
    orig = getattr(TL, "_rut_orig", None) or TL.translate_string
    TL._rut_orig = orig

    def translate_string(s, *args, **kwargs):
        return tr(orig(s, *args, **kwargs))
    TL.translate_string = translate_string
    if getattr(E, "translate_string", None) is orig:
        E.translate_string = translate_string
    st = R.store
    if getattr(st, "_" + "_", None) is orig:
        setattr(st, "_" + "_", translate_string)

    # Реплики и пункты меню — до подстановки [переменных]
    C = R.config
    prev = C.say_menu_text_filter
    if getattr(prev, "_rut", False):
        prev = prev._rut_prev

    def say_filter(s):
        s = tr(s)
        if prev is not None:
            s = prev(s)
        return s
    say_filter._rut = True
    say_filter._rut_prev = prev
    C.say_menu_text_filter = say_filter

    # Alt+T — показать оригинал / перевод (до выхода из игры)
    def toggle():
        state["off"] = not state["off"]
        try:
            E.notify(data.get("off" if state["off"] else "on") or "")
        except Exception:
            pass
        E.restart_interaction()
    try:
        C.keymap["rut_toggle"] = ["alt_K_t"]
        C.underlay.append(R.display.behavior.Keymap(rut_toggle=toggle))
    except Exception:
        pass


_rut_setup()
del _rut_setup
'''


def rpy_runtime_rpy(lang):
    body = "\n".join(("    " + x if x.strip() else "") for x in RPY_RUNTIME.strip("\n").split("\n"))
    return (f"# sugarcube_translate: машинный перевод на «{lang}» — текст подменяется только при показе.\n"
            f"# Вернуть оригинал: удалите {RUT_RPY}.rpy, {RUT_RPY}.rpyc и {RUT_JSON} (или Alt+T в игре).\n"
            "init 999 python:\n" + body + "\n")


def rpy_template(g):
    """Образец «init python:» из .rpyc самой игры: по нему собираем свой .rpyc (для APK) — тех же классов
    и той же версии формата. Ключ (--lock) у всех файлов игры один — берём из образца."""
    cands = [info["rpyc"] for _n, info in sorted(rpy_list_scripts(g).items()) if info.get("rpyc")]
    if g.get("common") and os.path.isdir(g["common"]):
        cands += [("file", os.path.join(g["common"], fn)) for fn in sorted(os.listdir(g["common"]))
                  if fn.lower().endswith(".rpyc")]
    for src in cands:
        try:
            raw = _rpy_load_rpyc(src)
            data, stmts = rpyc_read(raw)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(data, dict) or "version" not in data:
            continue
        for node in stmts or []:
            if not isinstance(node, RpyNode) or node._rname != "Init":
                continue
            blk = node.__dict__.get("block")
            if not (isinstance(blk, list) and len(blk) == 1 and isinstance(blk[0], RpyNode)
                    and blk[0]._rname == "Python"):
                continue
            code = blk[0].__dict__.get("code")
            if isinstance(code, RpyNode) and isinstance(code.__dict__.get("_rstate"), tuple):
                return {"data": data, "init": node, "rpc2": raw[:10] == RPC2, "key": data.get("key", "unlocked")}
    return None


def _rpy_clone(node, changes, add=()):
    o = object.__new__(type(node))
    for k in ("_rnew", "_rargs"):
        if k in node.__dict__:
            o.__dict__[k] = node.__dict__[k]
    st = node.__dict__.get("_rstate")
    dicts = [dict(x) for x in _rpy_state_dicts(st)]
    for k, v in changes.items():
        v = o if v is _rpy_clone else v
        hit = [x for x in dicts if k in x]
        for x in hit:
            x[k] = v
        if not hit and k in add and dicts:
            dicts[-1][k] = v
    if isinstance(st, dict):
        st = dicts[0]
    elif isinstance(st, tuple):
        it = iter(dicts)
        st = tuple(next(it) if isinstance(x, dict) else x for x in st)
    o.__setstate__(st)
    return o


def rpy_build_rpyc(tpl, source, fname, priority=999):
    """Свой .rpyc (init 999 python: <код>) по образцу узлов из .rpyc игры: те же классы, та же версия формата."""
    init = tpl["init"]
    py = init.__dict__["block"][0]
    code = py.__dict__["code"]
    st = list(code.__dict__["_rstate"])
    st[1] = source
    if isinstance(st[2], tuple) and len(st[2]) >= 2:
        st[2] = (fname, 1) + tuple(st[2][2:])
    if len(st) >= 6:
        st[5] = None  # хэш кода — Ren'Py посчитает сам
    new_code = object.__new__(type(code))
    new_code.__dict__.update({k: v for k, v in code.__dict__.items() if k in ("_rnew", "_rargs")})
    new_code.__setstate__(tuple(st))
    stamp = int(time.time())
    base = fname.rsplit("/", 1)[-1]

    def name_for(old, serial):
        return (base, stamp, serial) if isinstance(old, tuple) else (fname, stamp, serial)
    pyd = py.__dict__
    new_py = _rpy_clone(py, {"code": new_code, "filename": fname, "linenumber": 1, "next": None,
                             "name": name_for(pyd.get("name"), 1), "_name": name_for(pyd.get("_name"), 1),
                             "statement_start": _rpy_clone})
    ind = init.__dict__
    new_init = _rpy_clone(init, {"block": [new_py], "priority": priority, "filename": fname, "linenumber": 1,
                                 "next": None, "name": name_for(ind.get("name"), 0),
                                 "_name": name_for(ind.get("_name"), 0), "statement_start": _rpy_clone},
                          add=("priority",))
    # ссылки на другие узлы игры (кроме наших) убираем — иначе в файл попадёт весь сценарий образца
    ours = {id(new_init), id(new_py), id(new_code)}
    for node in (new_init, new_py):
        for d in _rpy_state_dicts(node.__dict__["_rstate"]):
            for k, v in list(d.items()):
                if isinstance(v, RpyNode) and id(v) not in ours:
                    d[k] = None
    data = {"version": tpl["data"]["version"], "key": tpl.get("key") or tpl["data"].get("key", "unlocked")}
    return rpyc_pack(rpy_dumps((data, [new_init])), tpl["rpc2"])


def rpy_write(g, table, lang, keep_tpl=None):
    """Кладёт в игру словарь и модуль перевода. Возвращает список записанных файлов."""
    pre = g["pre"]
    data = {"v": 1, "lang": lang, "t": table,
            "on": "Перевод: включён (Alt+T)" if lang.startswith(("ru", "uk", "be")) else f"Translation: on ({lang}, Alt+T)",
            "off": "Перевод: выключен — оригинал (Alt+T)" if lang.startswith(("ru", "uk", "be"))
            else "Translation: off — original (Alt+T)"}
    out = []
    jpath = os.path.join(g["game"], pre + RUT_JSON)
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    out.append(jpath)
    if g["apk"]:
        tpl = keep_tpl or rpy_template(g)
        if tpl is None:
            raise RuntimeError("в игре не нашёлся ни один .rpyc с блоком «init python:» — не по чему собрать модуль")
        src = RPY_RUNTIME.strip("\n") + "\n"
        path = os.path.join(g["game"], pre + RUT_RPY + ".rpyc")
        with open(path, "wb") as f:
            f.write(rpy_build_rpyc(tpl, src, "game/" + RUT_RPY + ".rpy"))
        out.append(path)
    else:
        path = os.path.join(g["game"], RUT_RPY + ".rpy")
        old_c = path + "c"
        if os.path.exists(old_c):
            os.remove(old_c)  # прошлый наш .rpyc — Ren'Py соберёт заново
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(rpy_runtime_rpy(lang))
        out.append(path)
    return out


def rpy_remove(g):
    removed = []
    for fn in (RUT_JSON, RUT_RPY + ".rpy", RUT_RPY + ".rpyc"):
        p = os.path.join(g["game"], g["pre"] + fn)
        if os.path.exists(p):
            os.remove(p)
            removed.append(p)
    return removed


# Модуль перевода на лету для игры (Python 2 и 3, Ren'Py 6.99–8.x). Только ASCII: Ren'Py 7 сам
# переписывает не-ASCII строки в коде, а это ломает сложные выражения. Русские подписи — в RPY_LIVE_UI.
RPY_LIVE_RUNTIME = r'''
def _rut_live_setup():
    # sugarcube_translate: live machine translation for Ren'Py.
    # The game's script and code are not changed: text is translated at the moment it is shown.
    # Works with Ren'Py 6.99-8.x (Python 2 and 3). This source must stay ASCII-only.
    import json
    import os
    import re
    import sys
    import threading
    import time
    import weakref
    import renpy as R

    E = R.exports
    C = R.config
    T_TEXT = type(u"")
    T_BYTES = type(b"")
    PY2 = sys.version_info[0] == 2
    STR_TS = (T_TEXT, T_BYTES)
    MAIN = threading.current_thread()

    LOG_FILE = os.environ.get("RUT_LOG")

    def log(*args):
        try:
            msg = u"[rut] " + u" ".join(u"%s" % (a,) for a in args) + u"\n"
            if LOG_FILE:
                with open(LOG_FILE, "ab") as f:
                    f.write(msg.encode("utf-8"))
            sys.stderr.write(msg.encode("utf-8") if PY2 else msg)
        except Exception:
            pass

    def u(x):
        if isinstance(x, T_BYTES):
            try:
                return x.decode("utf-8")
            except Exception:
                return x.decode("latin-1")
        return x

    def read_game(name):
        f = E.file(name)
        try:
            return u(f.read())
        finally:
            f.close()

    try:
        DATA = json.loads(read_game("rut_translation.json"))
    except Exception as e:
        log("no translation data:", e)
        return
    if not isinstance(DATA, dict) or DATA.get("mode") != "live":
        return
    try:  # everything we hook into must exist (Ren'Py 6.99 and newer); otherwise the game runs untouched
        for _x in (R.substitutions.substitute, R.text.text.Text.set_text, R.character.ADVCharacter.__call__,
                   E.menu, E.restart_interaction, E.define_screen, E.get_screen, C.periodic_callbacks.append,
                   R.game.context, R.ui.text, R.ui.textbutton, R.display.behavior.Keymap):
            pass
    except Exception as e:
        log("this Ren'Py version is not supported:", repr(e))
        return

    CFG = DATA.get("cfg") or {}
    UI = DATA.get("ui") or {}
    if UI and not any(isinstance(v, dict) for v in UI.values()):
        UI = {"ru": UI}  # v0.10: only Russian

    def ui_lang():
        # the panel speaks the language that is shown: the game's own language when the original is shown
        return st.src if (st.off or st.lang == u"off") else st.lang

    def ui_t(k, default):
        l = ui_lang()
        d = UI.get(l) or UI.get(base_lang(l))
        if isinstance(d, dict):
            v = d.get(k)
            return v if isinstance(v, T_TEXT) and v else default
        if base_lang(l) == u"en" or base_lang(st.src) != u"en" or st.web:
            return default
        return ui_machine(default, l)  # other languages: the English text through the same translator

    def ui_machine(text, lang):
        m = st.ui_memo.setdefault(lang, {})
        r = m.get(text)
        if r is not None:
            return r
        try:
            info = mark(text.replace(u"%d", u"{#d}").replace(u"%s", u"{#s}"))
            if info is None:
                return text
            prev = st.cur_text
            st.cur_text = None
            try:
                got = lookup(info, lang, True, 1)[0]
            finally:
                st.cur_text = prev
            if not got:
                return text  # English until the translation comes (the panel is redrawn then)
            r = m[text] = got.replace(u"{#d}", u"%d").replace(u"{#s}", u"%s")
            return r
        except Exception as e:
            err_once("ui_machine", e)
            return text

    class St(object):
        pass

    st = St()
    st.src = DATA.get("src") or "en"
    st.server = CFG.get("server") or ""
    try:
        st.wait = max(0.0, min(10.0, float(CFG.get("wait", 3))))
    except Exception:
        st.wait = 3.0
    st.dicts = {}
    for l, d in (DATA.get("dicts") or {}).items():
        if isinstance(d, dict):
            st.dicts[l] = d
    st.mem = {}
    for l, d in (DATA.get("live") or {}).items():
        if isinstance(d, dict):
            st.mem[l] = dict(d)
    st.manual = {}
    st.emb_manual = {}
    for l, ks in (DATA.get("manual") or {}).items():
        if isinstance(ks, list):
            st.manual[l] = set(ks)
            st.emb_manual[l] = set(ks)
    st.langs = [x for x in (DATA.get("langs") or []) if isinstance(x, list) and len(x) >= 2]
    st.fav = [x for x in (DATA.get("fav") or []) if isinstance(x, T_TEXT)]
    st.user = {}
    st.user_manual = {}
    st.user_dict = {}
    st.fail = {}
    st.q = {}
    st.seq = 0
    st.inflight = set()
    st.events = {}
    st.waiting = {}
    st.arrived = []
    st.refresh_all = False
    st.memo = {}
    st.out = {}
    st.out_order = []
    st.rev = {}
    st.rev_order = []
    st.say_untr = {}
    st.say_untr_order = []
    st.pause_map = {}
    st.pause_order = []
    st.pause_fix = bool(CFG.get("pause_fix", True))
    st.ui_memo = {}
    st.rq = []
    st.name_tr = bool(CFG.get("names", True))
    st.fix_list = []
    st.refreshing = False
    st.later = []
    st.err_screen = (0.0, False)
    st.names = None
    st.recent = []
    st.off = False
    st.cur_text = None
    st.cur_what = None
    st.char_depth = 0
    st.reg_count = 0
    st.down_until = 0.0
    st.fails_row = 0
    st.server_down_until = 0.0
    st.server_eps = None
    st.server_why = None
    st.bad_lang = None
    st.probing = False
    st.probed = False
    st.rr = 0
    st.ssl_mode = 0
    st.ssl_ctx = None
    st.lock = threading.RLock()
    st.cond = threading.Condition(st.lock)
    st.workers = False
    st.save_due = False
    st.save_now = False
    st.last_save = 0.0
    st.saving = False
    st.panel = "main"
    st.page = 0
    st.msg = u""
    st.toast = u""
    st.toast_until = 0.0
    st.inp = {}
    st.edit = None
    st.prefs = {"lang": None, "corner": 0}
    st.ahead_from = None
    st.touched = {}
    st.err_logged = set()
    st.web = bool(getattr(R, "emscripten", False))

    MO, MC = u"\u27e6", u"\u27e7"
    MARK_RE = re.compile(u"\u27e6(\\d+)\u27e7")
    MARK_LOOSE = re.compile(u"[\u27e6\\[\u2039<]\\s*(\\d+)\\s*[\u27e7\\]\u203a>]")
    MARK_SPLIT = re.compile(u"(\u27e6\\d+\u27e7)")
    TAG_RE = re.compile(u"\\{\\{|\\{[^{}\\n]*\\}|\\n")
    NUM_RE = re.compile(u"\\d+(?:[.,:]\\d+)*")
    LATIN = re.compile(u"[A-Za-z]{2}")
    DIGIT = re.compile(u"\\d")
    SOLO = set(u"w p nw fast done image space vspace clear k _start _end".split())
    NOPLURAL = set(u"zh ja ko vi th id ms lo km my jw su ka".split())
    FONT = "DejaVuSans.ttf"
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/124.0 Safari/537.36")
    PA_KEY = "AIzaSyATBXajvzQLTDHEQbcpq0Ihe0vWDHmO520"

    try:
        st.font = FONT if E.loadable(FONT) else None
        st.font_bold = bool(E.loadable("DejaVuSans-Bold.ttf"))
    except Exception:
        st.font, st.font_bold = FONT, False

    def base_lang(l):
        return (l or u"").split(u"-")[0].lower()

    def err_once(where, e):
        if where not in st.err_logged:
            st.err_logged.add(where)
            log(where, repr(e))

    # ------------------------------------------------------------------
    # Files on the player's device (save folder): learned translations and settings
    # ------------------------------------------------------------------

    def user_path():
        d = getattr(C, "savedir", None)
        return os.path.join(d, "rut_live.json") if d else None

    def load_user():
        p = user_path()
        if not p or not os.path.exists(p):
            return
        try:
            with open(p, "rb") as f:
                d = json.loads(u(f.read()))
        except Exception as e:
            err_once("load", e)
            return
        if not isinstance(d, dict) or d.get("src") not in (None, st.src):
            return
        if isinstance(d.get("prefs"), dict):
            st.prefs.update(d["prefs"])
        dev_man = d.get("manual") if isinstance(d.get("manual"), dict) else {}
        for l, ks in dev_man.items():
            if isinstance(ks, list):
                st.user_manual[l] = set(ks)
                st.manual.setdefault(l, set()).update(ks)
        for l, m in (d.get("langs") or {}).items():
            if not isinstance(m, dict):
                continue
            st.user[l] = dict(m)
            M = st.mem.setdefault(l, {})
            emb = st.emb_manual.get(l, ())
            dm = st.user_manual.get(l, ())
            for k, v in m.items():
                if k in emb and k not in dm:
                    continue
                M[k] = v
        for l, m in (d.get("dicts") or {}).items():
            if isinstance(m, dict):
                st.user_dict[l] = dict(m)

    def save_user(sync=False):
        p = user_path()
        if not p or st.saving:
            return False
        snap = {"format": "sugarcube_translate-live", "version": 1, "engine": "renpy", "src": st.src,
                "game": u"%s" % (getattr(C, "name", "") or ""), "prefs": dict(st.prefs),
                "langs": dict((l, dict(m)) for l, m in st.user.items() if m),
                "manual": dict((l, sorted(s)) for l, s in st.user_manual.items() if s),
                "dicts": dict((l, dict(m)) for l, m in st.user_dict.items() if m)}
        st.saving = True

        def run():
            try:
                data = json.dumps(snap, ensure_ascii=False)
                if not isinstance(data, T_BYTES):
                    data = data.encode("utf-8")
                d = os.path.dirname(p)
                if d and not os.path.isdir(d):
                    os.makedirs(d)
                tmp = p + ".tmp"
                with open(tmp, "wb") as f:
                    f.write(data)
                try:
                    os.replace(tmp, p)
                except AttributeError:
                    if os.path.exists(p):
                        os.remove(p)
                    os.rename(tmp, p)
            except Exception as e:
                err_once("save", e)
            finally:
                st.saving = False
        if sync:
            run()
        else:
            t = threading.Thread(target=run)
            t.daemon = True
            t.start()
        return True

    # ------------------------------------------------------------------
    # Text -> phrase for the translator: tags, line breaks and numbers become marks
    # ------------------------------------------------------------------

    def intval(t):
        if re.match(u"^(?:0|[1-9]\\d{0,14}|[1-9]\\d{0,2}(?:,\\d{3})+)$", t):
            return int(t.replace(u",", u""))
        return None

    def mark(s):
        if len(s) > 5000 or not src_words(s):
            return None
        items, out, pairs, stack = [], [], {}, []
        info = {"nums": 0}

        def add(it):
            items.append(it)
            return MO + T_TEXT(len(items) - 1) + MC

        def plain(piece):
            piece = piece.replace(MO, u"").replace(MC, u"")
            res, pos = [], 0
            for m in NUM_RE.finditer(piece):
                a, b = m.span()
                if (a > 0 and piece[a - 1].isalpha()) or (b < len(piece) and piece[b].isalpha()):
                    continue
                v = intval(m.group(0))
                res.append(piece[pos:a])
                res.append(add({"t": m.group(0), "v": v, "k": "num"}))
                if v is not None:
                    info["nums"] += 1
                pos = b
            res.append(piece[pos:])
            return u"".join(res)

        pos = 0
        for m in TAG_RE.finditer(s):
            out.append(plain(s[pos:m.start()]))
            g = m.group(0)
            kind = "nl" if g == u"\n" else ("esc" if g == u"{{" else "tag")
            k = len(items)
            out.append(add({"t": g, "k": kind}))
            if kind == "tag":
                inner = g[1:-1]
                nm = re.match(u"/?([^=\\s}]*)", inner).group(1)
                if inner.startswith(u"/"):
                    items[k]["k"] = "close"
                    for x in range(len(stack) - 1, -1, -1):
                        if stack[x][0] == nm:
                            pairs[stack[x][1]] = k
                            del stack[x:]
                            break
                elif nm and not nm.startswith(u"#") and nm not in SOLO:
                    items[k]["k"] = "open"
                    stack.append((nm, k))
            pos = m.end()
        out.append(plain(s[pos:]))
        txt = u"".join(out)
        core = txt.strip()
        if not core or not src_words(MARK_RE.sub(u" ", core)):
            return None
        a = len(txt) - len(txt.lstrip())
        info.update({"core": core, "items": items, "pairs": pairs, "lead": txt[:a],
                     "trail": txt[a + len(core):], "kc": {}, "src": s})
        info["plain_digits"] = bool(DIGIT.search(MARK_RE.sub(u" ", core)))
        return info

    # numbers: stand-in numbers of the same grammatical category ("1 coin", "2 coins", "5 coins")
    def pcat(lang, n):
        l = base_lang(lang)
        if l in (u"ru", u"uk", u"be"):
            if n % 10 == 1 and n % 100 != 11:
                return "one"
            if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
                return "few"
            return "many"
        if l == u"pl":
            if n == 1:
                return "one"
            if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
                return "few"
            return "many"
        if l in (u"cs", u"sk"):
            return "one" if n == 1 else ("few" if 2 <= n <= 4 else "other")
        if l in (u"hr", u"sr", u"bs"):
            if n % 10 == 1 and n % 100 != 11:
                return "one"
            if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
                return "few"
            return "other"
        if l == u"lt":
            if n % 10 == 1 and not 11 <= n % 100 <= 19:
                return "one"
            if 2 <= n % 10 <= 9 and not 11 <= n % 100 <= 19:
                return "few"
            return "other"
        if l == u"lv":
            if n % 10 == 0 or 11 <= n % 100 <= 19:
                return "zero"
            return "one" if n % 10 == 1 and n % 100 != 11 else "other"
        if l == u"ro":
            if n == 1:
                return "one"
            return "few" if n == 0 or 2 <= n % 100 <= 19 else "other"
        if l == u"sl":
            r = n % 100
            return "one" if r == 1 else ("two" if r == 2 else ("few" if r in (3, 4) else "other"))
        if l == u"ar":
            if n in (0, 1, 2):
                return ("zero", "one", "two")[n]
            r = n % 100
            return "few" if 3 <= r <= 10 else ("many" if 11 <= r <= 99 else "other")
        if l in (u"he", u"iw"):
            return "one" if n == 1 else ("two" if n == 2 else "other")
        if l in NOPLURAL:
            return "other"
        if l == u"fr" or (l == u"pt" and lang.lower() != u"pt-pt"):
            return "one" if n in (0, 1) else "other"
        return "one" if n == 1 else "other"

    PL = {}

    def plural_lists(lang):
        if lang in PL:
            return PL[lang]
        lists = {}
        for n in list(range(21, 1000)) + list(range(2, 21)) + [0, 1]:
            c = pcat(lang, n)
            lst = lists.setdefault(c, [])
            if len(lst) < 40:
                lst.append(n)
        PL[lang] = lists if len(lists) > 1 else None
        return PL[lang]

    def key_for(info, lang):
        kc = info["kc"]
        if lang in kc:
            return kc[lang]
        res = (info["core"], None)
        P = plural_lists(lang) if info["nums"] and not info["plain_digits"] else None
        if P:
            used, mp, ok = {}, {}, [False]

            def rep(m):
                i = int(m.group(1))
                it = info["items"][i]
                if it.get("v") is None:
                    return m.group(0)
                c = pcat(lang, it["v"])
                lst = P.get(c) or []
                k = used.get(c, 0)
                if k >= len(lst):
                    return m.group(0)
                used[c] = k + 1
                mp[T_TEXT(lst[k])] = i
                ok[0] = True
                return T_TEXT(lst[k])
            key = MARK_RE.sub(rep, info["core"])
            if ok[0]:
                res = (key, mp)
        kc[lang] = res
        return res

    def from_stand(res, mp):
        cnt, bad = {}, [False]

        def rep(m):
            g = m.group(0)
            if not g.isdigit():
                return g
            if g not in mp:
                bad[0] = True
                return g
            cnt[g] = cnt.get(g, 0) + 1
            return MO + T_TEXT(mp[g]) + MC
        out = re.sub(u"[\u27e6\\[]\\s*\\d+\\s*[\u27e7\\]]|\\d+", rep, res)
        if bad[0] or any(cnt.get(k) != 1 for k in mp):
            return None
        return out

    def to_stand(text, mp):
        rev = dict((v, k) for k, v in mp.items())
        return MARK_RE.sub(lambda m: rev.get(int(m.group(1)), m.group(0)), text)

    def norm_marks(res, core):
        if u"[" not in core:
            res = re.sub(u"\\[\\s*(\\d+)\\s*\\]", MO + u"\\1" + MC, res)
        return re.sub(u"\u27e6\\s*(\\d+)\\s*\u27e7", MO + u"\\1" + MC, res)

    def fix_spaces(core, res, items):
        for k, it in enumerate(items):
            m = MO + T_TEXT(k) + MC
            if it["k"] in ("open", "tag", "nl") and not re.search(re.escape(m) + u"\\s", core):
                res = re.sub(re.escape(m) + u"[ \\t]+", m, res)
            if it["k"] in ("close", "nl") and not re.search(u"\\s" + re.escape(m), core):
                res = re.sub(u"[ \\t]+" + re.escape(m), m, res)
        return res

    def unmark(res, info, mp):
        if not isinstance(res, T_TEXT):
            res = u(res)
        if mp:
            res = from_stand(res, mp)
            if res is None:
                return None
        res = norm_marks(res, info["core"])
        res = re.sub(u"\\s*\\n\\s*", u" ", res)
        res = fix_spaces(info["core"], res, info["items"])
        items, pairs = info["items"], info["pairs"]
        closes = dict((c, o) for o, c in pairs.items())
        parts = re.split(u"\u27e6(\\d+)\u27e7", res)
        out, seen, stack = [], set(), []
        for i, p in enumerate(parts):
            if i % 2 == 0:
                out.append(p.replace(u"{", u"{{"))
                continue
            k = int(p)
            if k >= len(items) or k in seen:
                return None
            seen.add(k)
            if k in pairs:
                stack.append(k)
            elif k in closes:
                if not stack or stack.pop() != closes[k]:
                    return None
            out.append(items[k]["t"])
        if len(seen) != len(items) or stack:
            return None
        return info["lead"] + u"".join(out).strip() + info["trail"]

    def marks_ok(src, res):
        if not isinstance(res, STR_TS):
            return False
        res = norm_marks(u(res), src)
        return sorted(MARK_RE.findall(src)) == sorted(MARK_RE.findall(res))

    # ------------------------------------------------------------------
    # Which text to translate
    # ------------------------------------------------------------------

    def note_out(r):
        if r in st.out:
            return
        st.out[r] = 1
        st.out_order.append(r)
        if len(st.out_order) > 40000:
            for x in st.out_order[:20000]:
                st.out.pop(x, None)
            del st.out_order[:20000]

    def note_rev(r, s):
        st.rev[r] = s
        st.rev_order.append(r)
        if len(st.rev_order) > 400:
            for x in st.rev_order[:200]:
                st.rev.pop(x, None)
            del st.rev_order[:200]

    def note_say_untr(s):
        # dialogue shown untranslated (translation came too late): Ren'Py checks that the "what" text is
        # exactly the line it passed, so this text may change only when it is safe (see dlg_ok)
        if s in st.say_untr:
            return
        st.say_untr[s] = 1
        st.say_untr_order.append(s)
        if len(st.say_untr_order) > 200:
            for x in st.say_untr_order[:100]:
                st.say_untr.pop(x, None)
            del st.say_untr_order[:100]

    PAUSE_RE = re.compile(u"\\{\\{|\\{([wp])(?:=[^{}]*)?\\}")

    def strip_pauses(s):
        # {w} and {p} split a line into parts shown one after another; such a line can not change its text
        # while it is on screen. If its translation is late, the line is shown whole ({p} becomes a line
        # break), so the translation can replace it as soon as it comes.
        def rep(m):
            g = m.group(1)
            if g is None:
                return m.group(0)
            return u"\n" if g == u"p" else u""
        return PAUSE_RE.sub(rep, s)

    def note_pauses(full, short):
        if short not in st.pause_map:
            st.pause_order.append(short)
        st.pause_map[short] = full
        if len(st.pause_order) > 400:
            for x in st.pause_order[:200]:
                st.pause_map.pop(x, None)
            del st.pause_order[:200]

    def names():
        if st.names is None:
            out = set()
            try:
                AC = R.character.ADVCharacter
                for v in list(R.store.__dict__.values()):
                    if isinstance(v, AC):
                        n = getattr(v, "name", None)
                        if isinstance(n, STR_TS) and u"[" not in n and not getattr(v, "dynamic", False):
                            out.add(u(n))
            except Exception as e:
                err_once("names", e)
            st.names = out
            prefetch_names(st.lang)
        return st.names

    NAME_PFX = u"Name: "

    def prefetch_names(lang):
        if not lang or lang == u"off" or st.names is None or not st.name_tr:
            return
        for n in list(st.names):
            if src_words(n) and u"{" not in n:
                info = mark(NAME_PFX + n)
                if info is not None:
                    lookup(info, lang, True, 2)

    def name_text(s, lang):
        # a name alone is often a word for the translator (Violet - a colour, Brooke - a stream):
        # it is translated as "Name: Violet", and the part after the colon is taken
        if not st.name_tr or not src_words(s) or u"{" in s or len(s) > 40:
            return None
        info = mark(NAME_PFX + s)
        if info is None:
            return None
        req, pr = may_ask(s)
        r = lookup(info, lang, req, 2 if pr is None else pr)[0]
        if not r:
            return None
        m = re.match(u"^[^:\uff1a]{1,30}[:\uff1a]\\s*(.+)$", r.strip())
        if not m:
            return None
        v = m.group(1).strip().strip(u"\"'\u00ab\u00bb\u201c\u201d\u300c\u300d").rstrip(u".\u3002!").strip()
        if not v or len(v) > 3 * len(s) + 10:
            return None
        return v

    SCRIPTS = [(u"cyr", 0x0400, 0x052f), (u"greek", 0x0370, 0x03ff), (u"arm", 0x0530, 0x058f),
               (u"heb", 0x0590, 0x05ff), (u"arab", 0x0600, 0x06ff), (u"deva", 0x0900, 0x097f),
               (u"thai", 0x0e00, 0x0e7f), (u"geo", 0x10a0, 0x10ff), (u"hangul", 0xac00, 0xd7af),
               (u"kana", 0x3040, 0x30ff), (u"han", 0x4e00, 0x9fff)]
    LANG_SCRIPT = {}
    for _s, _ls in ((u"cyr", u"ru uk be bg sr mk kk ky tg mn"), (u"greek", u"el"), (u"arm", u"hy"),
                    (u"heb", u"he iw yi"), (u"arab", u"ar fa ur ps ug sd ckb"), (u"deva", u"hi mr ne sa"),
                    (u"thai", u"th"), (u"geo", u"ka"), (u"hangul", u"ko"), (u"kana", u"ja"), (u"han", u"zh")):
        for _l in _ls.split():
            LANG_SCRIPT[_l] = _s

    def script_of(ch):
        o = ord(ch)
        if o < 0x250:
            return u"lat"
        for name, a, b in SCRIPTS:
            if a <= o <= b:
                return u"han" if name == u"kana" else name
        return u"other"

    def lang_script(l):
        s = LANG_SCRIPT.get(base_lang(l), u"lat")
        return u"han" if s == u"kana" else s

    SRC_SCRIPT = lang_script(st.src)

    def src_words(t):
        # at least one word of the game's own language (English and other Latin languages: 2 letters)
        if SRC_SCRIPT == u"lat":
            return bool(LATIN.search(t))
        return any(ch.isalpha() and script_of(ch) == SRC_SCRIPT for ch in t)

    def has_script(t, script):
        return any(ch.isalpha() and script_of(ch) == script for ch in t)

    def wanted(s, lang):
        if u"{#rut}" in s or u"[what]" in s or u"[who]" in s:
            return False
        if u"Traceback (most recent call last)" in s or u'File "' in s:
            return False
        if s in names():
            return False
        tgt = lang_script(lang)
        if tgt != u"lat" and tgt != SRC_SCRIPT and has_script(s, tgt):
            return False  # already in the target language (or mixed: our translation + a name)
        return True

    def active():
        if st.off or st.lang == u"off":
            return False
        if threading.current_thread() is not MAIN:
            return False
        try:
            if R.game.context().init_phase:
                return False
        except Exception:
            return False
        pl = lang_pref()
        if pl is not None and pl.lower() not in (u"english", u"en", u"eng"):
            return False
        return not error_screen()

    def error_screen():
        t, v = st.err_screen
        now = time.time()
        if now - t < 0.3:
            return v
        v = False
        try:
            for nm in ("_exception", "_parse_errors", "_console", "_developer"):
                if E.get_screen(nm):
                    v = True
                    break
        except Exception:
            pass
        st.err_screen = (now, v)
        return v

    def lang_pref():
        try:
            return R.game.preferences.language
        except Exception:
            return None

    def cur_dict():
        if lang_pref() is not None:
            return None
        return st.dicts.get(st.lang)

    def dict_value(s):
        d = cur_dict()
        if d is None or not isinstance(s, STR_TS):
            return None
        s = u(s)
        v = st.user_dict.get(st.lang, {}).get(s)
        if v is None:
            v = d.get(s)
        return v

    def predicting():
        try:
            return bool(R.display.predict.predicting)
        except Exception:
            return False

    def skipping():
        try:
            return bool(C.skipping)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Looking up a translation
    # ------------------------------------------------------------------

    def pieces(info, lang, M, req):
        out, need = [], []
        for p in MARK_SPLIT.split(info["core"]):
            if not p or MARK_RE.match(p) or not LATIN.search(p):
                out.append(p)
                continue
            a = len(p) - len(p.lstrip())
            core = p.strip()
            b = a + len(core)
            v = M.get(core)
            if isinstance(v, STR_TS) and not MARK_RE.search(v):
                out.append(p[:a] + u(v) + p[b:])
            else:
                need.append(core)
                out.append(p)
        if need:
            if req:
                for k in need:
                    ask(lang, k, None, 1)
            return None
        return unmark(u"".join(out), info, None)

    def lookup(info, lang, req=True, prio=1):
        M = st.mem.get(lang) or {}
        key, mp = key_for(info, lang)
        core = info["core"]
        got_any = False
        for k, m in ((key, mp), (core, None)) if mp else ((core, None),):
            v = M.get(k)
            if v is None:
                continue
            got_any = True
            r = unmark(v, info, m)
            if r is not None:
                return r, k
        if not got_any:
            if req:
                ask(lang, key, info, prio)
            return None, key
        if mp and core not in M:
            if req:
                ask(lang, core, info, prio)
            return None, core
        r = pieces(info, lang, M, req)
        return (r, core) if r is not None else (None, None)

    def ask(lang, key, info, prio):
        if request(lang, key, info, prio):
            register((lang, key))
        elif st.cur_text is not None:
            # not asked now (failed a moment ago): "Refresh" will ask again for this text
            st.touched[id(st.cur_text)] = weakref.ref(st.cur_text)

    def note_src(s, kind=u"ui"):
        # the text widget remembers which phrase it shows: "Fix a phrase" lists what is on the screen
        t = st.cur_text
        if t is not None:
            try:
                t._rut_s = (s, kind)
                st.touched[id(t)] = weakref.ref(t)  # and changes back when the original is chosen
            except Exception:
                pass

    def register(lk):
        t = st.cur_text
        st.reg_count += 1
        if t is None:
            return
        try:
            lst = st.waiting.setdefault(lk, [])
            if len(lst) < 40:
                lst.append(weakref.ref(t))
            st.touched[id(t)] = weakref.ref(t)
        except TypeError:
            pass

    def may_ask(s):
        # while Ren'Py predicts screens (to show them fast later) text is translated too: the prepared
        # widgets are reused as they are. Only raw text with [variables] is skipped there.
        if predicting():
            return u"[" not in s, 0
        return True, None

    def live_text(s, wait=False, kind=None, apply=True):
        if not isinstance(s, STR_TS) or not s:
            return None
        s = u(s)
        if s in st.out:
            return None
        full = st.pause_map.get(s)
        if full is not None:
            # dialogue that was shown without its {w}/{p} pauses (translation came late)
            r = live_text(full, False, kind, apply)
            if not r:
                return None
            r = strip_pauses(r)
            note_out(r)
            return r
        lang = st.lang
        memo = st.memo.get(lang)
        if memo is None:
            memo = st.memo[lang] = {}
        r = memo.get(s)
        if not apply:
            if r is None and wanted(s, lang):
                info = mark(s)
                if info is not None:
                    req, pr = may_ask(s)
                    r = lookup(info, lang, req, 2 if pr is None else pr)[0]
            if st.cur_text is not None and wanted(s, lang):
                note_src(s, u"say")
            if r and st.cur_text is not None:
                st.later.append(weakref.ref(st.cur_text))
            return None
        if r is not None:
            if st.cur_text is not None and r:
                st.touched[id(st.cur_text)] = weakref.ref(st.cur_text)
                note_src(s)
            if kind and r:
                remember(kind, lang, s, None, None)
            return r or None
        if s in names():
            r = name_text(s, lang)
            if st.cur_text is not None:
                st.touched[id(st.cur_text)] = weakref.ref(st.cur_text)
            if r:
                note_out(r)
                memo[s] = r
            return r or None
        if not wanted(s, lang):
            memo[s] = u""
            return None
        info = mark(s)
        if info is None:
            memo[s] = u""
            return None
        req, pr = may_ask(s)
        pred = pr is not None
        r, key = lookup(info, lang, req, pr if pred else (3 if wait else 1))
        if r is None and wait and not pred and st.wait > 0 and not st.web and time.time() >= st.down_until:
            wait_for([(lang, key)] if key else [], st.wait)
            r, key = lookup(info, lang, True, 3)
            if r is None and key and (lang, key) in st.inflight:
                st.down_until = time.time() + 20  # translator is slow: do not freeze every line, show text as is
        if kind:
            remember(kind, lang, s, info, key)
        note_src(s)
        if r is None:
            return None
        note_out(r)
        if len(memo) > 30000:
            memo.clear()
        memo[s] = r
        if st.cur_text is not None:
            st.touched[id(st.cur_text)] = weakref.ref(st.cur_text)
        return r

    def remember(kind, lang, s, info, key):
        for x in st.recent:
            if x.get("src") == s and x.get("lang") == lang:
                st.recent.remove(x)
                break
        st.recent.append({"kind": kind, "lang": lang, "src": s, "info": info})
        del st.recent[:-12]

    def wait_for(lks, timeout):
        end = time.time() + timeout
        for lk in lks:
            ev = st.events.get(lk)
            if ev is None:
                continue
            rem = end - time.time()
            if rem <= 0:
                break
            ev.wait(rem)

    # ------------------------------------------------------------------
    # Requests to the translator (background threads)
    # ------------------------------------------------------------------

    def request(lang, key, info=None, prio=1, force=False):
        if st.web or not key:
            return False
        lk = (lang, key)
        with st.lock:
            if not force:
                f = st.fail.get(lk)
                if f and time.time() - f < 60:
                    return False
                if lk in st.inflight:
                    return True
            cur = st.q.get(lk)
            if cur is not None:
                cur[0] = max(cur[0], prio)
                cur[2] = cur[2] or force
                return True
            st.seq += 1
            hint = None
            if info and info.get("pairs") and key in (info["core"], key_for(info, lang)[0]):
                hint = {"p": dict((T_TEXT(a), b) for a, b in info["pairs"].items())}
            st.q[lk] = [prio, st.seq, force, hint]
            if lk not in st.events:
                st.events[lk] = threading.Event()
            st.cond.notify()
        start_workers()
        return True

    def start_workers():
        if st.workers:
            return
        st.workers = True
        for _i in range(2):
            t = threading.Thread(target=worker)
            t.daemon = True
            t.start()
        if not st.server:
            start_probe()

    def take():
        items = sorted(st.q.items(), key=lambda kv: (-kv[1][0], kv[1][1]))
        if not items:
            return None
        (lang, _k), first = items[0]
        force = first[2]
        server = bool(st.server) and time.time() >= st.server_down_until
        maxn, maxc = (200, 30000) if server else (40, 4000)
        if force:
            maxn = 1
        keys, hints, size = [], [], 0
        for (l, k), v in items:
            if l != lang or v[2] != force:
                continue
            if keys and (len(keys) >= maxn or size + len(k) > maxc):
                break
            keys.append(k)
            hints.append(v[3])
            size += len(k) + 1
            del st.q[(l, k)]
            st.inflight.add((l, k))
        return lang, keys, hints, force

    def worker():
        while True:
            try:
                with st.cond:
                    while not st.q:
                        st.cond.wait(10)
                    batch = take()
                if not batch:
                    continue
                lang, keys, hints, force = batch
                try:
                    res = translate(lang, keys, hints, force)
                except Exception as e:
                    err_once("translate", e)
                    res = [None] * len(keys)
                store(lang, keys, res, force)
            except Exception as e:
                err_once("worker", e)
                time.sleep(1)

    def store(lang, keys, res, force):
        now = time.time()
        ok = False
        M = st.mem.setdefault(lang, {})
        U = st.user.setdefault(lang, {})
        man = st.manual.get(lang, ())
        for k, r in zip(keys, res):
            lk = (lang, k)
            if isinstance(r, STR_TS) and u(r).strip():
                r = u(r)
                if force or k not in man:
                    M[k] = r
                    U[k] = r
                st.fail.pop(lk, None)
                ok = True
            else:
                st.fail[lk] = now
            with st.lock:
                st.inflight.discard(lk)
                ev = st.events.pop(lk, None)
                st.arrived.append(lk)
            if ev is not None:
                ev.set()
        if ok:
            st.fails_row = 0
            st.down_until = 0.0
            st.save_due = True
        else:
            st.fails_row += 1
            if st.fails_row >= 2:
                st.down_until = now + 60
        if force:
            st.memo.pop(lang, None)
            st.refresh_all = True
        try:
            E.restart_interaction()
        except Exception:
            pass

    def translate(lang, keys, hints, force):
        if st.server and time.time() >= st.server_down_until:
            try:
                return via_server(lang, keys, hints, force)
            except Exception as e:
                st.server_down_until = time.time() + 30
                err_once("server", e)
                start_probe()
        return via_google(lang, keys, hints)

    # --- HTTP ---
    def ssl_ctx():
        if st.ssl_ctx is not None:
            return st.ssl_ctx
        import ssl
        ctx = None
        if st.ssl_mode == 0:
            ctx = ssl.create_default_context()
        elif st.ssl_mode == 1:
            try:
                import certifi
                ctx = ssl.create_default_context(cafile=certifi.where())
            except Exception:
                st.ssl_mode = 2
        if st.ssl_mode >= 2:
            ctx = ssl._create_unverified_context()
        st.ssl_ctx = ctx
        return ctx

    if PY2:
        import urllib2 as UR
        import urllib as UQ
        quote = UQ.quote
    else:
        import urllib.request as UR
        import urllib.parse as UQ
        quote = UQ.quote

    class HttpError(Exception):
        def __init__(self, code, msg=""):
            Exception.__init__(self, "HTTP %s %s" % (code, msg))
            self.code = code

    def http(url, data=None, headers=None, timeout=20):
        h = {"User-Agent": UA}
        h.update(headers or {})
        for attempt in range(3):
            req = UR.Request(url, data=data, headers=h)
            try:
                if url.startswith("https"):
                    r = UR.urlopen(req, timeout=timeout, context=ssl_ctx())
                else:
                    r = UR.urlopen(req, timeout=timeout)
                try:
                    return r.read()
                finally:
                    r.close()
            except Exception as e:
                code = getattr(e, "code", None)
                if code is not None:
                    raise HttpError(code)
                s = repr(e)
                if url.startswith("https") and st.ssl_mode < 2 and (
                        "CERTIFICATE_VERIFY_FAILED" in s or "certificate verify failed" in s):
                    st.ssl_mode += 1
                    st.ssl_ctx = None
                    log("TLS certificates: switching mode", st.ssl_mode)
                    continue
                raise
        raise IOError("TLS")

    SAFE = str("")  # Python 2: urllib.quote(bytes, safe=u"") fails on non-ASCII text

    def q(t):
        r = quote(u(t).encode("utf-8"), safe=SAFE)
        return r.decode("ascii") if isinstance(r, T_BYTES) else r

    def esc_html(t):
        return t.replace(u"&", u"&amp;").replace(u"<", u"&lt;").replace(u">", u"&gt;")

    CHR = eval("unichr") if PY2 else chr
    ENT = {u"amp": u"&", u"lt": u"<", u"gt": u">", u"quot": u'"', u"apos": u"'", u"nbsp": u"\u00a0"}

    def unesc_html(t):
        def rep(m):
            g = m.group(1)
            try:
                if g.startswith(u"#x") or g.startswith(u"#X"):
                    return CHR(int(g[2:], 16))
                if g.startswith(u"#"):
                    return CHR(int(g[1:]))
            except Exception:
                return m.group(0)
            return ENT.get(g, m.group(0))
        return re.sub(u"&(#[xX][0-9a-fA-F]+|#\\d+|[A-Za-z]+);", rep, t)

    def via_server(lang, keys, hints, force):
        body = json.dumps({"t": keys, "lang": lang, "force": False, "redo": bool(force), "h": hints})
        if not isinstance(body, T_BYTES):
            body = body.encode("utf-8")
        d = json.loads(u(http(st.server, body, {"Content-Type": "application/json"}, timeout=300)))
        if d.get("eps") is not None:
            st.server_eps, st.server_why = d.get("eps"), d.get("why")
        if d.get("err") == "lang":
            st.bad_lang = lang
        t = d.get("t")
        if not isinstance(t, list) or len(t) != len(keys):
            raise ValueError("bad answer")
        return t

    # --- Google directly from the game ---
    DEFAULT_EPS = [
        ["pa", "translate-pa.googleapis.com"],
        ["gtx", "translate.googleapis.com"], ["gtx", "translate.google.com"], ["gtx", "clients5.google.com"],
        ["gtx", "translate.google.com.ua"], ["gtx", "translate.google.de"],
        ["gtxt", "translate.googleapis.com"], ["gtxt", "clients5.google.com"], ["gtxt", "translate.google.com"],
        ["dict", "clients5.google.com"], ["dict", "translate.googleapis.com"], ["dict", "translate.google.com"],
        ["dict", "clients1.google.com"], ["dict", "clients2.google.com"], ["dict", "clients4.google.com"],
        ["dict", "clients6.google.com"],
        ["gtxget", "translate.googleapis.com"], ["gtxget", "translate.google.com"],
        ["gtxget", "clients5.google.com"],
    ]

    def make_eps():
        out = []
        for kind, host in (CFG.get("eps") or DEFAULT_EPS):
            base = host if u"://" in host else u"https://" + host
            out.append({"kind": kind, "base": base, "host": host, "until": 0.0, "ok": None, "ever": False,
                        "why": None, "max": 4500 if kind in ("gtx", "pa") else 1500,
                        "n": 100 if kind == "pa" else (60 if kind == "gtx" else 25)})
        return out

    st.eps = make_eps()

    class Split(Exception):
        pass

    def call_ep(ep, lines, lang, html=False):
        sl, tl, base = q(st.src), q(lang), ep["base"]
        joined = u"\n".join(lines)

        def split_lines(out):
            parts = out.split(u"\n")
            if len(parts) == len(lines):
                return parts
            if len(lines) == 1:
                return [out.replace(u"\n", u" ")]
            raise Split()
        if ep["kind"] == "pa":
            body = json.dumps([[[x if html else esc_html(x) for x in lines], st.src, lang], "wt_lib"])
            if not isinstance(body, T_BYTES):
                body = body.encode("utf-8")
            d = json.loads(u(http(base + "/v1/translateHtml", body,
                                  {"Content-Type": "application/json+protobuf", "X-Goog-API-Key": PA_KEY})))
            res = d[0]
            if not isinstance(res, list) or len(res) != len(lines):
                raise ValueError("bad answer")
            if html:
                return [u(x or u"") for x in res]
            return [unesc_html(re.sub(u"\\s*<br\\s*/?>\\s*", u" ", u(x or u""))).replace(u"\n", u" ")
                    for x in res]
        if ep["kind"] == "gtx":
            d = json.loads(u(http(base + "/translate_a/single?client=gtx&dt=t&sl=%s&tl=%s" % (sl, tl),
                                  ("q=" + q(joined)).encode("ascii"),
                                  {"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"})))
            return split_lines(u"".join(seg[0] for seg in (d[0] or []) if seg and isinstance(seg[0], STR_TS)))
        if ep["kind"] == "gtxget":
            d = json.loads(u(http(base + "/translate_a/single?client=gtx&dt=t&sl=%s&tl=%s&q=%s" % (sl, tl, q(joined)))))
            return split_lines(u"".join(seg[0] for seg in (d[0] or []) if seg and isinstance(seg[0], STR_TS)))
        client = "dict-chrome-ex" if ep["kind"] == "dict" else "gtx"
        d = json.loads(u(http(base + "/translate_a/t?client=%s&sl=%s&tl=%s&q=%s" % (client, sl, tl, q(joined)))))
        if isinstance(d, dict):
            out = u"".join(x.get("trans", u"") for x in d.get("sentences", []))
        else:
            first = d[0]
            out = first[0] if isinstance(first, list) else first
        return split_lines(u(out))

    def run_ep(ep, lines, lang, html=False):
        chunks, cur, size = [], [], 0
        for l in lines:
            if cur and (size + len(l) + 1 > ep["max"] or len(cur) >= ep["n"]):
                chunks.append(cur)
                cur, size = [], 0
            cur.append(l)
            size += len(l) + 1
        if cur:
            chunks.append(cur)
        out = []
        for ch in chunks:
            out.extend(run_chunk(ep, ch, lang, html))
        return out

    def run_chunk(ep, lines, lang, html=False):
        try:
            return call_ep(ep, lines, lang, html)
        except Split:
            mid = len(lines) // 2
            return run_chunk(ep, lines[:mid], lang, html) + run_chunk(ep, lines[mid:], lang, html)

    def why_of(e):
        code = getattr(e, "code", None)
        if code in (429, 403):
            return T_TEXT(code)
        if isinstance(code, int):
            return "5xx" if code >= 500 else "other"
        s = repr(e).lower()
        if "timed out" in s or "timeout" in s:
            return "timeout"
        if isinstance(e, (ValueError, KeyError, IndexError, TypeError)):
            return "bad"
        return "net"

    def ep_fail(ep, e):
        err_once("google " + ep["kind"] + " " + ep["host"], e)
        ep["ok"] = False
        ep["why"] = why_of(e)
        ep["until"] = time.time() + (60 if ep["ever"] else 600)

    def ep_good(ep):
        ep["ok"] = ep["ever"] = True
        ep["until"] = 0.0
        ep["why"] = None

    def pick(tried, kind=None):
        now = time.time()
        n = len(st.eps)
        best, score = None, 1e9
        for i in range(n):
            ep = st.eps[(st.rr + i) % n]
            if id(ep) in tried or ep["until"] > now or (kind and ep["kind"] != kind):
                continue
            sc = 0 if ep["ok"] else (100 if ep["ok"] is None else 200)
            if sc < score:
                best, score = ep, sc
        if best is not None:
            st.rr = (st.eps.index(best) + 1) % n
        return best

    class BadLang(Exception):
        pass

    def google_lines(lines, lang):
        tried, n400, nerr = set(), 0, 0
        while True:
            ep = pick(tried)
            if ep is None:
                if n400 and n400 == nerr:
                    raise BadLang(lang)
                raise IOError("no Google address answers")
            try:
                out = run_ep(ep, lines, lang)
                ep_good(ep)
                return out
            except Exception as e:
                tried.add(id(ep))
                nerr += 1
                if getattr(e, "code", None) == 400:
                    n400 += 1
                else:
                    ep_fail(ep, e)

    def to_html(key, pairs):
        closes = set(T_TEXT(v) for v in pairs.values())

        def rep(m):
            d = m.group(1)
            if d in pairs:
                return u"<a i=%s>" % d
            if d in closes:
                return u"</a>"
            return m.group(0)
        return MARK_RE.sub(rep, esc_html(key))

    def from_html(html, key, pairs):
        if not isinstance(html, STR_TS):
            return None
        stack, bad = [], [False]

        def rep(m):
            d = m.group(1)
            if d is not None:
                if d not in pairs:
                    bad[0] = True
                    return u""
                stack.append(d)
                return MO + d + MC
            if not stack:
                bad[0] = True
                return u""
            return MO + T_TEXT(pairs[stack.pop()]) + MC
        out = re.sub(u"<a\\s+i\\s*=\\s*[\"']?(\\d+)[\"']?\\s*>|</a\\s*>", rep, u(html), flags=re.I)
        if bad[0] or stack:
            return None
        out = unesc_html(re.sub(u"<[^>]*>", u"", out))
        return out if marks_ok(key, out) else None

    def via_google(lang, keys, hints):
        res = [None] * len(keys)
        hidx = [i for i, h in enumerate(hints) if h and h.get("p")]
        if hidx:
            ep = pick(set(), "pa")
            if ep is not None:
                try:
                    out = run_ep(ep, [to_html(keys[i], hints[i]["p"]) for i in hidx], lang, True)
                    ep_good(ep)
                    for i, x in zip(hidx, out):
                        res[i] = from_html(x, keys[i], hints[i]["p"])
                except Exception as e:
                    if getattr(e, "code", None) != 400:
                        ep_fail(ep, e)
        rest = [i for i in range(len(keys)) if res[i] is None]
        if rest:
            try:
                out = google_lines([keys[i] for i in rest], lang)
            except BadLang:
                st.bad_lang = lang
                out = [None] * len(rest)
            for i, x in zip(rest, out):
                res[i] = x
        again = [i for i, k in enumerate(keys) if res[i] is not None and MARK_RE.search(k)
                 and not marks_ok(k, res[i])][:8]
        for i in again:
            try:
                x = google_lines([keys[i]], lang)[0]
                if marks_ok(keys[i], x):
                    res[i] = x
            except Exception:
                pass
        return res

    def start_probe():
        if st.probing or st.web:
            return
        st.probing = True
        tl = u"en" if base_lang(st.src) == u"ru" else u"ru"

        def test(ep):
            try:
                r = call_ep(ep, [u"Hello"], tl)
                if r and r[0].strip() and r[0].strip() != u"Hello":
                    ep_good(ep)
                else:
                    raise ValueError("empty")
            except Exception as e:
                if getattr(e, "code", None) != 400:
                    ep_fail(ep, e)

        def run():
            ts = []
            for ep in st.eps:
                t = threading.Thread(target=test, args=(ep,))
                t.daemon = True
                t.start()
                ts.append(t)
            for t in ts:
                t.join(30)
            st.probing = False
            st.probed = True
            try:
                E.restart_interaction()
            except Exception:
                pass
        t = threading.Thread(target=run)
        t.daemon = True
        t.start()

    # ------------------------------------------------------------------
    # Hooks: text is translated when Ren'Py prepares it for the screen
    # ------------------------------------------------------------------

    SUB = R.substitutions
    orig_sub = getattr(SUB.substitute, "_rut_orig", None) or SUB.substitute

    def substitute(s, scope=None, force=False, translate=True):
        # only text that is being shown (Text objects, dialogue): strings that the game builds with
        # renpy.substitute() for its own logic stay as they are
        if not translate or (st.cur_text is None and st.char_depth == 0) or not active():
            return orig_sub(s, scope, force, translate)
        is_say = st.cur_what is not None and isinstance(s, STR_TS) and s == st.cur_what
        if is_say:
            st.cur_what = None
        try:
            v = dict_value(s)
        except Exception:
            v = None
        if v is not None:
            rv = orig_sub(v, scope, force, translate)
            note_out(rv[0])
            note_src(u(s), u"dict")
            if is_say:
                remember("dict", st.lang, u(s), None, None)
            return rv
        rv = orig_sub(s, scope, force, translate)
        try:
            r = live_text(rv[0], wait=is_say and not skipping(), kind="say" if is_say else None)
            if is_say:
                ahead()
            if r is not None:
                if is_say:
                    note_rev(r, rv[0])
                return (r, rv[1])
            if is_say:
                full = u(rv[0])
                short = strip_pauses(full) if st.pause_fix else full
                if short != full and short.strip() and wanted(full, st.lang) and mark(full) is not None:
                    note_pauses(full, short)
                    note_say_untr(short)
                    return (short, rv[1])
                note_say_untr(full)
        except Exception as e:
            err_once("substitute", e)
        return rv
    substitute._rut_orig = orig_sub
    SUB.substitute = substitute

    TX = R.text.text.Text
    INP = getattr(R.display.behavior, "Input", None)
    orig_set = TX.__dict__.get("set_text")
    orig_set = getattr(orig_set, "_rut_orig", None) or orig_set

    def set_text(self, text, scope=None, substitute=False, update=True):
        if (INP is not None and isinstance(self, INP)) or getattr(self, "tokenized", False) or not active():
            if substitute is False and getattr(self, "_rut_src", None) is not None and not st.off:
                self._rut_src = None
            return orig_set(self, text, scope, substitute, update)
        prev = st.cur_text
        st.cur_text = self
        try:
            if substitute is False:
                lst = text if isinstance(text, list) else [text]
                new, changed, held, reg0 = [], False, False, st.reg_count
                for i in lst:
                    if isinstance(i, STR_TS) and i in st.rev:
                        st.touched[id(self)] = weakref.ref(self)
                        note_src(st.rev[i], u"say")
                    if isinstance(i, STR_TS):
                        r = None
                        try:
                            r = dict_value(i)
                            if r is not None:
                                note_out(r)
                                note_src(u(i), u"dict")
                            elif i in st.say_untr and not st.refreshing:
                                live_text(i, apply=False)
                                held = True
                            else:
                                r = live_text(i)
                        except Exception as e:
                            err_once("set_text", e)
                        if r is not None:
                            i = r
                            changed = True
                    new.append(i)
                try:
                    self._rut_src = list(lst) if (changed or held or st.reg_count != reg0) else None
                except Exception:
                    pass
                if changed:
                    text = new
            return orig_set(self, text, scope, substitute, update)
        finally:
            st.cur_text = prev
    set_text._rut_orig = orig_set
    TX.set_text = set_text

    AC = R.character.ADVCharacter
    orig_call = AC.__dict__.get("__call__")
    orig_call = getattr(orig_call, "_rut_orig", None) or orig_call

    def char_call(self, *args, **kwargs):
        what = args[0] if args else kwargs.get("what")
        prev = st.cur_what
        st.cur_what = what if (isinstance(what, STR_TS) and what) else None
        try:
            n = getattr(self, "name", None)  # characters made during the game ($ a = Character("Ashley"))
            if isinstance(n, STR_TS) and u"[" not in n and not getattr(self, "dynamic", False):
                n = u(n)
                if n not in names():
                    st.names.add(n)
                    prefetch_names(st.lang)
        except Exception as e:
            err_once("char name", e)
        st.char_depth += 1
        try:
            return orig_call(self, *args, **kwargs)
        finally:
            st.char_depth -= 1
            st.cur_what = prev
    char_call._rut_orig = orig_call
    AC.__call__ = char_call

    orig_menu = getattr(E.menu, "_rut_orig", None) or E.menu

    def menu(items, *args, **kwargs):
        try:
            if active() and not skipping() and not st.web:
                want, lang = [], st.lang
                for it in items:
                    lab = final_of(it[0], True)
                    if lab is None:
                        continue
                    info = mark(lab)
                    if info is None or not wanted(lab, lang):
                        continue
                    r, key = lookup(info, lang, True, 3)
                    if r is None and key:
                        want.append((lang, key))
                if want and time.time() >= st.down_until and st.wait > 0:
                    wait_for(want, st.wait)
        except Exception as e:
            err_once("menu", e)
        return orig_menu(items, *args, **kwargs)
    menu._rut_orig = orig_menu
    E.menu = menu

    def final_of(s, is_menu=False):
        if not isinstance(s, STR_TS):
            return None
        f = getattr(C, "say_menu_text_filter", None)
        if f is not None:
            s = f(s)
        if is_menu and getattr(C, "old_substitutions", False):
            tq = getattr(E, "tag_quoting_dict", None)
            if tq is not None:
                try:
                    s = s % tq
                except Exception:
                    pass
        if dict_value(s) is not None:
            return None
        return u(orig_sub(s, None, False, True)[0])

    # Look ahead: the next lines of the script are translated while the player reads this one
    def ahead():
        try:
            ctx = R.game.context()
            name = getattr(ctx, "current", None)
            if name is None or name == st.ahead_from:
                return
            st.ahead_from = name
            sc = R.game.script
            nm = getattr(sc, "namemap", None) or {}
            node = nm.get(name)
            if node is None:
                return
            todo, seen, nodes, lines, lang = [getattr(node, "next", None)], set(), 0, 0, st.lang
            while todo and nodes < 150 and lines < 30:
                n = todo.pop(0)
                if n is None or id(n) in seen:
                    continue
                seen.add(id(n))
                nodes += 1
                cn = type(n).__name__
                if cn in ("Say", "TranslateSay"):
                    if getattr(n, "language", None) is None and getattr(n, "who", None) != "extend":
                        prefetch(getattr(n, "what", None), lang)
                        lines += 1
                elif cn == "Menu":
                    for it in getattr(n, "items", None) or ():
                        try:
                            prefetch(it[0], lang, True)
                            if it[2]:
                                todo.append(it[2][0])
                        except Exception:
                            pass
                    continue
                elif cn == "If":
                    for ent in getattr(n, "entries", None) or ():
                        try:
                            if ent[1]:
                                todo.append(ent[1][0])
                        except Exception:
                            pass
                    continue
                elif cn == "Translate":
                    if getattr(n, "language", None) is None and getattr(n, "block", None):
                        todo.append(n.block[0])
                        continue
                elif cn == "Jump":
                    if not getattr(n, "expression", False):
                        todo.append(nm.get(getattr(n, "target", None)))
                    continue
                elif cn == "Return":
                    continue
                elif cn == "Call":
                    if not getattr(n, "expression", False):
                        todo.append(nm.get(getattr(n, "label", None)))
                todo.append(getattr(n, "next", None))
        except Exception as e:
            err_once("ahead", e)

    def prefetch(s, lang, is_menu=False):
        try:
            f = final_of(s, is_menu)
        except Exception:
            return
        if not f or f in st.out or not wanted(f, lang):
            return
        info = mark(f)
        if info is not None:
            lookup(info, lang, True, 0)

    # ------------------------------------------------------------------
    # Fonts: many games ship fonts without Cyrillic - then the translated text would be invisible.
    # Such a font is replaced with Ren'Py's own DejaVuSans (only if it really lacks the letters).
    # ------------------------------------------------------------------

    SCRIPT_TEST = {}
    for _l in (u"ru", u"be", u"bg", u"sr", u"mk", u"kk", u"ky", u"tg", u"mn"):
        SCRIPT_TEST[_l] = u"\u0416\u0436\u042b\u044b\u042d\u044d"
    SCRIPT_TEST[u"uk"] = u"\u0416\u0436\u0406\u0456\u0407\u0457\u0404\u0454"
    SCRIPT_TEST[u"el"] = u"\u03a9\u03c9\u03bb"
    st.font_ok = {}

    def cmap_has(data, chars):
        import struct
        off = struct.unpack(">I", data[12:16])[0] if data[:4] == b"ttcf" else 0
        ntab = struct.unpack(">H", data[off + 4:off + 6])[0]
        cmap = None
        for i in range(ntab):
            rec = off + 12 + 16 * i
            if data[rec:rec + 4] == b"cmap":
                cmap = struct.unpack(">I", data[rec + 8:rec + 12])[0]
                break
        if cmap is None:
            return True
        found = False
        for i in range(struct.unpack(">H", data[cmap + 2:cmap + 4])[0]):
            pid, eid, so = struct.unpack(">HHI", data[cmap + 4 + 8 * i:cmap + 12 + 8 * i])
            if not (pid == 0 or (pid == 3 and eid in (1, 10))):
                continue
            so += cmap
            fmt = struct.unpack(">H", data[so:so + 2])[0]
            if fmt == 4:
                n = struct.unpack(">H", data[so + 6:so + 8])[0] // 2
                ends = struct.unpack(">%dH" % n, data[so + 14:so + 14 + 2 * n])
                starts = struct.unpack(">%dH" % n, data[so + 16 + 2 * n:so + 16 + 4 * n])
                deltas = struct.unpack(">%dh" % n, data[so + 16 + 4 * n:so + 16 + 6 * n])
                ro_pos = so + 16 + 6 * n
                ros = struct.unpack(">%dH" % n, data[ro_pos:ro_pos + 2 * n])

                def glyph4(c):
                    for k in range(n):
                        if starts[k] <= c <= ends[k]:
                            if ros[k] == 0:
                                return (c + deltas[k]) & 0xFFFF
                            gp = ro_pos + 2 * k + ros[k] + 2 * (c - starts[k])
                            g = struct.unpack(">H", data[gp:gp + 2])[0]
                            return (g + deltas[k]) & 0xFFFF if g else 0
                    return 0
                found = True
                if all(glyph4(ord(c)) for c in chars):
                    return True
            elif fmt == 12:
                ng = struct.unpack(">I", data[so + 12:so + 16])[0]
                groups = [struct.unpack(">III", data[so + 16 + 12 * k:so + 28 + 12 * k]) for k in range(ng)]
                found = True
                if all(any(a <= ord(c) <= b for a, b, _g in groups) for c in chars):
                    return True
        return not found

    def font_ok(fn):
        chars = SCRIPT_TEST.get(base_lang(st.lang))
        if not chars or not isinstance(fn, STR_TS):
            return True
        key = (fn, chars)
        if key not in st.font_ok:
            ok = True
            name = re.sub(u"^\\d+@", u"", u(fn))
            if name.lower().endswith((u".ttf", u".otf", u".ttc", u".otc")):
                try:
                    f = R.loader.load(name)
                    try:
                        data = f.read()
                    finally:
                        f.close()
                    ok = cmap_has(data, chars)
                except Exception as e:
                    err_once("font " + name, e)
            st.font_ok[key] = ok
            if not ok:
                log("font without the needed letters, using DejaVuSans instead:", name)
        return st.font_ok[key]

    FONT_MOD = getattr(R.text, "font", None)
    orig_font = getattr(getattr(FONT_MOD, "get_font", None), "_rut_orig", None) or getattr(FONT_MOD, "get_font", None)

    def get_font(fn, size, bold, italics, *args, **kwargs):
        try:
            if st.font and not st.off and st.lang != u"off" and not font_ok(fn):
                frm = getattr(C, "font_replacement_map", None)
                if isinstance(frm, dict):
                    for b in (False, True):
                        for it in (False, True):
                            cur = frm.get((fn, b, it))
                            if cur is None or (cur[0] != fn and cur[0] not in (FONT, "DejaVuSans-Bold.ttf")
                                               and not font_ok(cur[0])):
                                frm[(fn, b, it)] = ("DejaVuSans-Bold.ttf" if b and st.font_bold else FONT,
                                                    b and not st.font_bold, it)
        except Exception as e:
            err_once("get_font", e)
        return orig_font(fn, size, bold, italics, *args, **kwargs)
    if orig_font is not None and CFG.get("font_fix", True):
        get_font._rut_orig = orig_font
        FONT_MOD.get_font = get_font

    # ------------------------------------------------------------------
    # Main thread: new translations -> text on screen
    # ------------------------------------------------------------------

    def dlg_ok(t, cur):
        end = getattr(t, "end", None)
        if end is None:
            return True
        if not isinstance(cur, STR_TS) or (getattr(t, "start", None) or 0) != 0 or end != len(cur):
            return False
        if u"{w" in cur or u"{p" in cur or u"{nw" in cur:
            return False
        t.end = None
        return True

    def refresh_text(t):
        try:
            src = getattr(t, "_rut_src", None)
            cur = t.text[0] if getattr(t, "text", None) else None
            if src is None and isinstance(cur, STR_TS) and cur in st.rev and getattr(t, "substitute", None) is False:
                src = [st.rev[cur]]
            if src is not None:
                if not dlg_ok(t, cur):
                    return
                st.refreshing = True
                try:
                    t.set_text(list(src), None, False, True)
                finally:
                    st.refreshing = False
            elif not getattr(t, "_uses_scope", True):
                t.set_text(t.text_parameter, None, getattr(t, "substitute", None), True)
        except Exception as e:
            err_once("refresh", e)

    def visible_texts():
        out = []
        TX = R.text.text.Text

        def cb(d):
            if isinstance(d, TX):
                out.append(d)
        try:
            sl = R.game.context().scene_lists
            for layer in list(sl.layers.keys()):
                for sle in sl.layers.get(layer, ()):
                    try:
                        sle.displayable.visit_all(cb)
                    except Exception:
                        pass
        except Exception as e:
            err_once("visible", e)
        return out

    def refresh_everything():
        # the text on the screen - at once; the rest (prepared screens, earlier lines) - bit by bit in
        # the background, a few milliseconds at a time: a game with a big script must not freeze
        done = set()
        for t in visible_texts():
            if id(t) in st.touched and id(t) not in done:
                done.add(id(t))
                refresh_text(t)
        rest = []
        for k, ref in list(st.touched.items()):
            if k in done:
                continue
            if ref() is None:
                st.touched.pop(k, None)
                continue
            rest.append(ref)
        st.rq = rest
        try:
            E.restart_interaction()
        except Exception:
            pass

    def refresh_some(budget):
        end = time.time() + budget
        while st.rq and time.time() < end:
            t = st.rq.pop()()
            if t is not None:
                refresh_text(t)
        if not st.rq:
            try:
                E.restart_interaction()
            except Exception:
                pass

    def periodic():
        try:
            if st.arrived:
                with st.lock:
                    lst, st.arrived = st.arrived, []
                seen = set()
                for lk in lst:
                    for ref in st.waiting.pop(lk, ()):
                        t = ref()
                        if t is not None and id(t) not in seen:
                            seen.add(id(t))
                            refresh_text(t)
            if st.later:
                lst, st.later = st.later, []
                for ref in lst:
                    t = ref()
                    if t is not None:
                        refresh_text(t)
            if st.refresh_all:
                st.refresh_all = False
                refresh_everything()
            elif st.rq:
                refresh_some(0.006)
            if len(st.touched) > 3000:
                for k, ref in list(st.touched.items()):
                    if ref() is None:
                        st.touched.pop(k, None)
                if len(st.touched) > 3000:
                    st.touched.clear()
            now = time.time()
            if ((st.save_due and now - st.last_save > 15) or st.save_now) and not st.saving:
                st.save_due = st.save_now = False
                st.last_save = now
                save_user()
            if st.toast and now >= st.toast_until:  # the message in the corner goes away by itself
                st.toast = u""
                try:
                    E.restart_interaction()
                except Exception:
                    pass
        except Exception as e:
            err_once("periodic", e)

    # ------------------------------------------------------------------
    # The button in the corner and the panel (Alt+L)
    # Both live on the "overlay" layer above every screen of the game and are shown again in every
    # interaction: in the game, in the main menu and the game menu, in the console. Nothing of them gets
    # into save files.
    # ------------------------------------------------------------------

    ui = R.ui
    Solid = getattr(R.store, "Solid", None)
    try:
        TOUCH = bool(getattr(R, "android", False) or getattr(R, "ios", False) or E.variant("touch")
                     or E.variant("small"))
    except Exception:
        TOUCH = False
    UIS = 1.45 if TOUCH else 1.0  # phones: bigger buttons for fingers
    PC = not TOUCH and not st.web
    st.sup = False  # Ren'Py hides the game's overlays now (main menu, game menu)
    st.panel_open = False
    st.on_top = False

    def fkw(**kw):
        # our panel uses Ren'Py's own DejaVuSans (game fonts often lack Cyrillic); without it - game font
        if st.font:
            kw["font"] = st.font
        return kw

    def sz(f=1.0):
        h = getattr(C, "screen_height", 720) or 720
        return max(12, int(h / 34.0 * f * UIS))

    def px(f):
        h = getattr(C, "screen_height", 720) or 720
        return max(1, int(h / 34.0 * f * UIS))

    st.icon = None
    try:
        if isinstance(DATA.get("icon"), T_TEXT) and DATA["icon"]:
            import base64
            st.icon = R.display.im.Data(base64.b64decode(DATA["icon"].encode("ascii")), "rut_globe.png")
    except Exception as e:
        err_once("icon", e)

    def add_icon(size):
        if st.icon is None:
            return
        try:
            ui.add(R.store.Transform(st.icon, zoom=size / 64.0, yalign=0.5))
        except Exception as e:
            err_once("icon", e)
            st.icon = None

    st.name_ok = {}
    st.font_data = None
    st.sys_lang = None

    def drawable(t):
        # can our font draw this name? (DejaVuSans has no Devanagari, Chinese, Thai...)
        if t not in st.name_ok:
            ok = all(ord(ch) < 0x250 for ch in t)
            if not ok and st.font:
                try:
                    if st.font_data is None:
                        f = R.loader.load(st.font)
                        try:
                            st.font_data = f.read()
                        finally:
                            f.close()
                    ok = cmap_has(st.font_data, u"".join(ch for ch in t if not ch.isspace()))
                except Exception as e:
                    err_once("font names", e)
            st.name_ok[t] = ok
        return st.name_ok[t]

    def name_of(code):
        # Russian panel: Russian names; any other panel: the language's own name (Deutsch, Espanol),
        # or the English name if our font can not draw it
        l = ui_lang()
        own = bool(UI.get(l) or UI.get(base_lang(l)))
        for x in st.langs:
            if x[0].lower() == code.lower():
                if own or len(x) < 3:
                    return x[1]
                return x[2] if drawable(x[2]) else (x[3] if len(x) > 3 else x[0])
        return code

    def lang_name(code):
        if code == u"off":
            return orig_name()
        return name_of(code)

    def orig_name():
        return name_of(st.src) + u" \u2014 " + ui_t("orig_mark", u"original")

    LANG_ALIAS = {u"he": u"iw", u"jv": u"jw", u"fil": u"tl", u"nb": u"no", u"nn": u"no", u"in": u"id",
                  u"ji": u"yi", u"mni": u"mni-Mtei", u"zh": u"zh-CN"}

    def system_lang():
        # the language of Windows / Android / the system (Ren'Py 7.3+ knows how to ask each of them);
        # None if it is the game's own language or Google does not know it
        l, rg = None, None
        try:
            f = getattr(getattr(R, "translation", None), "detect_user_locale", None)
            if f is not None:
                l, rg = f()
        except Exception as e:
            err_once("locale", e)
        if not l or not re.match(u"^[A-Za-z]{2,3}([_.-]|$)", u(l)) or u(l).lower() in (u"c", u"posix"):
            l, rg = None, None
            for k in ("LC_ALL", "LC_MESSAGES", "LANG"):
                v = os.environ.get(k) or u""
                if re.match(u"^[A-Za-z]{2,3}([_-]|$)", v):
                    l = v
                    break
        if not l:
            return None
        l = u(l).replace(u"-", u"_").split(u".")[0]
        if u"_" in l:
            l, r2 = l.split(u"_", 1)
            rg = rg or r2
        l, rg = l.lower(), u(rg or u"").lower()
        if l == u"zh":
            code = u"zh-TW" if rg in (u"tw", u"hk", u"mo") else u"zh-CN"
        elif l == u"pt" and rg == u"pt":
            code = u"pt-PT"
        else:
            code = LANG_ALIAS.get(l, l)
        if base_lang(code) == base_lang(st.src) or (code == u"iw" and base_lang(st.src) == u"he"):
            return None
        for x in st.langs:
            if x[0].lower() == code.lower():
                return x[0]
        return None

    def say(msg):
        st.msg = msg
        restart()

    def restart():
        try:
            E.restart_interaction()
        except Exception:
            pass

    def blocked():
        # Ren'Py error screens: nothing of ours there
        try:
            for nm in ("_exception", "_parse_errors"):
                if E.get_screen(nm):
                    return True
        except Exception:
            pass
        return False

    def console_up():
        try:
            return bool(E.get_screen("_console"))
        except Exception:
            return False

    def windows_hidden():
        try:
            return bool(getattr(R.store, "_windows_hidden", False))
        except Exception:
            return False

    def ensure(sup):
        st.sup = bool(sup)
        try:
            if blocked():
                return
            if E.get_screen("rut_live_button") is None:
                E.show_screen("rut_live_button")
            if st.panel_open and E.get_screen("rut_live_panel") is None:
                E.show_screen("rut_live_panel")
        except Exception as e:
            err_once("ensure", e)

    def open_panel():
        st.panel, st.msg, st.edit = "main", u"", None
        st.panel_open = True
        if not st.on_top and not E.get_screen("rut_live_panel"):
            E.show_screen("rut_live_panel")
        restart()

    def close_panel():
        st.edit = None
        st.panel_open = False
        try:
            if E.get_screen("rut_live_panel"):
                E.hide_screen("rut_live_panel")
        except Exception:
            pass
        restart()

    def last_lang():
        # the language the player chose last; before any choice - the language of the phone / computer
        # (or the one given to the script); None - nothing to suggest yet
        l = st.prefs.get("last")
        if l:
            return l
        d = DATA.get("lang")
        if d and d not in (u"auto", u"off"):
            return d
        return st.sys_lang

    def toggle():
        # Alt+T / "Show original": the original is the same as choosing the game's language in the list
        if st.off or st.lang == u"off":
            l = last_lang()
            if not l:  # no language chosen yet: the list of languages
                open_panel()
                go("langs")
                return
            set_lang(l)
            st.toast = ui_t("toast_on", u"Translation on")
        else:
            set_lang(u"off")
            st.toast = ui_t("toast_off", u"Original")
        st.toast_until = time.time() + 2.5

    def set_lang(code):
        st.lang = code
        st.prefs["lang"] = code
        if code != u"off":
            st.prefs["last"] = code
        st.save_now = True
        st.bad_lang = None
        st.off = False
        st.page = 0
        st.panel = "main"
        prefetch_names(code)
        refresh_everything()

    def show_translation():
        if st.lang == u"off" or st.off:
            toggle()

    def retry():
        st.fail.clear()
        st.down_until = 0.0
        st.server_down_until = 0.0
        for ep in st.eps:
            ep["until"] = 0.0
        if not st.server:
            start_probe()
        refresh_everything()
        say(ui_t("retry_done", u"Trying again"))

    def retry_corner():
        retry()
        st.msg = u""
        st.toast = ui_t("retry_toast", u"Refreshing...")
        st.toast_until = time.time() + 2.5

    def screen_items():
        # translated phrases that are on the screen now (the text widgets remember their phrase)
        out, seen = [], set()
        TX = R.text.text.Text

        def cb(d):
            if isinstance(d, TX):
                v = getattr(d, "_rut_s", None)
                if isinstance(v, tuple) and len(v) == 2 and v[0] not in seen:
                    seen.add(v[0])
                    out.append(v)
        try:
            sl = R.game.context().scene_lists
            names = [l for l in (getattr(C, "layers", None) or []) if l in sl.layers] or list(sl.layers.keys())
            for layer in names:
                for sle in sl.layers.get(layer, ()):
                    try:
                        sle.displayable.visit_all(cb)
                    except Exception:
                        pass
        except Exception as e:
            err_once("screen_items", e)
        out.sort(key=lambda v: 0 if v[1] == u"say" else 1)
        return out

    def fix_items():
        lang, items, seen = st.lang, [], set()

        def add(src, kind):
            if not src or src in seen:
                return
            seen.add(src)
            if kind == u"dict":
                items.append({"kind": "dict", "lang": lang, "src": src, "info": None})
                return
            if wanted(src, lang):
                info = mark(src)
                if info is not None:
                    items.append({"kind": kind, "lang": lang, "src": src, "info": info})
        for src, kind in screen_items():
            add(src, kind)
        for x in reversed(st.recent):  # and the last lines of dialogue
            if x["lang"] == lang:
                add(x["src"], x["kind"])
        return items

    def redo():
        # "Translate again": the phrases on the screen and the last lines of dialogue, each one separately
        if st.off or st.lang == u"off":
            return say(ui_t("orig_first", u"The original is shown - choose a language first"))
        n = 0
        for x in fix_items()[:30]:
            if x["kind"] == "dict":
                continue
            key = key_for(x["info"], x["lang"])[0]
            if key in st.manual.get(x["lang"], ()):
                continue
            if request(x["lang"], key, x["info"], 2, True):
                n += 1
        try:
            say(ui_t("redo_started", u"Translating again: %d") % n)
        except Exception:
            say(u"%d" % n)

    def open_fix():
        if st.off or st.lang == u"off":
            return say(ui_t("orig_first", u"The original is shown - choose a language first"))
        st.fix_list = fix_items()
        st.page = 0
        go("fix")

    def export():
        p = user_path()
        if not p:
            return say(ui_t("no_savedir", u"No save folder"))
        save_user(sync=True)
        where = [p]
        try:
            bd = getattr(C, "basedir", None)
            if bd and not getattr(R, "android", False) and not getattr(R, "ios", False):
                p2 = os.path.join(bd, "rut_live_export.json")
                with open(p, "rb") as f:
                    data = f.read()
                with open(p2, "wb") as f:
                    f.write(data)
                where.append(p2)
        except Exception:
            pass
        say(ui_t("saved_to", u"Saved:") + u" " + u"\n".join(where))

    def corner_idx():
        try:
            return int(st.prefs.get("corner", 0) or 0) % 4
        except Exception:
            return 0

    def corner():
        st.prefs["corner"] = (corner_idx() + 1) % 4
        st.save_now = True
        restart()

    def hide_in_game():
        st.prefs["hide_game"] = not st.prefs.get("hide_game")
        st.save_now = True
        say(ui_t("hidden_hint", u"In the game the button is hidden; it is always shown in the game menu "
                                u"and the main menu") if st.prefs["hide_game"] else u"")

    # --- Ren'Py's own hidden menus: they need a keyboard, phones have none ---
    def console_mod():
        m = sys.modules.get("store._console")
        return m if m is not None else getattr(R.store, "_console", None)

    def tool_ok(name):
        try:
            if name == "renderer":
                return bool(E.has_label("_choose_renderer"))
            if name == "console":
                m = console_mod()
                return m is not None and hasattr(m, "enter") and getattr(m, "console", None) is not None
            if name == "access":
                return bool(E.has_screen("_accessibility"))
        except Exception:
            pass
        return False

    def tool_renderer():
        close_panel()
        E.call_in_new_context("_choose_renderer")

    def prepare_console():
        # Games often switch the console off (config.console = False). It is created here, while the game
        # starts (init): then it is a part of the game's starting state - it never gets into save files and
        # a rollback does not remove it. Ren'Py replaces it with its own one if the console is enabled.
        try:
            m = console_mod()
            if m is not None and getattr(m, "console", None) is None and hasattr(m, "DebugConsole"):
                m.console = m.DebugConsole()
        except Exception as e:
            err_once("console", e)

    def tool_console():
        m = console_mod()
        close_panel()
        if getattr(m, "console", None) is None:
            return say(ui_t("no_tools", u"Not available in this Ren'Py version"))
        m.enter()

    def tool_access():
        close_panel()
        E.show_screen("_accessibility")
        restart()

    def console_exit():
        E.jump("_console_return")

    def status_lines(full):
        out = []
        now = time.time()
        if st.web:
            out.append(ui_t("st_web", u"Live translation is not available in the web version"))
            return out
        if full:
            if st.server and now >= st.server_down_until:
                t = ui_t("st_server", u"Via the script window")
                if st.server_eps:
                    t += u" \u00b7 Google: %s / %s" % (st.server_eps[0], st.server_eps[1])
                out.append(t)
            else:
                if st.server:
                    out.append(ui_t("st_server_down", u"Script window does not answer - using Google directly"))
                ok = sum(1 for e in st.eps if e["ok"] and e["until"] <= now)
                if st.probing and not ok:
                    out.append(ui_t("st_probing", u"Checking Google servers..."))
                elif st.probed or ok:
                    out.append(ui_t("st_eps", u"Google: %d of %d servers answer") % (ok, len(st.eps)))
        n = len(st.q) + len(st.inflight)
        if n:
            out.append(ui_t("st_pending", u"Waiting for translation: %d") % n)
        if now < st.down_until:
            out.append(ui_t("st_down", u"No connection to the translator - will retry in a minute"))
        if st.bad_lang:
            out.append(ui_t("st_badlang", u"Google does not know language %s") % st.bad_lang)
        return out

    def lbl(text, f=0.8, color="#ffffff"):
        ui.text(u"{#rut}" + text.replace(u"{", u"{{"), substitute=False, **fkw(size=sz(f), color=color))

    def btn(text, fn, f=0.8, sel=False, w=None, center=False):
        kw = dict(clicked=fn, background=Solid("#3a5ad0" if sel else "#2a3352"),
                  hover_background=Solid("#4a6ae8"), xpadding=px(0.45), ypadding=px(0.24),
                  xmargin=0, ymargin=0, foreground=None, hover_foreground=None)
        if w:
            kw.update(xminimum=w, xmaximum=w)
        else:
            kw["xfill"] = True
        tk = fkw(size=sz(f), color="#ffffff", hover_color="#ffffff", xalign=0.5 if center else 0.0, yalign=0.5)
        kw.update(("text_" + k, v) for k, v in tk.items())
        ui.textbutton(u"{#rut}" + text.replace(u"{", u"{{"), substitute=False, **kw)

    def row(items, Wi, f=0.8):
        # several buttons side by side: [(text, function, selected, share of the width)]
        sp = px(0.3)
        tot = float(sum(x[3] for x in items)) or 1.0
        avail = Wi - sp * (len(items) - 1)
        ui.hbox(spacing=sp)
        for text, fn, sel, share in items:
            btn(text, fn, f, sel, max(sz(), int(avail * share / tot)), True)
        ui.close()

    def act(fn, *a):
        def run():
            try:
                fn(*a)
            except CTRL:
                raise
            except Exception as e:
                err_once("ui", e)
                say(u"%r" % (e,))
            return None
        return run

    CTRL = tuple(getattr(R.game, "CONTROL_EXCEPTIONS", None) or ())
    try:
        CTRL = CTRL + (R.display.core.EndInteraction,)
    except Exception:
        pass

    def noop():
        return None

    IV = getattr(R.store, "InputValue", None)
    if IV is not None:
        class Val(IV):
            def __init__(self, name):
                self.name = name

            def get_text(self):
                return st.inp.get(self.name, u"")

            def set_text(self, s):
                st.inp[self.name] = s

            def enter(self):
                return None
    else:
        Val = None

    def small_w():
        sw = C.screen_width
        return int(min(sw * 0.94, max(sw * 0.32, sz() * 18)))

    def big_w():
        sw = C.screen_width
        return int(min(sw * 0.94, max(sw * 0.55, sz() * 30)))

    def field(name, Wi):
        ui.frame(background=Solid("#f2f2f2"), xpadding=px(0.3), ypadding=px(0.2), xmargin=0, ymargin=0,
                 xminimum=Wi, xmaximum=Wi)
        if Val is not None:
            ui.input(value=Val(name), length=2000, **fkw(size=sz(0.8), color="#111111"))
        else:
            ui.input(st.inp.get(name, u""), length=2000, changed=lambda s: st.inp.__setitem__(name, s),
                     **fkw(size=sz(0.8), color="#111111"))

    def shown_marks(t):
        return MARK_RE.sub(lambda m: u"\u2039" + m.group(1) + u"\u203a", t)

    def short(t, n=70):
        t = re.sub(u"\\s+", u" ", t).strip()
        return t if len(t) <= n else t[:n - 1] + u"\u2026"

    def start_edit(x):
        lang = x["lang"]
        if x["kind"] == "dict":
            cur = st.user_dict.get(lang, {}).get(x["src"]) or (st.dicts.get(lang) or {}).get(x["src"]) or u""
            st.edit = {"x": x, "orig": x["src"], "cur": cur}
        else:
            info = x["info"]
            key, mp = key_for(info, lang)
            M = st.mem.get(lang) or {}
            cur = None
            if mp and key in M:
                cur = from_stand(u(M[key]), mp)
            if cur is None and info["core"] in M:
                cur, key, mp = u(M[info["core"]]), info["core"], None
            st.edit = {"x": x, "orig": shown_marks(info["core"]), "cur": shown_marks(norm_marks(cur or u"", info["core"])),
                       "key": key, "mp": mp}
        st.inp["edit"] = st.edit["cur"]
        st.panel = "edit"
        st.msg = u""
        restart()

    def toks_of(t):
        return sorted(re.findall(u"\\{[^{}]*\\}|\\[[^\\[\\]]*\\]", t))

    def save_edit(remove=False):
        ed = st.edit
        if not ed:
            return
        x, lang = ed["x"], ed["x"]["lang"]
        val = (st.inp.get("edit") or u"").strip()
        if x["kind"] == "dict":
            D = st.user_dict.setdefault(lang, {})
            if remove:
                D.pop(x["src"], None)
            else:
                if toks_of(val) != toks_of(ed["cur"]):
                    return say(ui_t("edit_tags", u"Keep all {tags} and [variables] as they were"))
                D[x["src"]] = val
        else:
            info = x["info"]
            key = key_for(info, lang)[0]
            if remove:
                for k in (key, info["core"]):
                    st.manual.get(lang, set()).discard(k)
                    st.user_manual.get(lang, set()).discard(k)
                post_manual(lang, key, None, True)
                request(lang, key, info, 2, True)
            else:
                text = MARK_LOOSE.sub(lambda m: MO + m.group(1) + MC, val)
                if unmark(text, info, None) is None:
                    return say(ui_t("edit_marks", u"Keep every \u2039n\u203a mark (they may be moved)"))
                k = ed["key"] if ed["key"] in (key, info["core"]) else info["core"]
                v = to_stand(text, ed["mp"]) if (ed["mp"] and k == key) else text
                st.mem.setdefault(lang, {})[k] = v
                st.user.setdefault(lang, {})[k] = v
                st.manual.setdefault(lang, set()).add(k)
                st.user_manual.setdefault(lang, set()).add(k)
                post_manual(lang, k, v, False)
        st.save_now = True
        st.edit = None
        st.panel = "fix"
        st.memo = {}
        st.refresh_all = True
        say(ui_t("edit_saved", u"Saved"))

    def post_manual(lang, key, value, remove):
        if not st.server or time.time() < st.server_down_until:
            return

        def run():
            try:
                body = json.dumps({"lang": lang, "key": key, "value": value, "remove": bool(remove)})
                if not isinstance(body, T_BYTES):
                    body = body.encode("utf-8")
                http(st.server.replace("/__rut/translate", "/__rut/manual"), body,
                     {"Content-Type": "application/json"}, timeout=15)
            except Exception as e:
                err_once("manual", e)
        t = threading.Thread(target=run)
        t.daemon = True
        t.start()

    def custom_lang():
        t = (st.inp.get("code") or u"").strip()
        code = None
        for x in st.langs:
            if t.lower() in [y.lower() for y in x[:3]]:
                code = x[0]
        if code is None and re.match(u"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,4})?$", t):
            p = t.split(u"-")
            code = p[0].lower() + (u"-" + p[1] if len(p) > 1 else u"")
        if not code or code == st.src:
            return say(ui_t("bad_code", u"Unknown language code (examples: hy, ka, he)"))
        set_lang(code)

    def go(panel):
        st.panel = panel
        st.msg = u""
        restart()

    def page(d, total):
        st.page = max(0, min(total - 1, st.page + d))
        restart()

    def safe_build(fn, where):
        depth = len(getattr(ui, "stack", None) or [])
        try:
            fn()
        except Exception as e:
            err_once(where, e)
            st.panel, st.edit = "main", None
            try:
                while len(ui.stack) > depth:
                    ui.close()
            except Exception:
                pass

    def scr_panel(**kwargs):
        safe_build(build_panel, "panel")

    def scr_button(**kwargs):
        safe_build(build_button, "button")

    CORNERS = [(1.0, 0.0), (0.0, 0.0), (0.0, 1.0), (1.0, 1.0)]

    def key_hint(k):
        return u" (" + k + u")" if PC else u""

    def view_main(Wi):
        lbl(ui_t("title", u"Live translation"), 0.75, "#c8cfe8")
        off = st.off or st.lang == u"off"
        cur = orig_name() if off else lang_name(st.lang)
        row([(cur + u" \u25be", act(go, "langs"), False, 1),
             (u"\u27f3 " + ui_t("retry_short", u"Refresh"), act(retry), False, 1)], Wi)
        if off and last_lang():
            btn(ui_t("show_tr", u"Show translation") + u": " + lang_name(last_lang()) + key_hint(u"Alt+T"),
                act(toggle))
        elif off:
            btn(ui_t("choose_lang_btn", u"Choose the translation language..."), act(go, "langs"))
        else:
            btn(ui_t("show_orig", u"Show original") + key_hint(u"Alt+T"), act(toggle))
            row([(u"\u21bb " + ui_t("redo_short", u"Translate again"), act(redo), False, 1),
                 (u"\u270e " + ui_t("fix_short", u"Fix a phrase"), act(open_fix), False, 1)], Wi, 0.72)
        for line in status_lines(False):
            lbl(line, 0.6, "#c8cfe8")
        return [(ui_t("more", u"More..."), act(go, "more"), False, 1),
                (u"\u2715 " + ui_t("close", u"Close"), act(close_panel), False, 1)]

    def view_more(Wi):
        lbl(ui_t("more_title", u"Live translation: more"), 0.75, "#c8cfe8")
        if not st.web:
            btn(ui_t("export", u"Save translations to a file"), act(export))
        names_c = [ui_t("c_tr", u"top right"), ui_t("c_tl", u"top left"), ui_t("c_bl", u"bottom left"),
                   ui_t("c_br", u"bottom right")]
        btn(ui_t("corner", u"Button in the corner:") + u" " + names_c[corner_idx()], act(corner))
        if st.on_top:
            btn(ui_t("btn_hidden", u"In the game the button: hidden") if st.prefs.get("hide_game")
                else ui_t("btn_shown", u"In the game the button: shown"), act(hide_in_game))
        btn(ui_t("tools", u"Ren'Py tools..."), act(go, "tools"))
        for line in status_lines(True):
            lbl(line, 0.6, "#c8cfe8")
        if PC:
            lbl(ui_t("keys", u"Alt+T - original/translation, Alt+L - this panel"), 0.55, "#8f98b8")
        return [(u"\u2039 " + ui_t("back", u"Back"), act(go, "main"), False, 1),
                (u"\u2715 " + ui_t("close", u"Close"), act(close_panel), False, 1)]

    def view_tools(Wi):
        lbl(ui_t("tools_title", u"Ren'Py tools"), 0.75, "#c8cfe8")
        n = 0
        if tool_ok("renderer"):
            btn(ui_t("tool_renderer", u"Renderer: GL / ANGLE / GLES") + key_hint(u"Shift+G"), act(tool_renderer))
            n += 1
        if tool_ok("access"):
            btn(ui_t("tool_access", u"Accessibility: font, text size") + key_hint(u"Shift+A"), act(tool_access))
            n += 1
        if tool_ok("console"):
            btn(ui_t("tool_console", u"Ren'Py console") + key_hint(u"Shift+O"), act(tool_console))
            lbl(ui_t("console_hint", u"Close the console with the button in the corner"), 0.55, "#8f98b8")
            n += 1
        if not n:
            lbl(ui_t("no_tools", u"Not available in this Ren'Py version"), 0.6, "#c8cfe8")
        return [(u"\u2039 " + ui_t("back", u"Back"), act(go, "more"), False, 1),
                (u"\u2715 " + ui_t("close", u"Close"), act(close_panel), False, 1)]

    def view_langs(Wi):
        lbl(ui_t("choose_lang", u"Translation language"), 0.9)
        codes = [u"off"]
        for c in st.fav + [x[0] for x in sorted(st.langs, key=lambda x: name_of(x[0]).lower())]:
            if c not in codes and c != st.src:
                codes.append(c)
        per = 16
        total = max(1, (len(codes) + per - 1) // per)
        st.page = max(0, min(total - 1, st.page))
        chunk = codes[st.page * per:(st.page + 1) * per]
        sp = px(0.3)
        cw = int((Wi - sp) / 2)
        ui.hbox(spacing=sp)
        half = (len(chunk) + 1) // 2
        for col in (chunk[:half], chunk[half:]):
            ui.vbox(spacing=px(0.2), xminimum=cw, xmaximum=cw)
            for c in col:
                if c == u"off":
                    btn(orig_name(), act(set_lang, u"off"), 0.7, st.lang == u"off" or st.off)
                else:
                    btn(u"%s (%s)" % (lang_name(c), c), act(set_lang, c), 0.7, c == st.lang and not st.off)
            ui.close()
        ui.close()
        row([(u"\u25c0", act(page, -1, total), False, 1),
             (u"%d / %d" % (st.page + 1, total), noop, False, 1),
             (u"\u25b6", act(page, 1, total), False, 1)], Wi)
        return [(ui_t("own_code", u"Own language code..."), act(go, "code"), False, 1),
                (u"\u2039 " + ui_t("back", u"Back"), act(go, "main"), False, 1)]

    def view_code(Wi):
        lbl(ui_t("own_code", u"Own language code..."), 0.9)
        lbl(ui_t("code_hint", u"Code or name of the language, e.g. hy, ka, he"), 0.65, "#c8cfe8")
        field("code", Wi)
        return [(ui_t("ok", u"OK"), act(custom_lang), True, 1),
                (u"\u2039 " + ui_t("back", u"Back"), act(go, "langs"), False, 1)]

    def view_fix(Wi):
        lbl(ui_t("fix_title", u"Which phrase to fix?"), 0.9)
        items = st.fix_list
        if not items:
            lbl(ui_t("fix_none", u"No translated text on the screen"), 0.75, "#c8cfe8")
        per = 8
        total = max(1, (len(items) + per - 1) // per)
        st.page = max(0, min(total - 1, st.page))
        for x in items[st.page * per:(st.page + 1) * per]:
            shown = None
            try:
                if x["kind"] == "dict":
                    shown = dict_value(x["src"])
                else:
                    shown = lookup(x["info"], x["lang"], False)[0]
            except Exception:
                shown = None
            btn(short(shown or x["src"]), act(start_edit, x), 0.65)
        if total > 1:
            row([(u"\u25c0", act(page, -1, total), False, 1),
                 (u"%d / %d" % (st.page + 1, total), noop, False, 1),
                 (u"\u25b6", act(page, 1, total), False, 1)], Wi)
        return [(u"\u2039 " + ui_t("back", u"Back"), act(go, "main"), False, 1),
                (u"\u2715 " + ui_t("close", u"Close"), act(close_panel), False, 1)]

    def view_edit(Wi):
        lbl(ui_t("fix_one", u"Fix translation"), 0.9)
        lbl(ui_t("original_txt", u"Original:"), 0.6, "#c8cfe8")
        lbl(st.edit["orig"], 0.7)
        lbl(ui_t("translation_txt", u"Translation:"), 0.6, "#c8cfe8")
        field("edit", Wi)
        if st.edit["x"]["kind"] != "dict" and u"\u2039" in st.edit["orig"]:
            lbl(ui_t("marks_hint", u"\u2039n\u203a - links, formatting and numbers: keep them all"),
                0.55, "#c8cfe8")
        x = st.edit["x"]
        foot = [(ui_t("save", u"Save"), act(save_edit), True, 2)]
        if x["kind"] == "dict" and x["src"] in st.user_dict.get(x["lang"], {}) or (
                x["kind"] != "dict" and st.edit.get("key") in st.manual.get(x["lang"], ())):
            foot.append((ui_t("google_back", u"Google translation"), act(save_edit, True), False, 3))
        return foot + [(ui_t("cancel", u"Cancel"), act(go, "fix"), False, 2)]

    VIEWS = {"main": view_main, "more": view_more, "tools": view_tools, "langs": view_langs,
             "code": view_code, "fix": view_fix, "edit": view_edit}

    def build_panel():
        if st.on_top and not st.panel_open:
            return
        p = st.panel if st.panel in VIEWS else "main"
        if p == "edit" and not st.edit:
            p = st.panel = "fix"
        big = p in ("langs", "code", "fix", "edit")
        sw, sh = C.screen_width, C.screen_height
        ui.keymap(game_menu=act(close_panel), K_ESCAPE=act(close_panel))
        # a tap outside the panel closes it; a tap on the panel itself (between its buttons) does nothing
        dim = Solid("#00000066" if big else "#00000030")
        ui.button(clicked=act(close_panel), xpos=0, ypos=0, xanchor=0, yanchor=0, xminimum=sw, xmaximum=sw,
                  yminimum=sh, ymaximum=sh, background=dim, hover_background=dim, xpadding=0, ypadding=0,
                  xmargin=0, ymargin=0, foreground=None, hover_foreground=None)
        ui.null()
        W = big_w() if big else small_w()
        pad = px(0.55)
        box = Solid("#151a2cf4")
        kw = dict(clicked=noop, xminimum=W, xmaximum=W, background=box, hover_background=box, xpadding=pad,
                  ypadding=pad, xmargin=0, ymargin=0, foreground=None, hover_foreground=None)
        if big:
            kw.update(xalign=0.5, yalign=0.5)
        else:
            xa, ya = CORNERS[corner_idx()]
            m = px(0.25)
            kw.update(xalign=xa, yalign=ya, xoffset=-m if xa else m, yoffset=-m if ya else m)
        ui.button(**kw)
        ui.vbox(spacing=px(0.28))
        Wi = W - 2 * pad
        foot = VIEWS[p](Wi)
        if st.msg:
            lbl(st.msg, 0.6, "#ffd27a")
        if foot:
            row(foot, Wi)
        ui.close()

    def trouble():
        now = time.time()
        if now < st.down_until or st.bad_lang:
            return True
        for f in list(st.fail.values()):
            if now - f < 120:
                return True
        return False

    def corner_bar(items):
        # [(label, function, globe icon, warning colour)]; the language button stays in the very corner.
        # Around each small visible button there is a bigger invisible area: easier to hit with a finger.
        xa, ya = CORNERS[corner_idx()]
        m = px(0.4) if TOUCH else 0
        if xa > 0.5:
            items = list(reversed(items))
        ui.hbox(xalign=xa, yalign=ya, spacing=0 if TOUCH else px(0.12))
        for label, fn, with_icon, warn in items:
            ui.button(clicked=fn, background=None, hover_background=None, xpadding=m, ypadding=m, xmargin=0,
                      ymargin=0, foreground=None, hover_foreground=None)
            ui.frame(background=Solid("#b8650cd8" if warn else "#00000078"), hover_background=Solid("#3a5ad0d8"),
                     xpadding=px(0.3), ypadding=px(0.12), xmargin=0, ymargin=0)
            ui.hbox(spacing=px(0.15))
            if with_icon:
                add_icon(int(sz(0.62)))
            ui.text(u"{#rut}" + label.replace(u"{", u"{{"), substitute=False,
                    **fkw(size=sz(0.55), color="#ffffff", yalign=0.5))
            ui.close()
        ui.close()

    def build_button():
        if blocked():
            return
        if console_up():
            corner_bar([(u"\u2715 " + ui_t("console_exit", u"Close console"), act(console_exit), False, False)])
            return
        if st.panel_open if st.on_top else E.get_screen("rut_live_panel"):
            return
        if windows_hidden():
            return
        now = time.time()
        toast = st.toast if now < st.toast_until else u""
        if st.on_top and st.prefs.get("hide_game") and not st.sup:
            if toast:
                xa, ya = CORNERS[corner_idx()]
                ui.text(u"{#rut}" + toast, substitute=False, **fkw(size=sz(0.55), color="#ffffff", xalign=xa,
                                                                   yalign=ya, outlines=[(2, "#000000", 0, 0)]))
            return
        off = st.off or st.lang == u"off"
        label = st.src.upper() if off else st.lang.upper()
        if st.q or st.inflight:
            label += u" \u2026"
        if toast:
            label = toast
        items = [(label, act(open_panel), True, False)]
        if not off and not st.web:
            items.append((u"\u27f3", act(retry_corner), False, trouble()))  # "Refresh" right on the game screen
        corner_bar(items)

    # ------------------------------------------------------------------
    # Start
    # ------------------------------------------------------------------

    load_user()
    if not st.prefs.get("lang"):
        st.prefs.pop("last", None)  # v0.10-v0.14 wrote the default language there by themselves
    try:
        if int(st.prefs.get("corner", 0) or 0) >= 4:  # v0.10: "hidden" - now hidden only during the game
            st.prefs["corner"] = 0
            st.prefs["hide_game"] = True
    except Exception:
        st.prefs["corner"] = 0
    st.sys_lang = system_lang()
    lang = st.prefs.get("lang")  # chosen by the player before
    if not lang:
        d = DATA.get("lang") or u"auto"
        lang = (st.sys_lang if d == u"auto" else d) or u"off"  # first start: the language of the device
    if lang != u"off" and not re.match(u"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,4})?$", lang):
        lang = u"off"
    st.lang = lang
    log("system language:", st.sys_lang)
    if CFG.get("tools", True):
        prepare_console()

    def define(name, fn, **kw):
        try:
            E.define_screen(name, fn, **kw)
            return True
        except TypeError:
            for k in ("layer", "predict"):
                kw.pop(k, None)
            E.define_screen(name, fn, **kw)
            return False

    try:
        SCR = R.display.screen
        orig_sos = getattr(SCR, "show_overlay_screens", None)
        orig_sos = getattr(orig_sos, "_rut_orig", None) or orig_sos
        if orig_sos is not None and "overlay" in list(getattr(C, "layers", None) or ()):
            st.on_top = (define("rut_live_panel", scr_panel, modal="True", zorder="1000", layer="overlay",
                                predict="False")
                         and define("rut_live_button", scr_button, zorder="999", layer="overlay", predict="False"))
        if st.on_top:
            def show_overlay_screens(suppress_overlay, *args, **kwargs):
                rv = orig_sos(suppress_overlay, *args, **kwargs)
                ensure(suppress_overlay)
                return rv
            show_overlay_screens._rut_orig = orig_sos
            SCR.show_overlay_screens = show_overlay_screens
            IFC = R.display.core.Interface
            orig_wn = IFC.__dict__.get("with_none")
            orig_wn = getattr(orig_wn, "_rut_orig", None) or orig_wn
            if orig_wn is not None:
                def with_none(self, *args, **kwargs):
                    # the picture a transition starts from: with the button, so it does not blink
                    ensure(getattr(R.store, "suppress_overlay", False))
                    return orig_wn(self, *args, **kwargs)
                with_none._rut_orig = orig_wn
                IFC.with_none = with_none
        else:
            define("rut_live_panel", scr_panel, modal="True", zorder="1000")
            define("rut_live_button", scr_button, zorder="999")
            C.overlay_screens.append("rut_live_button")
    except Exception as e:
        log("screens:", e)
    try:
        C.keymap["rut_toggle"] = ["alt_K_t"]
        C.keymap["rut_panel"] = ["alt_K_l"]
        C.underlay.append(R.display.behavior.Keymap(rut_toggle=act(toggle), rut_panel=act(open_panel)))
    except Exception as e:
        log("keys:", e)
    C.periodic_callbacks.append(periodic)
    qc = getattr(C, "quit_callbacks", None)
    if isinstance(qc, list):
        qc.append(lambda: save_user(sync=True))

    st.api = {"open": open_panel, "close": close_panel, "go": go, "set_lang": set_lang, "toggle": toggle,
              "export": export, "start_edit": start_edit, "save_edit": save_edit, "redo": redo, "retry": retry,
              "corner": corner, "hide_in_game": hide_in_game, "show_translation": show_translation,
              "tool_renderer": tool_renderer, "tool_console": tool_console, "tool_access": tool_access,
              "console_exit": console_exit, "open_fix": open_fix, "retry_corner": retry_corner,
              "fix_items": fix_items}
    st.dbg = dict((k, v) for k, v in locals().items() if callable(v))  # for tests
    R._rut_live = st
    log("live translation ready:", st.lang, "server" if st.server else "direct", "top" if st.on_top else "")

_rut_live_setup()
del _rut_live_setup
'''

# ---------------------------------------------------------------------------
# Ren'Py: перевод на лету (-l / -c) — модуль в игре сам переводит то, что появляется на экране
# ---------------------------------------------------------------------------

RPY_LIVE_UI = {
    "title": "Перевод на лету", "orig_mark": "оригинал", "is_off": "выключен",
    "toast_off": "Показан оригинал", "toast_on": "Перевод включён",
    "retry_short": "Обновить", "retry_done": "Пробую перевести снова всё, что не перевелось",
    "retry_toast": "Обновляю…", "redo_short": "Перевести заново", "fix_short": "Исправить фразу",
    "orig_first": "Сейчас показан оригинал — сначала выберите язык",
    "show_orig": "Показать оригинал", "show_tr": "Показать перевод", "more": "Ещё…", "close": "Закрыть",
    "back": "Назад", "more_title": "Перевод на лету: ещё",
    "redo_started": "Перевожу заново то, что на экране, и последние реплики (фраз: %d)",
    "export": "Сохранить переводы в файл",
    "no_savedir": "У игры нет папки сохранений — сохранить некуда", "saved_to": "Сохранено:",
    "corner": "Кнопка в углу:", "c_tr": "справа вверху", "c_tl": "слева вверху", "c_bl": "слева внизу",
    "c_br": "справа внизу",
    "btn_shown": "Кнопка во время игры: видна", "btn_hidden": "Кнопка во время игры: скрыта",
    "hidden_hint": "Во время игры кнопки не будет. В главном меню и в меню игры (настройки, сохранение) "
                   "она есть всегда — там её можно вернуть.",
    "tools": "Инструменты Ren'Py…", "tools_title": "Инструменты Ren'Py",
    "tool_renderer": "Рендерер: GL, ANGLE, GLES…", "tool_access": "Доступность: шрифт, размер текста",
    "tool_console": "Консоль Ren'Py", "console_hint": "Закрыть консоль — кнопка «✕ Закрыть консоль» в углу",
    "console_exit": "Закрыть консоль", "no_tools": "В этой версии Ren'Py недоступно",
    "keys": "Alt+T — оригинал/перевод, Alt+L — эта панель",
    "st_web": "В веб-версии игры перевод на лету недоступен", "st_server": "Через окно скрипта",
    "st_server_down": "Окно скрипта не отвечает — перевожу напрямую через Google",
    "st_probing": "Проверяю серверы Google…", "st_eps": "Google: %d из %d серверов отвечают",
    "st_pending": "Ждут перевода: %d", "st_down": "Нет связи с переводчиком — повторю через минуту",
    "st_badlang": "Google не знает язык «%s»", "edit_tags": "Оставьте все {теги} и [переменные] как были",
    "edit_marks": "Оставьте все метки ‹n› (их можно переставлять)", "edit_saved": "Исправление сохранено",
    "bad_code": "Не понял код языка (примеры: hy, ka, he)", "choose_lang": "Язык перевода", "choose_lang_btn": "Выбрать язык перевода…",
    "own_code": "Свой код языка…", "code_hint": "Код или название языка, например: hy, ka, he",
    "ok": "OK", "fix_title": "Какую фразу исправить? (с экрана и последние реплики)",
    "fix_none": "На экране нет переведённого текста",
    "fix_one": "Исправить перевод", "original_txt": "Оригинал:", "translation_txt": "Перевод:",
    "marks_hint": "‹n› — ссылки, выделение и числа: оставьте все метки", "save": "Сохранить",
    "google_back": "Вернуть перевод Google", "cancel": "Отмена",
}
# Значок «глобус» для кнопки в углу (PNG 64×64, белый с прозрачностью), base64
RPY_LIVE_ICON = (
    "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAILElEQVR42u1bW4iVVRT+/vOfM07j6MyYTl4S0dQRkR56kCRKCLqA"
    "DD70FNqgPhmhBvqQvUQgUeBLht1ACnsQg6AQIexBLKIQezHJ+2W0UdTxMl6GZub8Z/Xgt3PNcu///OfMjBXnbNj85//32muvtfbe"
    "67b3iUQEtVxyqPGSf4hjRRR4VAZOAJT4HHuixnALaIaTKhiKAMRjLZCxEIAjvGi+PwpgDoDZAB4HMENtQQHQA+ACgLMAzgC45lmt"
    "yWgLYjQF4GY84XsMYAmAlwEsBbAQwKSMuK4D+APAAQDfA/jF4B21FTFaAogVgTMBvAbgVQCLKtzfIT1xBMAuAF9xldgx/zUB5MiM"
    "cElvArAKQCvbE26FvGGs5LFAJbMlSqpvzO83AXwJYCu3TMRaqpoDEam2xnxGIrJBRK7K/TIgIoPiLyUJl1DbIHG6cpVjRoaWimu1"
    "zOf5nCci+w2hQ+r9nIjsJvElESny+wciclrBXRSRbfxdJOwA+55TcENGsPtJg6ZpzAXgBlouItcChP0mImtEZJyIbOG3v/j8nP3/"
    "VPDX+e0TA7uFONYQp0/Q10hLVUKolvn1ZlYS/j4jIl0KbpZqT0SkW0SayFSPwnFTRFpEpJEwDn6IONzYXRxDVLsr66sRQjXMb1YE"
    "FBUBn4lIm4LNqWXtZnQV2yeIyAWzAtrZttr02UZcbvw2jiVqy7gJ2FypELIA5USkgb/XeWZ9QDEWcRbzItIqIr1KsZ0XkfFsa/YI"
    "YArbxhPWKcVe4soTt1N8q5Ri1KthHdsbSPuorYBOxbxTVKdFZFEAfoWZyY2m/bwSwDUzaxtN3xWBMRaRBqdgnRA6s/KVL+PZAcA8"
    "enFf0D47e14EsB3ABAAvARhSvkEJwFrC5/m8DeB5wjQAaFRjFQAsIwz41H3XArikcLs+t0jD+wpWAOwEsJre5EnlW1TkCDnf+yMA"
    "b3DgSAlGMkR2D6uIoctN1HYA6wKxSaZw2CFLKIC8QhQpj83nGmvPL/G4wAUjwCHV7lzi2HiGScAbjVTfWAVNUi5mCK0A5+K2AzjM"
    "539pxrOuiCsAnuTT6zLnU/Z/CcBmMj9E2OsAfgzsKT0LLwBo5u9BAPuIw8HEhHlEzf4+wjqYAoAXqS8A4A6AHzxjWZ31HIA24mwn"
    "D28Gs18BswcRmSYit6lhnXZdmUGzFmjWXDkcgOtOsQKuHjamspBh/JXKWpXIwzTD2z81l5InXM1ZdLP/O0PSvIrQdG3g82k1AwBw"
    "VLW7fuPNjESMIGPCOFxH1QppI249lq6Orl2kNc9+zeTFmwPNeZZRws5dZmltVUqoyN+6OiU1Xyk+ADhm2pOAMvPhOmZwzQ/gSpRy"
    "Tkirpr1LWbUoTQBO+S0G0MEOBdrgb5SA0so8835qBMrsVBncPiFGpPUSaU/Iy2JlHlNXAOiUQC3j7wDcVUnKkOYFc35QJqw7zREp"
    "g6vb4JpdBpdTsHdJs+ZhmeHRKwBnJpaagfcENK+v7wzVV2iCqhXAFcWUxl3KYAL3GB6W+vrmPKZvksrlOXfzYIrTo81SDsBkhbsf"
    "wI0RbIEbxOHonKy2aZQyEUKab5EHkKdJyqN9QADu9xMAWtRePw6gV7VHKbVJ5QOd7e5XA0bGnbZCjAxsP3G40sox0mhwvPSSdqcb"
    "WsjbML5znv0/x+ydo8Yt9lUn9UYSqAVwR8GUlGvtU2AW7o4RQBPH0GOGKowZ1bxFaZ7gTPPew0HzoYBCRWmtynNz5rLRE6w0mlXg"
    "Vs+AJ9jSYzZwjDsmMvR5uEXSnsabVwDTTdvrzPNHGRRZ3ghgDoATgeU+Vb1PBHAowNBjRgA/pUyE1UnNhpfpWQRg92er2deVlAKP"
    "wbKcL0zPePo0dYSnV/Xj8UqPx/u5N7NKuMXkAW4FYFvMSVBfYItNNHmBvgp8inFGKWcSQI9SYHkAHwN4L6MSnMG9PI7fzzCA8SnB"
    "Q2rZ9wF4ikdfVgn+qlzgQQDPksYsSvBtHtc5XnqyCOCCeZ9SgTMTkchxSjDXAwSWjPfWq3KCoW06COBiBfRMKcPbMOSiZg3Kg1po"
    "Tm19NaeY71c4m5k0dTAOrhBQmBZugtLkbjsOVkDPQsPLGeuW5zy+/GkuSbfvOnDvckMpg0PUz2WsBdCkBkzL09k2YV8tgJsco5wD"
    "VCLNHSoe6CNvw+IBuwLckj2iPKiJDCWjFKshKpboVYM0MZFRbWkjDkdwr/LlJUUfRaR5ovICj5C3XGgF6PcDJhHRmSEpmjNK1MXm"
    "7SEbnMFet5scRE8G8+2E02l4OODrmwuEoXvN3lnONFaSwoj7ftYMPGsEAphlcJ0tg8sJazxp1jzs9YXlvnxAxFDyOPfOEIBpAF4x"
    "sXmonDTvc0ewBeaWwe07jxDSOo20x+TloC81ngtkVIq4d7ykJbZJMe9LirqDjBMmEbHAtMcBIfpwLTC4TgRwxcqkx6RV076TPD2Y"
    "0ar1tHg+kFGJmVTcAWCDMjEfcnmVOxjRdr6D6Sl7MKKdlAkAvvUcjHQYP2F3xoMRUUp7B3nx3iqr+aOxXEpeLQZwGcDXKu8ufBbV"
    "t0FPtTc6E64ADWMlr9uHzGy5LJJvLE2LpjEh7Zdx/3JlxdGgcy1jNft5I+UsJc5gPQpl6EjDYYOt2LjKYcQp9wN8FyRaTKrqLdy7"
    "xqo9LhelvQvgGdy/ALlWHXQ0UDM7PXCbWafbyvx9qvr+DOAd+C9ILMHwCxIR3d5MFyRq/opM/ZJU/Zpc/aJk/aps/bJ0LV+Xr/k/"
    "TNT/MlP/01T9b3P1P04+rBi95v46+78oNX88/jeDWP+aAr72sAAAAABJRU5ErkJggg=="
)
RPY_LIVE_FAV = ["ru", "uk", "be", "pl", "cs", "de", "fr", "es", "it", "pt", "tr", "kk", "zh-CN", "ja", "ko"]


# Названия языков по-английски — для панели игры, когда она не на русском (своё название языка не всегда
# можно показать: в шрифте Ren'Py нет, например, деванагари и иероглифов)
RPY_LANG_EN = {
    "af": "Afrikaans", "sq": "Albanian", "am": "Amharic", "ar": "Arabic", "hy": "Armenian", "as": "Assamese",
    "ay": "Aymara", "az": "Azerbaijani", "bm": "Bambara", "eu": "Basque", "be": "Belarusian", "bn": "Bengali",
    "bho": "Bhojpuri", "bs": "Bosnian", "bg": "Bulgarian", "ca": "Catalan", "ceb": "Cebuano",
    "ny": "Chichewa", "zh-CN": "Chinese (Simplified)", "zh-TW": "Chinese (Traditional)", "co": "Corsican",
    "hr": "Croatian", "cs": "Czech", "da": "Danish", "dv": "Dhivehi", "doi": "Dogri", "nl": "Dutch",
    "en": "English", "eo": "Esperanto", "et": "Estonian", "ee": "Ewe", "tl": "Filipino", "fi": "Finnish",
    "fr": "French", "fy": "Frisian", "gl": "Galician", "ka": "Georgian", "de": "German", "el": "Greek",
    "gn": "Guarani", "gu": "Gujarati", "ht": "Haitian Creole", "ha": "Hausa", "haw": "Hawaiian",
    "iw": "Hebrew", "hi": "Hindi", "hmn": "Hmong", "hu": "Hungarian", "is": "Icelandic", "ig": "Igbo",
    "ilo": "Ilocano", "id": "Indonesian", "ga": "Irish", "it": "Italian", "ja": "Japanese", "jw": "Javanese",
    "kn": "Kannada", "kk": "Kazakh", "km": "Khmer", "rw": "Kinyarwanda", "gom": "Konkani", "ko": "Korean",
    "kri": "Krio", "ku": "Kurdish (Kurmanji)", "ckb": "Kurdish (Sorani)", "ky": "Kyrgyz", "lo": "Lao",
    "la": "Latin", "lv": "Latvian", "ln": "Lingala", "lt": "Lithuanian", "lg": "Luganda",
    "lb": "Luxembourgish", "mk": "Macedonian", "mai": "Maithili", "mg": "Malagasy", "ms": "Malay",
    "ml": "Malayalam", "mt": "Maltese", "mi": "Maori", "mr": "Marathi", "mni-Mtei": "Meiteilon (Manipuri)",
    "lus": "Mizo", "mn": "Mongolian", "my": "Myanmar (Burmese)", "ne": "Nepali", "no": "Norwegian",
    "or": "Odia (Oriya)", "om": "Oromo", "ps": "Pashto", "fa": "Persian", "pl": "Polish", "pt": "Portuguese",
    "pt-PT": "Portuguese (Portugal)", "pa": "Punjabi", "qu": "Quechua", "ro": "Romanian", "ru": "Russian",
    "sm": "Samoan", "sa": "Sanskrit", "gd": "Scots Gaelic", "nso": "Sepedi", "sr": "Serbian", "st": "Sesotho",
    "sn": "Shona", "sd": "Sindhi", "si": "Sinhala", "sk": "Slovak", "sl": "Slovenian", "so": "Somali",
    "es": "Spanish", "su": "Sundanese", "sw": "Swahili", "sv": "Swedish", "tg": "Tajik", "ta": "Tamil",
    "tt": "Tatar", "te": "Telugu", "th": "Thai", "ti": "Tigrinya", "ts": "Tsonga", "tr": "Turkish",
    "tk": "Turkmen", "ak": "Twi (Akan)", "uk": "Ukrainian", "ur": "Urdu", "ug": "Uyghur", "uz": "Uzbek",
    "vi": "Vietnamese", "cy": "Welsh", "xh": "Xhosa", "yi": "Yiddish", "yo": "Yoruba", "zu": "Zulu",
}


def rpy_live_langs():
    """Языки Google (код, название по-русски, своё название) — тот же список, что в переводе на лету для HTML."""
    block = LIVE_JS[LIVE_JS.index("var GLANGS = ["):]
    block = block[:block.index("]];") + 2]
    return [[c, ru, native, RPY_LANG_EN.get(c, native)]
            for c, ru, native in re.findall(r'\["([\w-]+)", "([^"]+)", "([^"]+)"\]', block)]


def rpy_live_loader():
    """Код для .rpy/.rpyc. Модуль выполняется обычным compile()/exec: в блоках python Ren'Py подменяет
    dict/list/object «откатываемыми» типами (Rollback), а кэш переводов откатываться не должен."""
    rt = RPY_LIVE_RUNTIME.strip("\n") + "\n"
    if "'''" in rt or any(ord(c) > 127 for c in rt):
        raise RuntimeError("RPY_LIVE_RUNTIME: только ASCII и без '''")
    return _ascii_only("import __future__ as _rut_f\n"
            "try:\n"
            "    exec(compile(r'''" + rt + "''', \"rut_live.py\", \"exec\", _rut_f.unicode_literals.compiler_flag"
            " | _rut_f.print_function.compiler_flag | _rut_f.division.compiler_flag"
            " | _rut_f.absolute_import.compiler_flag, True), {\"__name__\": \"rut_live\"})\n"
            "except Exception as _rut_e:  # translation did not start - the game runs as is\n"
            "    import sys as _rut_s\n"
            "    _rut_s.stderr.write(\"[rut] live translation failed: %r\\n\" % (_rut_e,))\n"
            "del _rut_f\n")


def _ascii_only(code):
    """Ren'Py 7 переписывает строки в коде с не-ASCII символами — это ломает модуль; поэтому только ASCII."""
    if any(ord(c) > 127 for c in code):
        raise RuntimeError("код модуля перевода должен быть ASCII")
    return code


def rpy_live_rpy(lang):
    code = rpy_live_loader()
    a = code.index("r'''") + 4
    b = code.rindex("'''")
    head, body, tail = code[:a], code[a:b], code[b:]  # строки модуля (внутри r'''...''') не сдвигаем
    ind = lambda t: "\n".join(("    " + x) if x.strip() else x for x in t.split("\n"))  # noqa: E731
    return (f"# sugarcube_translate: перевод на лету (по умолчанию «{lang}»): текст переводится, когда появляется\n"
            f"# на экране. Кнопка с глобусом в углу (или Alt+L) — язык и настройки, Alt+T — оригинал/перевод.\n"
            f"# Убрать: запустите скрипт с --remove (или удалите {RUT_RPY}.rpy, {RUT_RPY}.rpyc и {RUT_JSON}).\n"
            "init 999 python:\n" + ind(head) + body + tail.split("\n", 1)[0] + "\n"
            + ind(tail.split("\n", 1)[1]).rstrip(" ") )


def rpy_live_entries(tr):
    """Что игра уже просила перевести на лету (и исправления вручную) — это встраиваем в игру."""
    seen = tr.cache.get(LIVE_KEY)
    seen = seen if isinstance(seen, dict) else {}
    out = {k: v for k, v in tr.cache.items() if isinstance(v, str) and k and k[0] not in "\u0001\u0002\u0003"
           and v.strip() and live_hash(k) in seen}
    out.update({k: v for k, v in tr.glossary.items() if isinstance(v, str)})
    return out, [k for k in live_manual(tr) if k in out]


def rpy_static_count(tr):
    """Сколько в кэше обычного (не «на лету») перевода — стоит ли собирать из него словарь."""
    seen = tr.cache.get(LIVE_KEY)
    seen = seen if isinstance(seen, dict) else {}
    return sum(1 for k in tr.cache if k and k[0] not in "\u0001\u0002\u0003" and live_hash(k) not in seen)


def rpy_live_entries_static(g):
    """Тексты игры для словаря «как есть» (из обычного перевода, если он уже делался)."""
    say, ui, st = rpy_collect(g)
    entries = {}
    for s in list(dict.fromkeys(say)) + list(dict.fromkeys(ui)):
        if s.strip() and s not in entries:
            m = rpy_mark(s)
            if m:
                entries[s] = m
    return entries, st


def rpy_live_table(entries, tr, lang):
    table = {k: v for k, v in rpy_builtin(lang).items() if v}
    for s, (k, toks, _pairs) in entries.items():
        r = tr.peek(k)
        if isinstance(r, str) and live_marks_ok(k, r):
            r = rpy_unmark(_rpy_fix_spaces(k, r, toks), toks)
            if r != s:
                table[s] = r
    return table


def rpy_live_write(g, payload, tpl=None):
    """Кладёт в игру модуль перевода на лету и rut_translation.json (готовые переводы, настройки)."""
    pre = g["pre"]
    jpath = os.path.join(g["game"], pre + RUT_JSON)
    tmp = jpath + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, jpath)
    out = [jpath]
    if g["apk"]:
        tpl = tpl or rpy_template(g)
        if tpl is None:
            raise RuntimeError("в игре не нашёлся ни один .rpyc с блоком «init python:» — не по чему собрать модуль")
        path = os.path.join(g["game"], pre + RUT_RPY + ".rpyc")
        with open(path, "wb") as f:
            f.write(rpy_build_rpyc(tpl, rpy_live_loader(), "game/" + RUT_RPY + ".rpy"))
        out.append(path)
    else:
        path = os.path.join(g["game"], RUT_RPY + ".rpy")
        if os.path.exists(path + "c"):
            os.remove(path + "c")  # прошлый наш .rpyc — Ren'Py соберёт заново
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(rpy_live_rpy(payload.get("lang") or "ru"))
        out.append(path)
    return out


def engine_cache_langs(kind, g):
    """Языки, для которых у игры уже есть кэш перевода (rut_cache.<язык>.json)."""
    d, prefix, suffix = engine_cache_parts(kind, g)
    out = []
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return out
    for n in names:
        if n.startswith(prefix) and n.endswith(suffix):
            lang = n[len(prefix):len(n) - len(suffix)]
            if LANG_RE.match(lang):
                out.append(lang)
    return out


def rpy_launch(g, input_path):
    """-c: запускает игру (её .exe / .sh / .app). Возвращает путь или None, если запустить нечего."""
    root = g["root"]
    p = os.path.abspath(input_path)
    try:
        names = sorted(os.listdir(root))
    except OSError:
        names = []
    if sys.platform.startswith("win"):
        cands = ([p] if p.lower().endswith(".exe") else []) + [
            os.path.join(root, n) for n in names if n.lower().endswith(".exe")
            and not re.search(r"(-32|unins\d*|crash\w*|setup|dxweb\w*|vc_?redist\w*)\.exe$", n, re.I)]
        cmd = lambda c: [c]  # noqa: E731
    elif sys.platform == "darwin":
        cands = ([p] if p.endswith(".app") else []) + [os.path.join(root, n) for n in names if n.endswith(".app")]
        cmd = lambda c: ["open", c]  # noqa: E731
    else:
        cands = ([p] if p.endswith(".sh") else []) + [os.path.join(root, n) for n in names if n.endswith(".sh")]
        cmd = lambda c: ["/bin/sh", c]  # noqa: E731
    for c in cands:
        if os.path.exists(c):
            try:
                subprocess.Popen(cmd(c), cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return c
            except OSError as e:
                print(f"  не удалось запустить {c}: {e}", file=sys.stderr)
    return None


def run_renpy_live(args, g, engine, key, glossary):
    """Ren'Py: перевод на лету. -l — модуль в игре сам ходит в Google; -c — через это окно (быстрее,
    переводы копятся в кэше и при выходе встраиваются в игру); -i — добавить переводы, сохранённые в игре."""
    lang = args.dst  # без флага игра сама берёт язык телефона / компьютера, дальше — выбор игрока

    def cache_fn(l):
        return args.cache if args.cache and lang and l.lower() == lang.lower() else engine_cache_path("renpy", g, l)
    pool = LivePool(args, engine, key, glossary, g["root"], cache_fn=cache_fn,
                    langs_fn=lambda: engine_cache_langs("renpy", g))
    kind = "APK (распакованный)" if g["apk"] else "ПК"
    print(f"Ren'Py: {kind}, папка игры: {g['game']} — перевод на лету", file=sys.stderr)
    if args.import_files:
        live_import(pool, args.import_files)
    console = args.console
    if console and g["apk"]:
        print("Это APK: с телефона до окна скрипта на ПК не достучаться, поэтому делаю как -l (игра будет "
              "переводить сама, через Google).", file=sys.stderr)
        console = False
    tpl = None
    if g["apk"]:
        tpl = rpy_template(g)
        if tpl is None:
            raise SystemExit("В APK не нашёлся ни один .rpyc с блоком «init python:» — не по чему собрать модуль.")
    state = {"entries": None}

    def install(server):
        # + русский: официальный перевод интерфейса самого Ren'Py (кнопки, подтверждения) — встраивается всегда
        langs = sorted({x.lower(): x for x in pool.langs() + [lang or "ru"]}.values())
        trs = {l: pool.get(l, quiet=True) for l in langs}
        if state["entries"] is None and any(rpy_static_count(tr) for tr in trs.values()):
            print("Собираю готовый перевод из кэша (игра уже переводилась обычным способом)…", file=sys.stderr)
            state["entries"] = rpy_live_entries_static(g)[0]
        dicts, live, manual, n_dict, n_live = {}, {}, {}, 0, 0
        for l, tr in trs.items():
            table = rpy_live_table(state["entries"] or {}, tr, l)
            if table:
                dicts[l] = table
                n_dict += len(table)
            e, m = rpy_live_entries(tr)
            if e:
                live[l] = e
                n_live += len(e)
            if m:
                manual[l] = m
        payload = {"v": 2, "mode": "live", "src": args.src, "lang": lang or "auto",
                   "cfg": {"server": server, "wait": args.live_wait}, "ui": {"ru": RPY_LIVE_UI},
                   "langs": rpy_live_langs(), "fav": RPY_LIVE_FAV, "icon": RPY_LIVE_ICON, "dicts": dicts, "live": live,
                   "manual": manual, "built": int(time.time())}
        files = rpy_live_write(g, payload, tpl)
        for p in files:
            print(f"  записан: {p}", file=sys.stderr)
        print(f"  встроено готовых переводов: {n_dict + n_live:,}"
              + (f" ({', '.join(l + ' ' + format(len(live.get(l, {})) + len(dicts.get(l, {})), ',') for l in langs)})"
                 if n_dict + n_live else "") + "; новое игра переводит сама и запоминает.", file=sys.stderr)

    keys = ("Язык игра берёт сама — как у телефона / Windows (если это не язык оригинала); выбранный в игре\n"
            "  запоминается." if not lang else f"Язык по умолчанию: {lang}.") + (
            "\n  В игре: в правом верхнем углу кнопка с глобусом (на ПК ещё Alt+L) — язык,\n"
            "  «Перевести заново», «Исправить фразу»; рядом «⟳» — обновить перевод. В «Ещё…» — место кнопки,\n"
            "  рендерер и консоль Ren'Py. Alt+T — оригинал/перевод.")
    if not console:
        install("")
        print("\nГотово: перевод на лету встроен в игру. Запускайте её как обычно"
              + (" (APK соберите и подпишите заново: apktool b + uber-apk-signer)." if g["apk"] else ".")
              + f"\n  {keys}\n"
              "  Новый текст игра переводит через Google сама (нужен интернет) и запоминает — в папке сохранений\n"
              "  игры, файл rut_live.json. Его же можно добавить в игру на ПК (переводы встроятся):\n"
              f"      python sugarcube_translate.py \"{args.input}\" -i rut_live.json\n"
              "  Вернуть оригинал: тот же запуск с --remove.", file=sys.stderr)
        return 0
    if engine in ("free", "google"):
        n_ok = pool.prober.probe()
        if not n_ok:
            print("Сейчас ни один адрес Google не отвечает: уже переведённое игра покажет, новое — пока как есть "
                  "(скрипт будет пробовать снова).", file=sys.stderr)
        pool.prober.workers = max(1, min(n_ok, 6 if args.fast else 4))
    elif args.fast:
        pool.prober.workers = 3
    srv = live_server(pool, None, None, None, args.port)
    port = srv.server_address[1]
    install(f"http://127.0.0.1:{port}/__rut/translate")
    started = None if args.no_browser else rpy_launch(g, args.input)
    print(("\nИгра запущена: " + started if started else "\nЗапустите игру как обычно.")
          + f"\n  Перевод идёт через это окно (127.0.0.1:{port}): быстрее и всё копится в кэше на диске.\n"
          f"  {keys}\n"
          "  Не закрывайте это окно, пока играете. Выход — введите exit и нажмите Enter (или Ctrl+C): всё\n"
          "  переведённое встроится в игру, и дальше она будет переводить и без этого окна.", file=sys.stderr)

    def on_exit():
        try:
            install("")
        except Exception as e:  # noqa: BLE001
            print(f"Не удалось встроить переводы в игру: {e}", file=sys.stderr)
    live_loop(srv, pool, on_exit)
    return 0


# Официальный перевод интерфейса Ren'Py на русский (launcher/game/tl/russian, лицензия MIT)
RPY_RU_BUILTIN = '{"{#weekday}Monday":"{#weekday}Понедельник","{#weekday}Tuesday":"{#weekday}Вторник","{#weekday}Wednesday":"{#weekday}Среда","{#weekday}Thursday":"{#weekday}Четверг","{#weekday}Friday":"{#weekday}Пятница","{#weekday}Saturday":"{#weekday}Суббота","{#weekday}Sunday":"{#weekday}Воскресенье","{#weekday_short}Mon":"{#weekday_short}Пн","{#weekday_short}Tue":"{#weekday_short}Вт","{#weekday_short}Wed":"{#weekday_short}Ср","{#weekday_short}Thu":"{#weekday_short}Чт","{#weekday_short}Fri":"{#weekday_short}Пт","{#weekday_short}Sat":"{#weekday_short}Сб","{#weekday_short}Sun":"{#weekday_short}Вс","{#month}January":"{#month}Января","{#month}February":"{#month}Февраля","{#month}March":"{#month}Марта","{#month}April":"{#month}Апреля","{#month}May":"{#month}Мая","{#month}June":"{#month}Июня","{#month}July":"{#month}Июля","{#month}August":"{#month}Августа","{#month}September":"{#month}Сентября","{#month}October":"{#month}Октября","{#month}November":"{#month}Ноября","{#month}December":"{#month}Декабря","{#month_short}Jan":"{#month_short}Янв","{#month_short}Feb":"{#month_short}Фев","{#month_short}Mar":"{#month_short}Мар","{#month_short}Apr":"{#month_short}Апр","{#month_short}May":"{#month_short}Мая","{#month_short}Jun":"{#month_short}Июн","{#month_short}Jul":"{#month_short}Июл","{#month_short}Aug":"{#month_short}Авг","{#month_short}Sep":"{#month_short}Сен","{#month_short}Oct":"{#month_short}Окт","{#month_short}Nov":"{#month_short}Ноя","{#month_short}Dec":"{#month_short}Дек","%b %d, %H:%M":"%d %b, %H:%M","Save slot %s: [text]":"Слот сохранения %s: [text]","Load slot %s: [text]":"Слот загрузки %s: [text]","Delete slot [text]":"Удалить слот [text]","File page auto":"Автосохранения","File page quick":"Быстрые сохранения","File page [text]":"Страница сохранений [text]","Next file page.":"Следующая страница сохранений","Previous file page.":"Предыдущая страница сохранений","Quick save complete.":"Быстрое сохранение завершено.","Quick save.":"Быстрое сохранение","Quick load.":"Быстрая загрузка","Language [text]":"Язык [text]","Are you sure?":"Вы уверены?","Are you sure you want to delete this save?":"Вы уверены, что хотите удалить это сохранение?","Are you sure you want to overwrite your save?":"Вы уверены, что хотите перезаписать ваше сохранение?","Loading will lose unsaved progress.\\nAre you sure you want to do this?":"Загрузка игры приведёт к потере несохранённого прогресса.\\nВы уверены, что хотите это сделать?","Are you sure you want to quit?":"Вы уверены, что хотите выйти?","Are you sure you want to return to the main menu?\\nThis will lose unsaved progress.":"Вы уверены, что хотите вернуться в главное меню?\\nЭто приведёт к потере несохранённого прогресса.","Are you sure you want to end the replay?":"Вы уверены, что хотите завершить повтор?","Are you sure you want to begin skipping?":"Вы уверены, что хотите начать пропуск?","Are you sure you want to skip to the next choice?":"Вы точно хотите пропустить всё до следующего выбора?","Are you sure you want to skip unseen dialogue to the next choice?":"Вы уверены, что хотите пропустить непрочитанные диалоги до следующего выбора?","Failed to save screenshot as %s.":"Провалена попытка сохранить скриншот как %s.","Saved screenshot as %s.":"Скриншот сохранён как %s.","Self-voicing disabled.":"Синтезатор речи отключён.","Clipboard voicing enabled. ":"Озвучка буфера обмена включена.","Self-voicing enabled. ":"Синтезатор речи включён.","bar":". Полоса настройки","selected":". На данный момент это выбрано","viewport":"порт просмотра","horizontal scroll":". горизонтальная полоса прокрутки","vertical scroll":". вертикальная полоса прокрутки","activate":"элемент активирован","deactivate":"элемент деактивирован","increase":"больше","decrease":"меньше","Skip Mode":"Режим Пропуска","This program contains free software under a number of licenses, including the MIT License and GNU Lesser General Public License. A complete list of software, including links to full source code, can be found {a=https://www.renpy.org/l/license}here{/a}.":"Эта программа содержит свободное и открытое программное обеспечение под несколькими лицензиями, включая лицензию MIT и GNU Lesser General Public. Полный список лицензий, включая ссылки на полный исходный код, можно найти {a=https://www.renpy.org/l/license}здесь{/a}.","display":"режим экрана","transitions":"переходы","skip transitions":"пропускать переходы","video sprites":"видео-спрайты","show empty window":"показывать пустое окно диалога","text speed":"скорость текста","joystick":"джойстик","joystick...":"джойстик...","skip":"пропускать","skip unseen [text]":"пропускать весь [text]","skip unseen text":"пропускать весь текст","begin skipping":"начать пропуск","after choices":"после выборов","skip after choices":"пропускать после выборов","auto-forward time":"скорость авточтения","auto-forward":"авточтение","Auto forward":"Авточтение","auto-forward after click":"продолжать авточтение после клика","automatic move":"автоматически передвигать мышь к кнопке","wait for voice":"ждать голос","voice sustain":"не останавливать голос","self voicing":"озвучка через синтезатор речи","clipboard voicing":"синтез речи из буфера обмена","debug voicing":"режим дебага синтеза речи","emphasize audio":"усилить громкость заранее заданных звуковых каналов за счёт приглушения остальных каналов","rollback side":"сторона отката","gl powersave":"настройка графики. Экономия энергии","gl framerate":"настройка графики. Частота кадров","gl tearing":"настройка графики. Разрывание кадров","music volume":"громкость музыки","sound volume":"громкость звуков","voice volume":"громкость голоса","mute music":"без музыки","mute sound":"без звуков","mute voice":"без голоса","mute all":"режим без звука","Clipboard voicing enabled. Press \'shift+C\' to disable.":"Озвучка буфера обмена включена. Нажмите \'shift+C\', чтобы отключить её.","Self-voicing would say \\"[renpy.display.tts.last]\\". Press \'alt+shift+V\' to disable.":"Синтезатор речи должен сказать \\"[renpy.display.tts.last]\\". Нажмите \'alt+shift+V\', чтобы отключить его.","Self-voicing enabled. Press \'v\' to disable.":"Синтезатор речи включён. Нажмите \'v\', чтобы отключить его.","Empty Slot.":"Пустой слот","Previous":"Назад","Next":"Далее","Joystick Mapping":"Раскладка джойстика","a":"а","q":"б","Font Override":"Переопределение шрифта","Default":"По умолчанию","Text Size Scaling":"Масштабирование размера текста","Reset":"Сбросить","Line Spacing Scaling":"Масштабирование межстрочного интервала","Self-Voicing":"Озвучка через синтезатор речи","Off":"Выключить","Text-to-speech":"Преобразование текста в речь","Clipboard":"Из буфера обмена","font transform":"преобразование шрифта","font size":"размер шрифта","font line spacing":"межстрочный интервал","The options on this menu are intended to improve accessibility. They may not work with all games, and some combinations of options may render the game unplayable. This is not an issue with the game or engine. For the best results when changing fonts, try to keep the text size the same as it originally was.":"Параметры этого меню предназначены для увеличения доступности. Они могут работать не со всеми играми, а некоторые комбинации опций могут сделать игру отображаемой некорректно. Это не проблема с игрой или движком. Для достижения наилучших результатов при изменении шрифтов старайтесь сохранять размер текста таким, каким он был изначально.","Self-Voicing Volume Drop":"Уменьшение громкости при озвучке через синтезатор речи","self voicing volume drop":"уменьшение громкости при озвучке через синтезатор речи","system cursor":"системный курсор","High Contrast Text":"Высококонтрастный текст","renderer menu":"меню рендерера","accessibility menu":"меню специальных возможностей","high contrast text":"высококонтрастный текст","audio when minimized":"звук при сворачивании окна","main volume":"общая громкость","mute main":"режим без звука","Accessibility Menu. Use up and down arrows to navigate, and enter to activate buttons and bars.":"Меню специальных возможностей. Для навигации используйте стрелки вверх и вниз, а для активации кнопок и полос - клавишу Enter.","Are you sure you want to continue where you left off?":"Вы уверены, что хотите продолжить с того места, на котором остановились?","self voicing enable":"включить авто озвучивание","self voicing disable":"отключить авто озвучивание","clipboard voicing enable":"включить озвучивание буфера обмена","clipboard voicing disable":"отключить озвучивание буфера обмена","debug voicing enable":"включить дебаг озвучивания","debug voicing disable":"отключить дебаг озвучивания","restore window position":"восстановить положение окна","reset":"сбросить","(clear retained bubbles)":"(очистить сохранившиеся пузыри)","Back":"Назад","History":"История","Skip":"Пропуск","Auto":"Авто","Save":"Сохранить","Q.Save":"Б.Сохр","Q.Load":"Б.Загр","Prefs":"Опции","Start":"Начать","Load":"Загрузить","Preferences":"Настройки","End Replay":"Завершить повтор","Main Menu":"Главное меню","About":"Об игре","Help":"Помощь","Quit":"Выход","Return":"Вернуться","Version [config.version!t]\\n":"Версия [config.version!t]\\n","Made with {a=https://www.renpy.org/}Ren\'Py{/a} [renpy.version_only].\\n\\n[renpy.license!t]":"Сделано с помощью {a=https://www.renpy.org/}Ren\'Py{/a} [renpy.version_only].\\n\\n[renpy.license!t]","Page {}":"{} страница","Automatic saves":"Автосохранения","Quick saves":"Быстрые сохранения","{#file_time}%A, %B %d %Y, %H:%M":"{#file_time}%A, %d %B %Y, %H:%M","empty slot":"Пустой слот","{#auto_page}A":"{#auto_page}А","{#quick_page}Q":"{#quick_page}Б","Display":"Режим экрана","Window":"Оконный","Fullscreen":"Полный","Rollback Side":"Сторона отката","Disable":"Отключено","Left":"Левая","Right":"Правая","Unseen Text":"Всего текста","After Choices":"После выборов","Transitions":"Переходов","Text Speed":"Скорость текста","Auto-Forward Time":"Скорость авточтения","Music Volume":"Громкость музыки","Sound Volume":"Громкость звуков","Test":"Тест","Voice Volume":"Громкость голоса","Mute All":"Без звука","The dialogue history is empty.":"История диалогов пуста.","Keyboard":"Клавиатура","Mouse":"Мышь","Gamepad":"Геймпад","Advances dialogue and activates the interface.":"Прохождение диалогов, активация интерфейса.","Space":"Пробел","Advances dialogue without selecting choices.":"Прохождение диалогов без возможности делать выбор.","Arrow Keys":"Стрелки","Navigate the interface.":"Навигация по интерфейсу.","Escape":"Esc","Accesses the game menu.":"Вход в игровое меню.","Skips dialogue while held down.":"Пропускает диалоги, пока зажат.","Toggles dialogue skipping.":"Включает режим пропуска.","Rolls back to earlier dialogue.":"Откат назад по сюжету игры.","Rolls forward to later dialogue.":"Откатывает предыдущее действие вперёд.","Hides the user interface.":"Скрывает интерфейс пользователя.","Takes a screenshot.":"Делает снимок экрана.","Toggles assistive {a=https://www.renpy.org/l/voicing}self-voicing{/a}.":"Включает поддерживаемый {a=https://www.renpy.org/l/voicing}синтезатор речи{/a}.","Left Click":"Левый клик","Middle Click":"Клик колёсиком","Right Click":"Правый клик","Mouse Wheel Up":"Колёсико вверх","Mouse Wheel Down":"Колёсико вниз","Right Trigger\\nA/Bottom Button":"Правый триггер\\nA/Нижняя кнопка","Left Trigger\\nLeft Shoulder":"Левый Триггер\\nЛевый Бампер","Right Shoulder":"Правый бампер","D-Pad, Sticks":"Крестовина, Стики","Y/Top Button":"Y/Верхняя кнопка","Calibrate":"Калибровка","Yes":"Да","No":"Нет","Skipping":"Пропускаю","Menu":"Меню","Opens the accessibility menu.":"Открывает меню специальных возможностей.","Upload Sync":"Загрузить Sync","Download Sync":"Скачать Sync","Start, Guide, B/Right Button":"Старт, Гид, B/Правая кнопка"}'


def rpy_builtin(lang):
    """Интерфейс самого Ren'Py (подтверждения, даты, кнопки по умолчанию): {английский: перевод или None}.
    Для русского — официальный перевод Ren'Py, для других языков — переводим машинно."""
    if not RPY_RU_BUILTIN:
        return {}
    ru = json.loads(RPY_RU_BUILTIN)
    if lang.lower().split("-")[0] == "ru":
        return ru
    return {k: None for k in ru}


def run_renpy(args, g, tr, lang):
    """Ren'Py целиком: собрать тексты → перевести → положить словарь и модуль в игру."""
    t0 = time.time()
    kind = "APK (распакованный)" if g["apk"] else "ПК"
    print(f"Ren'Py: {kind}, папка игры: {g['game']}", file=sys.stderr)
    say, ui, st = rpy_collect(g)
    print(f"  сценариев: .rpyc {st['rpyc']}, .rpy {st['rpy']}" +
          (f"; не прочитались: {', '.join(st['bad'][:5])}" if st["bad"] else ""), file=sys.stderr)
    common = rpy_builtin(lang)
    builtin = {k: v for k, v in common.items() if v}
    say_u = list(dict.fromkeys(s for s in say if s.strip()))
    ui_u = [s for s in dict.fromkeys(s for s in ui if s.strip()) if s not in set(say_u)]
    entries = {}
    for s in say_u + ui_u + [k for k in common if k not in set(say_u) | set(ui_u)]:
        if s in builtin or s in entries:
            continue
        m = rpy_mark(s)
        if m:
            entries[s] = m
    chars = sum(len(m[0]) for m in entries.values())
    print(f"  реплик и пунктов меню: {len(say_u):,}, подписей интерфейса: {len(ui_u):,}; "
          f"к переводу {len(entries):,} фраз ({chars:,} симв.)", file=sys.stderr)
    if args.dry_run:
        return 0
    items = [(m[0], {"p": m[2]} if m[2] else None) for m in entries.values()]
    if items:
        translate_marked(tr, items)
    table, broken, missing = dict(builtin), 0, 0
    for s, (k, toks, _pairs) in entries.items():
        r = tr.peek(k)
        if not isinstance(r, str):
            missing += 1
            continue
        if not live_marks_ok(k, r):
            broken += 1
            continue
        r = rpy_unmark(_rpy_fix_spaces(k, r, toks), toks)
        if r != s:
            table[s] = r
    if tr.offline:
        print(f"Перевод остановлен: {tr.stop_reason}. Кладу в игру то, что готово; запустите ту же команду "
              f"позже — продолжится с этого места.", file=sys.stderr)
    files = rpy_write(g, table, lang)
    for p in files:
        print(f"  записан: {p}", file=sys.stderr)
    print(f"Готово за {(time.time() - t0) / 60:.1f} мин: переведено {len(table):,} фраз" +
          (f", не перевелось {missing:,} (лимит/сеть — запустите ещё раз, продолжит)" if missing else "") +
          (f", {broken:,} оставлены на английском (переводчик испортил теги)" if broken else ""), file=sys.stderr)
    if g["apk"]:
        print("  Это APK: соберите и подпишите его заново (apktool b + apksigner/uber-apk-signer).", file=sys.stderr)
    print("  В игре: Alt+T — показать оригинал/перевод. Вернуть оригинал навсегда: --remove", file=sys.stderr)
    return 0


# ===========================================================================
# Godot 4: перевод через TranslationServer — словарь + автозагрузка (сцены и скрипты игры не меняются)
# ===========================================================================

GD_MAGIC = 0x43504447  # "GDPC"
GD_DIR_ENCRYPTED, GD_REL_FILEBASE, GD_SPARSE = 1, 2, 4
GD_FILE_ENCRYPTED, GD_FILE_REMOVAL = 1, 2
GD_DIR = "rut_translate"
GD_AUTOLOAD = "RutTranslate"


class GdPack:
    """Архив .pck Godot 4 (форматы 2–4): отдельный файл, встроенный в .exe/.x86_64 или «sparse» из APK."""

    def __init__(self, path):
        self.path, self.files, self.order = path, {}, []
        self.start = 0          # где начинается пак (в .exe — не 0)
        self.embedded = False
        with open(path, "rb") as f:
            size = f.seek(0, 2)
            f.seek(0)
            if _struct.unpack("<I", f.read(4))[0] == GD_MAGIC:
                self.start = 0
            else:
                if size < 16:
                    raise ValueError("не .pck")
                f.seek(size - 4)
                if _struct.unpack("<I", f.read(4))[0] != GD_MAGIC:
                    raise ValueError("не .pck Godot")
                f.seek(size - 12)
                ds = _struct.unpack("<Q", f.read(8))[0]
                self.start = size - 12 - ds
                f.seek(self.start)
                if self.start < 0 or _struct.unpack("<I", f.read(4))[0] != GD_MAGIC:
                    raise ValueError("не .pck Godot")
                self.embedded = True
            self.version, self.major, self.minor, self.patch, self.flags = _struct.unpack("<5I", f.read(20))
            if self.version not in (2, 3, 4):
                raise ValueError(f"формат .pck {self.version} не поддерживается (это Godot 3 или старше?)")
            if self.flags & GD_DIR_ENCRYPTED:
                raise ValueError("список файлов в .pck зашифрован ключом игры — перевести нельзя")
            fb = _struct.unpack("<Q", f.read(8))[0]
            if self.version >= 3 or self.flags & GD_REL_FILEBASE:
                fb += self.start
            self.file_base = fb
            if self.version >= 3:
                f.seek(_struct.unpack("<Q", f.read(8))[0] + self.start)
            else:
                f.read(64)
            n = _struct.unpack("<I", f.read(4))[0]
            self.prefix = None
            for _ in range(n):
                sl = _struct.unpack("<I", f.read(4))[0]
                p = f.read(sl).rstrip(b"\0").decode("utf-8", "replace")
                ofs, sz = _struct.unpack("<QQ", f.read(16))
                md5 = f.read(16)
                fl = _struct.unpack("<I", f.read(4))[0]
                if self.prefix is None:
                    self.prefix = "res://" if p.startswith("res://") else ""
                key = p if p.startswith("res://") else "res://" + p
                self.files[key] = (ofs, sz, md5, fl)
                self.order.append(key)
        self.sparse = bool(self.flags & GD_SPARSE)
        self.base_dir = os.path.dirname(path)

    def read(self, res):
        ofs, sz, _md5, fl = self.files[res]
        if fl & (GD_FILE_ENCRYPTED | GD_FILE_REMOVAL):
            return None
        if self.sparse:
            p = os.path.join(self.base_dir, *res[6:].split("/"))
            if not os.path.exists(p):
                return None
            with open(p, "rb") as f:
                return f.read()
        with open(self.path, "rb") as f:
            f.seek(self.file_base + ofs)
            return f.read(sz)

    def names(self):
        return [k for k in self.order if not self.files[k][3] & GD_FILE_REMOVAL]

    def _entry(self, res):
        p = res if self.prefix == "res://" else res[6:]
        b = p.encode("utf-8")
        return _struct.pack("<I", len(b) + (-len(b)) % 4) + b + b"\0" * ((-len(b)) % 4)

    def write(self, out, add):
        """Новый пак = старые файлы как есть + add {res://путь: байты}. Встроенный в .exe — пишется в .exe."""
        tmp = out + ".rut-tmp"
        entries = [(k, self.files[k]) for k in self.order if k not in add]
        if self.sparse:  # данные лежат рядом отдельными файлами — дописываем их, пак — только список
            for res, data in add.items():
                p = os.path.join(self.base_dir, *res[6:].split("/"))
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "wb") as f:
                    f.write(data)
        data_end = 0
        for _k, (ofs, sz, _m, fl) in entries:
            if not self.sparse and not fl & GD_FILE_REMOVAL:
                data_end = max(data_end, ofs + sz)
        data_end += (-data_end) % 16
        new, pos = [], data_end
        for res, data in add.items():
            new.append((res, (0 if self.sparse else pos, len(data), _hashlib.md5(data).digest(), 0)))
            if not self.sparse:
                pos += len(data) + (-len(data)) % 16
        allent = entries + new
        directory = _struct.pack("<I", len(allent)) + b"".join(
            self._entry(k) + _struct.pack("<QQ", v[0], v[1]) + v[2] + _struct.pack("<I", v[3]) for k, v in allent)
        flags = self.flags & ~GD_DIR_ENCRYPTED
        with open(self.path, "rb") as src, open(tmp, "wb") as dst:
            if self.embedded:  # всё до пака (сама программа) — без изменений
                left = self.start
                while left:
                    chunk = src.read(min(left, 1 << 20))
                    dst.write(chunk)
                    left -= len(chunk)
            start = dst.tell()
            head = _struct.pack("<6I", GD_MAGIC, self.version, self.major, self.minor, self.patch, flags)
            dst.write(head)
            fb_pos = dst.tell()
            dst.write(b"\0" * 8)
            if self.version >= 3:
                dir_pos = dst.tell()
                dst.write(b"\0" * 8 + b"\0" * 64)
            else:
                dst.write(b"\0" * 64)
                dst.write(directory)
            dst.write(b"\0" * ((-(dst.tell() - start)) % 16))
            fb = dst.tell()
            if not self.sparse:
                src.seek(self.file_base)
                left = data_end
                while left:
                    chunk = src.read(min(left, 1 << 20))
                    if not chunk:
                        dst.write(b"\0" * left)
                        break
                    dst.write(chunk)
                    left -= len(chunk)
                for res, data in add.items():
                    dst.write(data)
                    dst.write(b"\0" * ((-len(data)) % 16))
            if self.version >= 3:
                dst.write(b"\0" * ((-(dst.tell() - start)) % 16))
                dpos = dst.tell()
                dst.write(directory)
                dst.seek(dir_pos)
                dst.write(_struct.pack("<Q", dpos - start))
                dst.seek(0, 2)
            rel = self.version >= 3 or flags & GD_REL_FILEBASE
            dst.seek(fb_pos)
            dst.write(_struct.pack("<Q", fb - start if rel else fb))
            dst.seek(0, 2)
            if self.embedded:
                dst.write(b"\0" * ((dst.tell() - start + 12) % 8))
                dst.write(_struct.pack("<QI", dst.tell() - start, GD_MAGIC))
        os.replace(tmp, out)


class GdDir:
    """Распакованные файлы Godot (APK: папка assets) — те же операции, что у пака."""

    def __init__(self, root):
        self.path, self.root, self.files = root, root, {}
        for dirpath, dirs, files in os.walk(root):
            for fn in files:
                rel = os.path.relpath(os.path.join(dirpath, fn), root).replace(os.sep, "/")
                self.files["res://" + rel] = None

    def names(self):
        return sorted(self.files)

    def read(self, res):
        with open(os.path.join(self.root, *res[6:].split("/")), "rb") as f:
            return f.read()


# ---------------------------------------------------------------------------
# Ресурсы Godot: двоичные (RSRC/RSCC) и текстовые (.tscn/.tres)
# ---------------------------------------------------------------------------

class _GdRd:
    def __init__(self, data, pos=0):
        self.d, self.p, self.real64, self.big = data, pos, False, False

    def _u(self, fmt, n):
        v = _struct.unpack_from((">" if self.big else "<") + fmt, self.d, self.p)
        self.p += n
        return v

    def u32(self):
        return self._u("I", 4)[0]

    def i32(self):
        return self._u("i", 4)[0]

    def u64(self):
        return self._u("Q", 8)[0]

    def real(self, n=1):
        return self._u(("d" if self.real64 else "f") * n, (8 if self.real64 else 4) * n)

    def skip(self, n):
        self.p += n

    def ustr(self):
        n = self.u32()
        s = self.d[self.p:self.p + n]
        self.p += n
        return s.split(b"\0", 1)[0].decode("utf-8", "replace")


class GdRef:
    def __init__(self, kind, idx):
        self.kind, self.idx = kind, idx


def _gd_parse_variant(r, fmt=6):
    t = r.u32()
    if t == 1:
        return None
    if t in (2, 3):
        return r.i32()
    if t == 40:
        return r.u64()
    if t == 4:
        return r.real()[0]
    if t == 41:
        return r._u("d", 8)[0]
    if t in (5, 44):
        return r.ustr()
    reals = {10: 2, 11: 4, 12: 3, 13: 4, 14: 4, 15: 6, 16: 9, 17: 12, 18: 6, 50: 4, 52: 16}
    if t in reals:
        return r.real(reals[t])
    ints = {45: 2, 46: 4, 47: 3, 51: 4}
    if t in ints:
        r.skip(4 * ints[t])
        return None
    if t == 20:
        r.skip(16)
        return None
    if t == 22:  # NodePath
        nn = r._u("H", 2)[0]
        ns = r._u("H", 2)[0] & 0x7FFF
        if fmt < 3:
            ns += 1
        for _ in range(nn + ns):
            sid = r.u32()
            if sid & 0x80000000:
                r.skip(sid & 0x7FFFFFFF)
        return None
    if t == 23:
        r.skip(4)
        return None
    if t == 24:
        k = r.u32()
        if k == 0:
            return None
        if k == 2:
            return GdRef("int", r.u32())
        if k == 1:
            r.ustr()
            return GdRef("ext", r.ustr())
        if k == 3:
            return GdRef("ext", r.u32())
        raise ValueError("объект")
    if t in (42, 43):
        return None
    if t == 26:
        n = r.u32() & 0x7FFFFFFF
        out = {}
        for _ in range(n):
            k = _gd_parse_variant(r, fmt)
            v = _gd_parse_variant(r, fmt)
            try:
                out[k] = v
            except TypeError:
                out[repr(k)] = v
        return out
    if t == 30:
        n = r.u32() & 0x7FFFFFFF
        return [_gd_parse_variant(r, fmt) for _ in range(n)]
    if t == 31:
        n = r.u32()
        v = r.d[r.p:r.p + n]
        r.skip(n + (-n) % 4)
        return bytes(v)
    if t == 32:
        n = r.u32()
        return list(r._u(f"{n}i", 4 * n))
    if t in (48, 49):
        n = r.u32()
        r.skip(8 * n)
        return None
    if t == 33:
        n = r.u32()
        r.skip(4 * n)
        return None
    if t == 34:
        n = r.u32()
        return [r.ustr() for _ in range(n)]
    if t in (35, 37, 53):
        n = r.u32()
        r.skip(n * {35: 3, 37: 2, 53: 4}[t] * (8 if r.real64 else 4))
        return None
    if t == 36:
        n = r.u32()
        r.skip(16 * n)
        return None
    raise ValueError(f"тип {t}")


def _gd_fastlz(src, out_size):
    level = (src[0] >> 5) + 1
    ip, op, n = 1, bytearray(), len(src)
    ctrl = src[0] & 31
    while True:
        if ctrl >= 32:
            ln = (ctrl >> 5) - 1
            ofs = (ctrl & 31) << 8
            ref = len(op) - ofs - 1
            if ln == 6:
                if level == 1:
                    ln += src[ip]
                    ip += 1
                else:
                    while True:
                        code = src[ip]
                        ip += 1
                        ln += code
                        if code != 255:
                            break
            code = src[ip]
            ip += 1
            ref -= code
            ln += 3
            if level == 2 and code == 255 and ofs == (31 << 8):
                ofs = (src[ip] << 8) + src[ip + 1]
                ip += 2
                ref = len(op) - ofs - 8191 - 1
            for k in range(ln):
                op.append(op[ref + k])
        else:
            ctrl += 1
            op += src[ip:ip + ctrl]
            ip += ctrl
        if (ip > n - 2) if level == 1 else (ip >= n):
            break
        ctrl = src[ip]
        ip += 1
    return bytes(op[:out_size])


def _gd_zstd(data, size):
    try:
        import zstandard
        return zstandard.ZstdDecompressor().decompress(data, max_output_size=size)
    except ImportError:
        pass
    try:
        from compression import zstd  # Python 3.14+
        return zstd.decompress(data)
    except ImportError:
        pass
    try:
        import pyzstd
        return pyzstd.decompress(data)
    except ImportError:
        raise RuntimeError("zstd")


def _gd_decompress(mode, data, size):
    if mode == 0:
        return _gd_fastlz(data, size) if size >= 16 else data[:size]
    if mode in (1, 3):
        return _zlib.decompress(data, 15 if mode == 1 else 31)
    if mode == 2:
        return _gd_zstd(data, size)
    raise RuntimeError(f"сжатие {mode}")


def gd_uncompress_res(data):
    """RSCC (сжатый ресурс) → RSRC."""
    r = _GdRd(data, 4)
    mode, bsize, total = r.u32(), r.u32(), r.u32()
    bc = total // bsize + 1
    sizes = [r.u32() for _ in range(bc)]
    out, pos = bytearray(), r.p
    for cs in sizes:
        want = min(bsize, total - len(out))
        if want <= 0:
            break
        out += _gd_decompress(mode, data[pos:pos + cs], want)
        pos += cs
    return b"RSRC" + bytes(out[4:]) if out[:4] == b"RSRC" else bytes(out)


def gd_read_binary_res(data):
    """Двоичный ресурс → {"type", "res": [(тип, {свойство: значение})], "ext": [путь...]}."""
    if data[:4] == b"RSCC":
        data = gd_uncompress_res(data)
        if data[:4] != b"RSRC":
            data = b"RSRC" + data
    if data[:4] != b"RSRC":
        raise ValueError("не RSRC")
    r = _GdRd(data, 4)
    r.big = bool(r.u32())
    r.u32()  # use_real64 — в Godot 4 не используется, смотрим флаг ниже
    r.skip(8)  # версия движка
    fmt = r.u32()
    rtype = r.ustr()
    r.u64()
    flags = r.u32()
    r.u64()
    if flags & 8:  # имя класса скрипта
        r.ustr()
    r.real64 = bool(flags & 4)
    r.skip(4 * 11)
    strings = [r.ustr() for _ in range(r.u32())]
    ext = []
    for _ in range(r.u32()):
        r.ustr()
        ext.append(r.ustr())
        if flags & 2:
            r.u64()
    ints = []
    for _ in range(r.u32()):
        path = r.ustr()
        ints.append((path, r.u64()))
    res = []
    for _path, ofs in ints:
        rr = _GdRd(data, ofs)
        rr.big, rr.real64 = r.big, r.real64
        try:
            t = rr.ustr()
            props = {}
            for _ in range(rr.u32()):
                sid = rr.u32()
                if sid & 0x80000000:
                    n = sid & 0x7FFFFFFF
                    name = rr.d[rr.p:rr.p + n].split(b"\0", 1)[0].decode("utf-8", "replace")
                    rr.skip(n)
                else:
                    name = strings[sid] if sid < len(strings) else f"#{sid}"
                props[name] = _gd_parse_variant(rr, fmt)
            res.append((t, props))
        except (ValueError, IndexError, _struct.error):
            continue  # сломанный/неизвестный кусок — остальное читаем
    return {"type": rtype, "res": res, "ext": ext}


_GD_TXT_STR = re.compile(r'(&|\^)?"((?:[^"\\]|\\[\s\S])*)"')


def _gd_unescape(s):
    def rep(m):
        c = m.group(1)
        if c[0] in "uU":
            return chr(int(c[1:], 16))
        return {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "a": "\a"}.get(c, c)
    return re.sub(r"\\(u[0-9a-fA-F]{4}|U[0-9a-fA-F]{6}|.)", rep, s, flags=re.S)


def gd_read_text_res(text):
    """Текстовый ресурс (.tscn/.tres) → [(тип узла/ресурса, свойство, строка)]."""
    out, cur = [], ""
    n = len(text)
    sect = re.compile(r"^\[(\w+)([^\]\n]*)\]\s*$", re.M)
    prop = re.compile(r"^([\w/\-:.@\[\]]+)\s*=\s*", re.M)
    pos = 0
    while pos < n:
        ms, mp = sect.search(text, pos), prop.search(text, pos)
        if not mp and not ms:
            break
        if ms and (not mp or ms.start() < mp.start()):
            attrs = ms.group(2)
            t = re.search(r'\btype="([^"]*)"', attrs)
            cur = t.group(1) if t else ms.group(1)
            pos = ms.end()
            continue
        # значение свойства: до конца строки, но строки "..." и скобки могут занимать несколько строк
        j, depth, k = mp.end(), 0, mp.end()
        while k < n:
            c = text[k]
            if c == '"':
                m = _GD_TXT_STR.match(text, k)
                k = m.end() if m else k + 1
                continue
            if c in "[{(":
                depth += 1
            elif c in "]})":
                depth -= 1
            elif c == "\n" and depth <= 0:
                break
            k += 1
        value = text[j:k]
        name = mp.group(1)
        for m in _GD_TXT_STR.finditer(value):
            if m.group(1):
                continue  # &"имя" и ^"путь" — не текст
            before = value[:m.start()].rstrip()
            if re.search(r"(?:ExtResource|SubResource|NodePath|Resource|preload|load)\(\s*$", before):
                continue
            out.append((cur, name, _gd_unescape(m.group(2)), m.start() == 0 and m.end() == len(value.rstrip())))
        pos = k
    return out


# ---------------------------------------------------------------------------
# Что из ресурсов и скриптов — текст для игрока
# ---------------------------------------------------------------------------

GD_TEXT_PROPS = set(("text tooltip_text placeholder_text title dialog_text ok_button_text cancel_button_text "
                     "description hint_tooltip bbcode_text window_title button_text label caption subtitle "
                     "display_name hint message").split())
GD_SKIP_PROPS = set(("name script unique_name_in_owner animation current_animation autoplay assigned_animation bus "
                     "theme_type_variation path file resource_path resource_name scene_file_path editor_description "
                     "material shader code process_mode action group groups layer mask audio_bus_name "
                     "icon_name font_name locale language font_feature features shader_parameter "
                     "_bundled tracks/ uniform_name parameter_name expression method signal property").split())


def gd_prop_ok(name, s, exact=True):
    """Строка-значение свойства — текст для перевода?"""
    base = name.rsplit("/", 1)[-1]
    if base in GD_SKIP_PROPS or name.startswith(("tracks/", "metadata/_", "shader_parameter/", "theme_override_")):
        return False
    if base in GD_TEXT_PROPS or re.fullmatch(r"(?:popup/)?item_\d+/text|tab_\d+/title|item_\d+/tooltip", name):
        return gd_has_words(s)
    return rpy_prose(s) and not gd_codey(s)


def gd_has_words(s):
    plain = re.sub(r"\[[^\[\]]*\]|\{[^{}]*\}|%[-+#0]*\d*(?:\.\d+)?[a-zA-Z%]", " ", s)
    return bool(re.search(r"[^\W\d_]{2}|[^\W\d_\x00-\u024f]", plain))


def gd_codey(s):
    return bool(re.match(r"^(?:res|user|uid)://", s) or re.search(r"\.(?:tscn|tres|scn|res|gd|gdc|gdshader|"
                                                                    r"import|translation)\b", s))


def gd_walk(v, prop, out):
    if isinstance(v, str):
        if gd_prop_ok(prop, v):
            out.append(v)
    elif isinstance(v, dict):
        for k, x in v.items():
            gd_walk(x, (str(k) if isinstance(k, str) else prop), out)
    elif isinstance(v, (list, tuple)):
        for x in v:
            gd_walk(x, prop, out)


def gd_scene_strings(bundled, out):
    """Сцена (PackedScene._bundled): свойства узлов — по именам («text», «tooltip_text»...)."""
    names, variants, nodes = bundled.get("names") or [], bundled.get("variants") or [], bundled.get("nodes") or []
    used = set()
    try:
        idx = 0
        for _ in range(int(bundled.get("node_count") or 0)):
            idx += 5
            for _j in range(nodes[idx]):
                pname = names[nodes[idx + 1] & ((1 << 30) - 1)]
                vi = nodes[idx + 2]
                if 0 <= vi < len(variants):
                    used.add(vi)
                    gd_walk(variants[vi], pname, out)
                idx += 2
            idx += 1
            idx += nodes[idx] + 1
    except (IndexError, TypeError):
        pass
    for i, v in enumerate(variants):  # значения, которые встретились не как свойство узла
        if i not in used and isinstance(v, (list, dict, str)):
            gd_walk(v, "", out)


def gd_gdc_constants(data):
    """Двоичный скрипт .gdc (Godot 4.3+): строки-константы."""
    if data[:4] != b"GDSC":
        return []
    ver, dsize = _struct.unpack_from("<II", data, 4)
    body = data[12:] if dsize == 0 else _gd_zstd(data[12:], dsize)
    r = _GdRd(body)
    nid, ncon = r.u32(), r.u32()
    r.p = 20 if ver <= 100 else 16
    for _ in range(nid):
        r.skip(4 * r.u32())
    out = []
    for _ in range(ncon):
        try:
            v = _gd_marshal(r)
        except (ValueError, _struct.error, IndexError):
            break
        if isinstance(v, str):
            out.append(v)
    return out


def _gd_marshal(r):
    """Variant в формате marshalls (encode_variant)."""
    h = r.u32()
    t, f64 = h & 0xFF, bool(h & (1 << 16))
    rl = 8 if f64 else 4
    if t == 0:
        return None
    if t == 1:
        r.skip(4)
        return None
    if t == 2 or t == 3:
        r.skip(8 if f64 else 4)
        return None
    if t in (4, 21):
        n = r.u32()
        s = r.d[r.p:r.p + n].decode("utf-8", "replace")
        r.skip(n + (-n) % 4)
        return s if t == 4 else None
    sizes = {5: 2 * rl, 6: 8, 7: 4 * rl, 8: 16, 9: 3 * rl, 10: 12, 11: 6 * rl, 12: 4 * rl, 13: 16, 14: 4 * rl,
             15: 4 * rl, 16: 6 * rl, 17: 9 * rl, 18: 12 * rl, 19: 16 * rl, 20: 16, 23: 8}
    if t in sizes:
        r.skip(sizes[t])
        return None
    if t == 22:
        n = r.u32()
        if not n & 0x80000000:
            raise ValueError("nodepath")
        cnt = (n & 0x7FFFFFFF) + r.u32()
        fl = r.u32()
        cnt += 1 if fl & 2 else 0
        for _ in range(cnt):
            k = r.u32()
            r.skip(k + (-k) % 4)
        return None
    raise ValueError(f"marshal {t}")


# GDScript (.gd): строки по вызовам, как в Python
GD_TEXT_CALLS = set(("tr atr tr_n atr_n set_text add_item add_check_item add_radio_check_item add_icon_item "
                     "set_item_text set_item_tooltip add_tab set_tab_title append_text add_text set_tooltip_text "
                     "set_placeholder set_title add_button add_cancel_button alert show_message show_dialog "
                     "say notify toast popup_message set_dialog_text push_notification").split())
GD_CODE_CALLS = set(("get_node get_node_or_null has_node find_child find_children load preload change_scene_to_file "
                     "emit_signal connect disconnect is_connected has_signal has_method call call_deferred callv get "
                     "set has get_meta set_meta has_meta remove_meta is_action_pressed is_action_just_pressed "
                     "is_action_just_released is_action_released get_action_strength get_axis get_vector "
                     "action_press action_release play play_backwards queue travel start add_to_group "
                     "remove_from_group is_in_group get_nodes_in_group get_first_node_in_group call_group "
                     "notify_group set_group print prints printt printerr printraw print_debug print_rich "
                     "push_error push_warning assert get_setting set_setting has_setting open open_compressed "
                     "file_exists dir_exists get_file_as_string get_file_as_bytes make_dir make_dir_recursive "
                     "remove rename copy load_resource_pack save get_environment set_environment has_feature "
                     "compile search search_all sub set_shader_parameter get_shader_parameter tween_property "
                     "tween_method tween_callback get_bus_index set_bus_volume_db set_bus_mute "
                     "get_animation has_animation add_animation set_animation get_parameter set_parameter "
                     "get_theme_color get_theme_constant get_theme_font get_theme_font_size get_theme_icon "
                     "get_theme_stylebox has_theme_color add_theme_color_override add_theme_constant_override "
                     "add_theme_font_override add_theme_font_size_override add_theme_icon_override "
                     "add_theme_stylebox_override get_singleton has_singleton str_to_var instantiate "
                     "can_instantiate class_exists is_class get_class set_script property_get_revert "
                     "request http_request get_value set_value has_section has_section_key erase_section "
                     "get_section_keys parse_string Color Color8 html StringName NodePath "
                     "ResourceLoader.load ResourceLoader.exists FileAccess.open DirAccess.open").split())


_GD_STRING = re.compile(r'(&|\^|r)?("""(?:\\.|(?!""")[\s\S])*"""|\'\'\'(?:\\.|(?!\'\'\')[\s\S])*\'\'\'|'
                        r'"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\')')


def gd_script_strings(src, out):
    """Строки в тексте .gd: текст в tr(), .text = "...", add_item(...) — всегда; остальное — если похоже на фразы."""
    # убираем комментарии, не трогая строки
    i, n, clean = 0, len(src), []
    while i < n:
        c = src[i]
        if c in "\"'" or (c in "&^r" and i + 1 < n and src[i + 1] in "\"'"):
            m = _GD_STRING.match(src, i)
            if m:
                clean.append(m.group(0))
                i = m.end()
                continue
        if c == "#":
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        clean.append(c)
        i += 1
    code = "".join(clean)
    stack = []
    last = 0
    for m in _GD_STRING.finditer(code):
        seg = code[last:m.start()]
        for ch in re.finditer(r"([A-Za-z_][\w.]*)?\s*([(\[{])|([)\]}])|,", seg):
            if ch.group(2):
                stack.append([ch.group(1) or "", 0])
            elif ch.group(3):
                if stack:
                    stack.pop()
            elif stack:
                stack[-1][1] += 1
        last = m.end()
        if m.group(1) in ("&", "^"):
            continue
        body = m.group(2)
        q = 3 if body[:3] in ('"""', "'''") else 1
        raw = body[q:-q]
        v = raw if m.group(1) == "r" else _gd_unescape(raw)
        before = code[max(0, m.start() - 80):m.start()]
        call = stack[-1][0].rsplit(".", 1)[-1] if stack else ""
        argn = stack[-1][1] if stack else 0
        if re.search(r"\.(?:text|tooltip_text|placeholder_text|title|dialog_text|bbcode_text|description)\s*[+]?=\s*$",
                     before) or re.search(r"\b(?:text|title|tooltip|message|caption|label|dialog|line|desc)\w*\s*[:=]\s*$",
                                         before, re.I):
            ok = gd_has_words(v)
        elif call in GD_TEXT_CALLS or stack and stack[-1][0] in GD_TEXT_CALLS:
            ok = gd_has_words(v) and (argn == 0 or rpy_prose(v))
        elif call in GD_CODE_CALLS or stack and stack[-1][0] in GD_CODE_CALLS or re.search(r"\$\s*$|%\s*$", before):
            ok = False
        elif re.search(r"(?:==|!=|\bin|\bmatch|\bcase)\s*$", before) or re.search(r"[\w)\]]\s*\[\s*$", before):
            ok = False  # сравнения и ключи словарей
        else:
            ok = rpy_prose(v) and not gd_codey(v)
        if ok and v.strip():
            out.append(v)


def gd_json_strings(v, out, key=""):
    if isinstance(v, str):
        k = key.lower()
        if v.startswith("^") and len(v) > 2:  # Ink (.ink.json): «^Текст»
            v = v[1:]
        if re.search(r"(?:^|_)(?:text|line|lines|dialog|dialogue|message|msg|title|desc|description|caption|"
                     r"label|name|choice|choices|option|options|tooltip|hint|speech|say|content|body)s?$", k):
            if gd_has_words(v) and not gd_codey(v) and not re.fullmatch(r"[a-z0-9_.\-]+", v):
                out.append(v)
        elif rpy_prose(v) and not gd_codey(v):
            out.append(v)
    elif isinstance(v, dict):
        for k, x in v.items():
            gd_json_strings(x, out, str(k))
    elif isinstance(v, list):
        for x in v:
            gd_json_strings(x, out, key)


# ---------------------------------------------------------------------------
# Готовые переводы игры (CSV/PO → .translation): ключ → текст исходного языка
# ---------------------------------------------------------------------------

SMAZ_RCB = (" ", "the", "e", "t", "a", "of", "o", "and", "i", "n", "s", "e ", "r", " th", " t", "in", "he", "th", "h",
            "he ", "to", "\r\n", "l", "s ", "d", " a", "an", "er", "c", " o", "d ", "on", " of", "re", "of ", "t ",
            ", ", "is", "u", "at", "   ", "n ", "or", "which", "f", "m", "as", "it", "that", "\n", "was", "en", "  ",
            " w", "es", " an", " i", "\r", "f ", "g", "p", "nd", " s", "nd ", "ed ", "w", "ed", "http://", "for", "te",
            "ing", "y ", "The", " c", "ti", "r ", "his", "st", " in", "ar", "nt", ",", " to", "y", "ng", " h", "with",
            "le", "al", "to ", "b", "ou", "be", "were", " b", "se", "o ", "ent", "ha", "ng ", "their", "\"", "hi",
            "from", " f", "in ", "de", "ion", "me", "v", ".", "ve", "all", "re ", "ri", "ro", "is ", "co", "f t",
            "are", "ea", ". ", "her", " m", "er ", " p", "es ", "by", "they", "di", "ra", "ic", "not", "s, ", "d t",
            "at ", "ce", "la", "h ", "ne", "as ", "tio", "on ", "n t", "io", "we", " a ", "om", ", a", "s o", "ur",
            "li", "ll", "ch", "had", "this", "e t", "g ", "e\r\n", " wh", "ere", " co", "e o", "a ", "us", " d",
            "ss", "\n\r\n", "\r\n\r", "=\"", " be", " e", "s a", "ma", "one", "t t", "or ", "but", "el", "so", "l ",
            "e s", "s,", "no", "ter", " wa", "iv", "ho", "e a", " r", "hat", "s t", "ns", "ch ", "wh", "tr", "ut",
            "/", "have", "ly ", "ta", " ha", " on", "tha", "-", " l", "ati", "en ", "pe", " re", "there", "ass",
            "si", " fo", "wa", "ec", "our", "who", "its", "z", "fo", "rs", ">", "ot", "un", "<", "im", "th ", "nc",
            "ate", "><", "ver", "ad", " we", "ly", "ee", " n", "id", " cl", "ac", "il", "</", "rt", " wi", "div",
            "e, ", " it", "whi", " ma", "ge", "x", "e c", "men", ".com")


def smaz_decompress(b):
    out, i = bytearray(), 0
    while i < len(b):
        c = b[i]
        if c == 254:
            out.append(b[i + 1])
            i += 2
        elif c == 255:
            ln = b[i + 1] + 1
            out += b[i + 2:i + 2 + ln]
            i += 2 + ln
        else:
            out += SMAZ_RCB[c].encode("latin-1")
            i += 1
    return bytes(out)


def gd_opt_messages(props):
    """OptimizedTranslation: [(номер в bucket_table, текст)] — ключи там только хэшами."""
    bt = props.get("bucket_table") or []
    strings = props.get("strings") or b""
    out, i = [], 0
    try:
        while i < len(bt):
            size = bt[i]
            for e in range(size):
                j = i + 2 + e * 4
                ofs, comp, unc = bt[j + 1], bt[j + 2], bt[j + 3]
                raw = strings[ofs:ofs + comp]
                txt = raw if comp == unc else smaz_decompress(raw)
                out.append((j, txt.split(b"\0", 1)[0].decode("utf-8", "replace")))
            i += 2 + size * 4
    except (IndexError, TypeError):
        pass
    return out


def gd_hash(d, s):
    """Хэш ключа OptimizedTranslation (как в Godot; char — со знаком)."""
    if d == 0:
        d = 0x1000193
    for b in s.encode("utf-8"):
        d = ((d * 0x1000193) & 0xFFFFFFFF) ^ ((b - 256 if b >= 128 else b) & 0xFFFFFFFF)
    return d


def gd_opt_has_key(props, s):
    """Строка — ключ из таблицы OptimizedTranslation (например, «MENU_TITLE» в тексте кнопки)."""
    ht, bt = props.get("hash_table") or [], props.get("bucket_table") or []
    if not ht or not bt:
        return False
    p = ht[gd_hash(0, s) % len(ht)] & 0xFFFFFFFF
    if p == 0xFFFFFFFF or p + 1 >= len(bt):
        return False
    h = gd_hash(bt[p + 1] & 0xFFFFFFFF, s)
    return any(bt[p + 2 + e * 4] & 0xFFFFFFFF == h for e in range(bt[p]))


def gd_opt_rebuild(props, new_texts):
    """Тот же OptimizedTranslation (те же хэши ключей), но с новыми текстами: {номер: текст}."""
    bt = list(props["bucket_table"])
    strings = bytearray()
    for j, _old in gd_opt_messages(props):
        b = new_texts.get(j, _old).encode("utf-8") + b"\0"
        bt[j + 1], bt[j + 2], bt[j + 3] = len(strings), len(b), len(b)
        strings += b
    return bt, bytes(strings)


def gd_po_messages(props):
    """Translation/TranslationPO: {ключ: текст}."""
    msgs = props.get("messages") or {}
    out = {}
    for k, v in msgs.items() if isinstance(msgs, dict) else ():
        if isinstance(k, str) and isinstance(v, str):
            out[k] = v
        elif isinstance(k, list) and len(k) >= 2 and isinstance(v, list) and v:  # 4.7: [контекст, ключ] → [тексты]
            if not k[0] and isinstance(k[1], str) and isinstance(v[0], str):
                out[k[1]] = v[0]
        elif isinstance(k, str) and isinstance(v, dict):  # TranslationPO: контекст → {ключ: [тексты]}
            if k == "":
                for kk, vv in v.items():
                    t = vv[0] if isinstance(vv, list) and vv else vv
                    if isinstance(kk, str) and isinstance(t, str):
                        out[kk] = t
    return out


def gd_csv_messages(text, src, texts=None):
    """CSV-таблица перевода Godot (keys,en,de...): {ключ: текст на исходном языке}.
    Таблица строк Yarn Spinner (id,text,...): тексты — в texts."""
    import csv
    rows = list(csv.reader(_io.StringIO(text)))
    if not rows or len(rows[0]) < 2:
        return {}
    head = [h.strip().lower() for h in rows[0]]
    if head[0] not in ("keys", "key", "id", "ids", "msgid"):
        return {}
    if texts is not None and "text" in head and src not in head:
        col = head.index("text")
        texts.extend(r[col] for r in rows[1:] if len(r) > col and gd_has_words(r[col]))
        return {}
    col = next((i for i, h in enumerate(head) if h == src or h.split("_")[0] == src), None)
    if col is None:
        return {}
    return {r[0]: r[col] for r in rows[1:] if len(r) > col and r[0] and r[col].strip()}


# ---------------------------------------------------------------------------
# Сбор текста игры
# ---------------------------------------------------------------------------

def gd_find(path):
    """Игра Godot 4: {"kind": "pck"|"exe"|"dir", "pck": путь, "root": папка, "apk": bool} или None."""
    p = os.path.abspath(path)
    cands = []
    if os.path.isfile(p):
        cands.append(p)
        base = os.path.splitext(p)[0]
        cands += [base + ".pck", p + ".pck"]
        p = os.path.dirname(p)
    for d in (p, os.path.join(p, "assets")):
        if os.path.isdir(d):
            sp = os.path.join(d, "assets.sparsepck")
            if os.path.exists(sp):
                return {"kind": "pck", "pck": sp, "root": d, "apk": True}
            if os.path.exists(os.path.join(d, "project.binary")) and os.path.basename(d) == "assets":
                return {"kind": "dir", "pck": None, "root": d, "apk": True}
    if os.path.isdir(p) and os.path.exists(os.path.join(p, "project.godot")) and not any(
            f.lower().endswith(".pck") for f in os.listdir(p)):  # исходники проекта (игра без экспорта)
        return {"kind": "dir", "pck": None, "root": p, "apk": False}
    if os.path.isdir(p):
        pcks = sorted(os.path.join(p, f) for f in os.listdir(p) if f.lower().endswith(".pck"))
        exes = sorted(os.path.join(p, f) for f in os.listdir(p)
                      if f.lower().endswith((".exe", ".x86_64", ".x86_32", ".arm64")) and os.path.isfile(os.path.join(p, f)))
        cands += pcks + exes
        mac = [os.path.join(dp, f) for dp, _d, fs in os.walk(p) for f in fs
               if f.lower().endswith(".pck") and ".app" in dp][:3]
        cands += mac
    for c in cands:
        if not os.path.isfile(c):
            continue
        try:
            pk = GdPack(c)
        except (ValueError, OSError, _struct.error):
            continue
        return {"kind": "exe" if pk.embedded else "pck", "pck": c, "root": os.path.dirname(c), "apk": False}
    return None


def gd_open(g):
    return GdDir(g["root"]) if g["kind"] == "dir" else GdPack(g["pck"])


def gd_collect(src, lang_src="en"):
    """Тексты игры: (фразы-текст, {ключ: текст исходного языка}, [(путь, свойства OptimizedTranslation)], статистика)."""
    texts, keyed, opts = [], {}, []
    st = {"files": 0, "scenes": 0, "scripts": 0, "gdc_skip": 0, "bad": [], "translations": []}
    names = [n for n in src.names() if not n.startswith("res://" + GD_DIR + "/")]
    remap = {n[:-6] for n in names if n.endswith(".remap")}
    for n in names:
        low = n.lower()
        if low.endswith((".png", ".jpg", ".webp", ".ogg", ".wav", ".mp3", ".ctex", ".stex", ".oggvorbisstr",
                         ".sample", ".mp3str", ".fontdata", ".ttf", ".otf", ".woff", ".woff2", ".res.import",
                         ".import", ".md5", ".uid", ".so", ".dll", ".dylib", ".svg", ".glb", ".mesh", ".scn.import")):
            if not low.endswith((".translation",)):
                continue
        size = src.files[n][1] if isinstance(src, GdPack) else 0
        if size > 64 << 20 and not low.endswith((".translation", ".csv", ".json")):
            continue  # огромные файлы — модели, видео, звук
        try:
            data = src.read(n)
        except (OSError, KeyError):
            continue
        if not data:
            continue
        st["files"] += 1
        try:
            if data[:4] in (b"RSRC", b"RSCC"):
                res = gd_read_binary_res(data)
                main_type = res["type"]
                for t, props in res["res"]:
                    if t in ("Translation", "OptimizedTranslation", "TranslationPO"):
                        loc = str(props.get("locale") or "en")  # «en» по умолчанию в файл не пишется
                        st["translations"].append(f"{n} ({t}, {loc})")
                        if loc.split("_")[0].lower() != lang_src:
                            continue
                        if t == "OptimizedTranslation":
                            opts.append((n, props))
                        else:
                            keyed.update(gd_po_messages(props))
                        continue
                    if t == "PackedScene" and isinstance(props.get("_bundled"), dict):
                        st["scenes"] += 1
                        gd_scene_strings(props["_bundled"], texts)
                    elif t in ("GDScript",) and isinstance(props.get("script/source"), str):
                        gd_script_strings(props["script/source"], texts)
                    else:
                        for k, v in props.items():
                            gd_walk(v, k, texts)
                _ = main_type
            elif low.endswith(".gdc"):
                try:
                    texts.extend(s for s in gd_gdc_constants(data) if rpy_prose(s) and not gd_codey(s))
                    st["scripts"] += 1
                except RuntimeError:
                    st["gdc_skip"] += 1
            elif low.endswith(".gd") and n not in remap:
                gd_script_strings(data.decode("utf-8", "replace"), texts)
                st["scripts"] += 1
            elif low.endswith((".tscn", ".tres", ".escn")):
                for typ, prop, s, whole in gd_read_text_res(data.decode("utf-8", "replace")):
                    if prop in ("script/source", "source_code"):
                        gd_script_strings(s, texts)
                    elif gd_prop_ok(prop, s) if whole else (rpy_prose(s) and not gd_codey(s)):
                        texts.append(s)
                st["scenes"] += low.endswith(".tscn")
            elif low.endswith(".json"):
                try:
                    gd_json_strings(json.loads(data.decode("utf-8-sig")), texts)
                except ValueError:
                    pass
            elif low.endswith(".csv"):
                keyed.update(gd_csv_messages(data.decode("utf-8-sig", "replace"), lang_src, texts))
            elif low.endswith(".dtl"):  # Dialogic 2: «Персонаж: текст» и просто текст
                for line in data.decode("utf-8-sig", "replace").split("\n"):
                    t = line.strip()
                    if not t or t.startswith(("[", "#", "-", "jump ", "label ", "if ", "elif ", "else", "set ", "do ",
                                              "return", "join ", "leave ", "update ", "audio ", "music ")):
                        continue
                    m = re.match(r"^[\w ]{1,40}(?:\([^)]*\))?:\s+(.+)$", t)
                    t = (m.group(1) if m else t).strip()
                    if gd_has_words(t):
                        texts.append(t)
        except Exception as e:  # noqa: BLE001 — один странный файл не мешает остальным
            st["bad"].append(f"{n} ({e.__class__.__name__}: {e})"[:120])
    return texts, keyed, opts, st


# ---------------------------------------------------------------------------
# Перевод строки Godot: BBCode [b]…[/b], {имя}, %s, \n — защищены
# ---------------------------------------------------------------------------

GD_SOLO_BB = set("br img lb rb hr".split())
GD_BB_TAGS = set(("b i u s code p center left right fill indent url hint img font font_size opentype_features lang "
                  "table cell ul ol lb rb color bgcolor fgcolor outline_size outline_color wave tornado shake fade "
                  "rainbow pulse dropcap char br hr kbd").split())


def gd_mark(s):
    """Текст Godot → (с метками ⟦n⟧, куски, пары тегов) или None."""
    toks, out, pairs, stack = [], [], {}, []
    i, n = 0, len(s)

    def tok(x):
        toks.append(x)
        out.append(f"\u27E6{len(toks) - 1}\u27E7")
        return len(toks) - 1
    while i < n:
        c = s[i]
        if c == "[":
            m = re.compile(r"\[(/?)([a-zA-Z_][\w]*)((?:[= ][^\[\]]*)?)\]").match(s, i)
            if m and not (m.group(2).lower() in GD_BB_TAGS or re.fullmatch(r"[a-z_]+", m.group(2))
                          and not m.group(3).strip(" =") or m.group(3).startswith("=")):
                m = None  # «[Press E]» — просто текст в скобках
            if m:
                name = m.group(2).lower()
                if not m.group(1) and name == "img":  # [img]путь[/img] — целиком
                    end = s.find("[/img]", m.end())
                    if end >= 0:
                        tok(s[i:end + 6])
                        i = end + 6
                        continue
                k = tok(m.group(0))
                if m.group(1):
                    for x in range(len(stack) - 1, -1, -1):
                        if stack[x][0] == name:
                            pairs[stack[x][1]] = k
                            del stack[x:]
                            break
                elif name not in GD_SOLO_BB:
                    stack.append((name, k))
                i = m.end()
                continue
        if c == "{":
            m = re.compile(r"\{[\w.\-:]*\}").match(s, i)
            if m:
                tok(m.group(0))
                i = m.end()
                continue
        if c == "%":
            m = re.compile(r"%[-+#0]*\d*(?:\.\d+)?[sdifxXoceEgGv%]").match(s, i)
            if m:
                tok(m.group(0))
                i = m.end()
                continue
        if c == "\n":
            tok("\n")
            i += 1
            continue
        out.append(c)
        i += 1
    text = "".join(out)
    if not gd_has_words(re.sub(r"\u27E6\d+\u27E7", " ", text)):
        return None
    return text, toks, {str(a): b for a, b in pairs.items()}


def gd_unmark(res, toks):
    res = re.sub(r"\s*\n\s*", " ", res)
    return re.sub(r"\u27E6\s*(\d+)\s*\u27E7", lambda m: toks[int(m.group(1))], res)


# ---------------------------------------------------------------------------
# Что кладём в игру
# ---------------------------------------------------------------------------

def gd_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace(
        "\t", "\\t") + '"'


def gd_tres_translation(lang, table):
    body = ",\n".join(f"{gd_str(k)}: {gd_str(v)}" for k, v in table.items())
    return (f'[gd_resource type="Translation" format=3]\n\n[resource]\nlocale = {gd_str(lang)}\n'
            f"messages = {{\n{body}\n}}\n")


def gd_tres_optimized(lang, props, bt, strings):
    ht = ", ".join(str(x) for x in props["hash_table"])
    bts = ", ".join(str(x if x < 0x80000000 else x - 0x100000000) for x in bt)
    st = ", ".join(str(x) for x in strings)
    return (f'[gd_resource type="OptimizedTranslation" format=3]\n\n[resource]\nlocale = {gd_str(lang)}\n'
            f"hash_table = PackedInt32Array({ht})\nbucket_table = PackedInt32Array({bts})\n"
            f"strings = PackedByteArray({st})\n")


GD_SCRIPT = '''extends Node
## sugarcube_translate: машинный перевод ({lang}). Alt+T — показать оригинал / перевод.
## Убрать перевод: запустите скрипт с --remove (или удалите override.cfg и папку {dir}).

const RUT_LOCALE := {lang_q}
const RUT_FILES := [{files}]
var rut_on := true
var rut_orig := ""


func _enter_tree() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	for p in RUT_FILES:
		var t = load(p)
		if t is Translation:
			TranslationServer.add_translation(t)
	rut_orig = TranslationServer.get_locale()
	TranslationServer.set_locale(RUT_LOCALE)


func _process(_delta: float) -> void:
	if rut_on and TranslationServer.get_locale() != RUT_LOCALE:
		rut_orig = TranslationServer.get_locale()
		TranslationServer.set_locale(RUT_LOCALE)


func _input(event: InputEvent) -> void:
	var k := event as InputEventKey
	if k and k.pressed and not k.echo and k.alt_pressed and k.keycode == KEY_T:
		rut_on = not rut_on
		TranslationServer.set_locale(RUT_LOCALE if rut_on else rut_orig)
'''

GD_OVERRIDE_MARK = "; sugarcube_translate"


def gd_override(old):
    """override.cfg игры (если был) + наша автозагрузка."""
    lines = (old or "").replace("\r\n", "\n").split("\n")
    lines = [x for x in lines if GD_OVERRIDE_MARK not in x and not x.startswith(GD_AUTOLOAD + "=")]
    text = "\n".join(lines).strip("\n")
    ours = f'{GD_AUTOLOAD}="*res://{GD_DIR}/rut.gd" {GD_OVERRIDE_MARK}'
    if re.search(r"^\[autoload\]\s*$", text, re.M):
        text = re.sub(r"^\[autoload\]\s*$", "[autoload]\n" + ours, text, count=1, flags=re.M)
    else:
        text = (text + "\n\n" if text else "") + "[autoload]\n" + ours
    return text + "\n"


def gd_files(lang, table, opt_tres, old_override):
    """{res://путь: байты} — всё, что добавляем в игру."""
    files = {f"res://{GD_DIR}/{lang}.tres": gd_tres_translation(lang, table).encode("utf-8")}
    for i, text in enumerate(opt_tres):
        files[f"res://{GD_DIR}/{lang}_keys{i}.tres"] = text.encode("utf-8")
    lst = ", ".join(gd_str(k) for k in files)
    files[f"res://{GD_DIR}/rut.gd"] = GD_SCRIPT.format(lang=lang, dir=GD_DIR, lang_q=gd_str(lang),
                                                        files=lst).encode("utf-8")
    files["res://override.cfg"] = gd_override(old_override).encode("utf-8")
    return files


def gd_install(g, src, files):
    """Записывает файлы в игру. Пак/exe — копия оригинала сохраняется рядом (*.rut-orig)."""
    if g["kind"] == "dir":
        for res, data in files.items():
            p = os.path.join(g["root"], *res[6:].split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as f:
                f.write(data)
        return [g["root"]]
    path = g["pck"]
    bak = path + ".rut-orig"
    if not os.path.exists(bak):
        if src.sparse:
            shutil.copy2(path, bak)
        else:
            shutil.copy2(path, bak)
    orig = GdPack(bak) if not src.sparse else src
    orig.write(path, files)
    if os.name != "nt" and g["kind"] == "exe":
        os.chmod(path, os.stat(bak).st_mode)
    out = [path]
    if not g["apk"]:  # и рядом с паком: Godot читает его, даже если игру запускают с --main-pack
        oc = os.path.join(os.path.dirname(path), "override.cfg")
        old = None
        if os.path.exists(oc):
            with open(oc, encoding="utf-8", errors="replace") as f:
                old = f.read()
        with open(oc, "w", encoding="utf-8", newline="\n") as f:
            f.write(gd_override(old))
        out.append(oc)
    return out


def gd_remove(g):
    if g["kind"] == "dir":
        import shutil as _sh
        d = os.path.join(g["root"], GD_DIR)
        if os.path.isdir(d):
            _sh.rmtree(d)
        oc = os.path.join(g["root"], "override.cfg")
        if os.path.exists(oc):
            with open(oc, encoding="utf-8") as f:
                txt = f.read()
            rest = "\n".join(x for x in txt.split("\n") if GD_OVERRIDE_MARK not in x).strip()
            if rest in ("", "[autoload]"):
                os.remove(oc)
            else:
                with open(oc, "w", encoding="utf-8") as f:
                    f.write(rest + "\n")
        return True
    oc = os.path.join(os.path.dirname(g["pck"]), "override.cfg")
    if os.path.exists(oc) and not g["apk"]:
        with open(oc, encoding="utf-8", errors="replace") as f:
            txt = f.read()
        if GD_OVERRIDE_MARK in txt:
            rest = "\n".join(x for x in txt.split("\n") if GD_OVERRIDE_MARK not in x).strip()
            if rest in ("", "[autoload]"):
                os.remove(oc)
            else:
                with open(oc, "w", encoding="utf-8") as f:
                    f.write(rest + "\n")
    bak = g["pck"] + ".rut-orig"
    if os.path.exists(bak):
        os.replace(bak, g["pck"])
        return True
    return False


def run_godot(args, g, tr, lang):
    """Godot 4 целиком: тексты → перевод → словарь + автозагрузка в пак/APK."""
    t0 = time.time()
    if g["pck"] and os.path.exists(g["pck"] + ".rut-orig"):
        src = GdPack(g["pck"] + ".rut-orig")  # переводим оригинал (наши файлы из прошлого запуска — не в счёт)
    else:
        src = gd_open(g)
    kind = {"pck": "пак .pck", "exe": "пак внутри программы", "dir": "распакованные файлы (APK)"}[g["kind"]]
    ver = f"{src.major}.{src.minor}" if isinstance(src, GdPack) else "4.x"
    print(f"Godot {ver}: {kind}: {g['pck'] or g['root']}", file=sys.stderr)
    texts, keyed, opts, st = gd_collect(src, (args.src or "en").split("-")[0].lower())
    print(f"  файлов: {st['files']:,}, сцен: {st['scenes']:,}, скриптов: {st['scripts']:,}"
          + (f", готовых переводов игры: {len(st['translations'])}" if st["translations"] else ""), file=sys.stderr)
    if st["gdc_skip"]:
        print(f"  {st['gdc_skip']} скриптов .gdc сжаты zstd — чтобы взять из них текст: pip install zstandard",
              file=sys.stderr)
    for b in st["bad"][:5]:
        print(f"  не прочитался: {b}", file=sys.stderr)
    opt_msgs = [(path, props, gd_opt_messages(props)) for path, props in opts]
    texts_u = [s for s in dict.fromkeys(s for s in texts if s.strip())
               if s not in keyed and not any(gd_opt_has_key(pr, s) for _p, pr in opts)]
    want = list(dict.fromkeys(list(keyed.values()) + [t for _p, _pr, ms in opt_msgs for _j, t in ms] + texts_u))
    entries = {}
    for s in want:
        m = gd_mark(s)
        if m:
            entries[s] = m
    chars = sum(len(m[0]) for m in entries.values())
    print(f"  текстов: {len(texts_u):,}, ключей перевода игры: {len(keyed) + sum(len(x[2]) for x in opt_msgs):,}; "
          f"к переводу {len(entries):,} фраз ({chars:,} симв.)", file=sys.stderr)
    if args.dry_run:
        return 0
    translate_marked(tr, [(m[0], {"p": m[2]} if m[2] else None) for m in entries.values()])
    done = {}
    missing = broken = 0
    for s, (k, toks, _p) in entries.items():
        r = tr.peek(k)
        if not isinstance(r, str):
            missing += 1
        elif not live_marks_ok(k, r):
            broken += 1
        else:
            done[s] = gd_unmark(_rpy_fix_spaces(k, r, toks), toks)
    table = {}
    for key, text in keyed.items():
        if text in done:
            table[key] = done[text]
    for s in texts_u:
        if s in done and done[s] != s:
            table[s] = done[s]
    opt_tres = []
    for _path, props, ms in opt_msgs:
        new = {j: done[t] for j, t in ms if t in done}
        if new:
            bt, strings = gd_opt_rebuild(props, new)
            opt_tres.append(gd_tres_optimized(lang, props, bt, strings))
    old_ov = None
    if "res://override.cfg" in getattr(src, "files", {}):
        try:
            old_ov = src.read("res://override.cfg").decode("utf-8", "replace")
        except (OSError, KeyError, AttributeError):
            old_ov = None
    if tr.offline:
        print(f"Перевод остановлен: {tr.stop_reason}. Кладу в игру то, что готово; запустите ту же команду "
              f"позже — продолжится с этого места.", file=sys.stderr)
    files = gd_files(lang, table, opt_tres, old_ov)
    out = gd_install(g, src, files)
    for p in out:
        print(f"  записан: {p}", file=sys.stderr)
    print(f"Готово за {(time.time() - t0) / 60:.1f} мин: переведено {len(table):,} фраз" +
          (f" (+ {len(opt_tres)} таблиц перевода игры по ключам)" if opt_tres else "") +
          (f", не перевелось {missing:,} (лимит/сеть — запустите ещё раз, продолжит)" if missing else "") +
          (f", {broken:,} оставлены как есть (переводчик испортил теги)" if broken else ""), file=sys.stderr)
    if g["kind"] != "dir":
        print(f"  Оригинал сохранён: {g['pck']}.rut-orig  (вернуть: --remove)", file=sys.stderr)
    if g["apk"]:
        print("  Это APK: соберите и подпишите его заново (apktool b + apksigner/uber-apk-signer).", file=sys.stderr)
    print("  В игре: Alt+T — показать оригинал/перевод.", file=sys.stderr)
    return 0


# ===========================================================================
# Какой движок у игры: Ren'Py / Godot 4 (перевод встраивается в игру) или SugarCube/HTML (ниже, в main)
# ===========================================================================

RPY_TL_NAMES = {"ru": "russian", "uk": "ukrainian", "de": "german", "fr": "french", "es": "spanish",
                "pt": "portuguese", "it": "italian", "pl": "polish", "ja": "japanese", "ko": "korean",
                "zh": "schinese", "tr": "turkish", "cs": "czech", "be": "belarusian", "vi": "vietnamese",
                "id": "indonesian", "ar": "arabic", "fi": "finnish", "nl": "dutch", "hu": "hungarian"}


def detect_engine(path):
    """("renpy", игра) / ("godot", игра) / (None, None) — по папке, .exe/.py/.sh, .pck или распакованному APK."""
    p = os.path.abspath(path)
    low = p.lower()
    if os.path.isfile(p) and low.endswith((".html", ".htm", ".twee", ".tw", ".txt", ".json", ".js")):
        return None, None
    if os.path.isfile(p) and low.endswith((".apk", ".xapk", ".aab")):
        raise SystemExit("Это сам файл APK. Сначала распакуйте его (apktool d \"игра.apk\") и укажите получившуюся "
                         "папку; после перевода соберите и подпишите APK заново (apktool b, uber-apk-signer).")
    g = rpy_find_game(p)
    if g:
        return "renpy", g
    g = gd_find(p)
    if g:
        return "godot", g
    d = p if os.path.isdir(p) else os.path.dirname(p)
    try:
        names = os.listdir(d)
    except OSError:
        names = []
    for fn in names:
        if fn.lower().endswith(".pck"):
            with open(os.path.join(d, fn), "rb") as f:
                head = f.read(8)
            if head[:4] == b"GDPC" and _struct.unpack("<I", head[4:8])[0] < 2:
                raise SystemExit("Это игра на Godot 3 (или старше) — поддерживается только Godot 4.")
    return None, None


def engine_cache_parts(kind, g):
    """(папка, начало имени, конец имени) файла кэша: <папка>/<начало><язык><конец>."""
    if g.get("apk"):  # кэш — рядом с распакованным APK, чтобы не попал в сборку
        base = (g["root"] if kind == "renpy" else os.path.dirname(g["root"])).rstrip("/\\")
        return os.path.dirname(base), os.path.basename(base) + ".rut_cache.", ".json"
    return g["root"], "rut_cache.", ".json"


def engine_cache_path(kind, g, lang):
    d, prefix, suffix = engine_cache_parts(kind, g)
    return os.path.join(d, prefix + lang + suffix)


def run_engine(args, kind, g, engine, key, glossary):
    """Ren'Py или Godot 4: тексты игры → перевод (кэш) → словарь и маленький модуль в игру."""
    lang = args.dst or "ru"
    name = {"renpy": "Ren'Py", "godot": "Godot 4"}[kind]
    if args.remove:
        if kind == "renpy":
            gone = rpy_remove(g)
            print(f"{name}: перевод убран (удалено файлов: {len(gone)})." if gone else
                  f"{name}: файлов перевода в игре нет.", file=sys.stderr)
        else:
            ok = gd_remove(g)
            print(f"{name}: перевод убран, оригинал восстановлен." if ok else
                  f"{name}: копии оригинала (*.rut-orig) нет — перевод, похоже, не ставился.", file=sys.stderr)
        return 0
    if kind == "renpy" and (args.console or args.portable or args.import_files):
        if args.dry_run:
            print("Перевод на лету: заранее ничего не переводится — переводится то, что появляется на экране.",
                  file=sys.stderr)
            return 0
        return run_renpy_live(args, g, engine, key, glossary)
    if args.console or args.portable or args.import_files:
        print(f"{name}: перевод на лету (-l/-c) есть только для Ren'Py и HTML-игр. Делаю обычный перевод: он "
              f"встраивается в игру и подставляется при показе текста.", file=sys.stderr)
    if kind == "renpy":
        tl = os.path.join(g["game"], g["pre"] + "tl", g["pre"] + RPY_TL_NAMES.get(lang.split("-")[0], "~"))
        if os.path.isdir(tl):
            print(f"Заметка: в игре уже есть свой перевод ({tl}) — его можно включить в настройках игры "
                  f"(Language/Язык). Машинный перевод всё равно сделаю.", file=sys.stderr)
    cache_path = args.cache or engine_cache_path(kind, g, lang)
    tr = Translator(args.src, lang, cache_path, engine, key, args.region, args.delay, glossary,
                    args.max_chars, args.max_wait)
    if args.fresh:
        tr.start_fresh()
    print(f"Кэш перевода: {cache_path}", file=sys.stderr)
    if not args.dry_run:
        if engine in ("free", "google"):
            n_ok = tr.probe()
            if args.fast:
                tr.workers = max(1, min(n_ok, 6))
        elif args.fast:
            tr.workers = 3
    try:
        return (run_renpy if kind == "renpy" else run_godot)(args, g, tr, lang)
    except KeyboardInterrupt:
        tr.halt.set()
        tr.save(force=True)
        print("\nОстановлено. Кэш сохранён — запустите ту же команду, чтобы продолжить.", file=sys.stderr)
        sys.stderr.flush()
        os._exit(1)
    except Exception:
        tr.save(force=True)
        print("\nНеожиданная ошибка. Всё переведённое сохранено в кэше — пришлите текст ниже.", file=sys.stderr)
        raise


# ==== ENGINES END ====


EXIT_WORDS = ("exit", "quit", "q", "выход", "выйти", "стоп", "stop")
_CONSOLE = {"q": None, "asking": False}  # строки, введённые в консоли, пока работает watch_exit()


def ask(prompt, default=""):
    """Вопрос в консоли. exit (или «выход») — выйти из скрипта: на телефоне Ctrl+C набрать неудобно."""
    q = _CONSOLE["q"]
    if q is not None:
        while not q.empty():  # то, что ввели раньше (просто Enter во время перевода), — не ответ
            q.get_nowait()
        sys.stderr.write(prompt)
        sys.stderr.flush()
        _CONSOLE["asking"] = True
        try:
            ans = q.get()
        finally:
            _CONSOLE["asking"] = False
        if ans is None:
            ans = default
    else:
        try:
            ans = input(prompt)
        except EOFError:
            ans = default
    if ans.strip().lower() in EXIT_WORDS:
        print("Выход.", file=sys.stderr)
        sys.stderr.flush()
        os._exit(0)
    return ans


SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".sugarcube_translate.json")


def settings_load():
    """Настройки скрипта между запусками (пока — последний выбранный язык)."""
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def settings_save(**kw):
    d = settings_load()
    d.update(kw)
    try:
        tmp = SETTINGS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(tmp, SETTINGS_PATH)
    except OSError:
        pass


def locale_lang(src):
    """Язык системы (uk_UA → uk) — подсказка при первом запуске; язык оригинала игры не предлагаем."""
    cands = [os.environ.get(k, "") for k in ("LC_ALL", "LC_MESSAGES", "LANG")]
    cands.append(os.environ.get("LANGUAGE", "").split(":")[0])
    try:  # Windows и прочие: язык системы
        import locale
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cands.append((locale.getdefaultlocale()[0] if hasattr(locale, "getdefaultlocale") else "") or "")
    except Exception:  # noqa: BLE001
        pass
    m = None
    for loc in cands:
        m = re.match(r"([a-z]{2,3})(?:[_-]([A-Za-z]{2}))?(?![a-z])", loc or "")
        if m:
            break
    if not m:
        return None
    code = m.group(1).lower()
    if code == "zh":
        code = "zh-TW" if (m.group(2) or "").upper() in ("TW", "HK") else "zh-CN"
    if code == (src or "en").split("-")[0].lower():
        return None
    return code


def _stop_main():
    """Как Ctrl+C: прервать то, что делает скрипт (кэш и переводы сохраняются как обычно)."""
    if os.name == "nt":
        import _thread
        _thread.interrupt_main()
    else:
        import signal
        os.kill(os.getpid(), signal.SIGINT)


def watch_exit():
    """Пока скрипт работает (перевод, окно -c), «exit» и Enter в консоли — остановить его, как Ctrl+C."""
    if _CONSOLE["q"] is not None:
        return
    try:
        if not sys.stdin or not sys.stdin.isatty():
            return
    except (AttributeError, ValueError):
        return
    import queue
    q = _CONSOLE["q"] = queue.Queue()

    def run():
        while True:
            try:
                line = sys.stdin.readline()
            except Exception:  # noqa: BLE001
                line = ""
            if not line:
                q.put(None)
                return
            if line.strip().lower() in EXIT_WORDS and not _CONSOLE["asking"]:
                print("Останавливаю…", file=sys.stderr)
                _stop_main()
                continue
            q.put(line.rstrip("\r\n"))
    t = threading.Thread(target=run, name="rut-console", daemon=True)
    t.start()


def main():
    ap = argparse.ArgumentParser(
        prog="sugarcube_translate.py", description=HELP_INTRO, epilog=HELP_EXAMPLES,
        formatter_class=lambda prog: argparse.RawDescriptionHelpFormatter(prog, max_help_position=30, width=100),
        add_help=False)
    g = ap.add_argument_group("Основное")
    g.add_argument("input", nargs="?", help="игра: файл .html или .twee/.tw, папка игры (SugarCube, Ren'Py, "
                                            "Godot 4), её .exe/.pck или папка распакованного APK")
    g.add_argument("output", nargs="?",
                   help="своё имя результата, например \"FC_ru\" → FC_ru_safe.html и FC_ru_full.html "
                        "(по умолчанию <имя игры>_ru)")
    g.add_argument("-h", "--help", action="help", help="показать эту справку")
    g.add_argument("--dst", "--to", "--lang", dest="dst", metavar="ЯЗЫК",
                   help="на какой язык переводить: ru, uk, en, de, pl, fr, es ... Можно короче: -uk, -de. "
                        "Если не указать — скрипт спросит (Enter — язык прошлого раза). Для -l и -c не нужен: "
                        "игра берёт язык телефона / компьютера, а выбранный в игре запоминает (флаг — язык "
                        "по умолчанию вместо языка системы)")
    g.add_argument("--src", default="en", metavar="ЯЗЫК", help="язык оригинала (по умолчанию en)")
    g.add_argument("-C", "--check", action="store_true",
                   help="проверить за пару секунд, какие переводчики сейчас работают (игру указывать не нужно)")
    g.add_argument("-d", "--dry-run", action="store_true",
                   help="пробный запуск: показать, сколько символов нужно перевести, ничего не переводя")
    g.add_argument("-R", "--remove", action="store_true",
                   help="Ren'Py и Godot: убрать перевод из игры (вернуть оригинал)")

    g = ap.add_argument_group("Перевод на лету (HTML и Ren'Py)")
    g.add_argument("--portable", dest="portable", action="store_true", help=argparse.SUPPRESS)  # старое имя -l
    g.add_argument("-l", "--live", dest="portable", action="store_true",
                   help="перевод на лету: сделать файл <игра>_live.html со встроенным переводом и выйти — он "
                        "открывается на ПК двойным щелчком и на Android, без окна скрипта (браузер обращается к "
                        "Google сам), текст переводится, когда появляется на экране, и запоминается. "
                        "Ren'Py: модуль перевода на лету встраивается в саму игру (и в APK)")
    g.add_argument("-c", "--console-live", dest="console", action="store_true",
                   help="перевод на лету через окно скрипта (консоль): скрипт запускает игру (HTML — в браузере, "
                        "Ren'Py — её .exe/.sh) и переводит сам, переводы копятся на диске; при выходе (exit или Ctrl+C) они "
                        "встраиваются в игру (<игра>_live.html или файлы Ren'Py)")
    g.add_argument("-i", "--import", dest="import_files", action="append", default=[], metavar="ФАЙЛ",
                   help="добавить переводы, сохранённые в игре кнопкой «Сохранить переводы в файл» (например, "
                        "с телефона; в Ren'Py — rut_live.json из папки сохранений), и встроить их в игру")
    g.add_argument("-w", "--live-wait", type=float, default=3, metavar="СЕК",
                   help="для -l и -c: сколько секунд ждать перевода нового пассажа (в Ren'Py — реплики), "
                        "прежде чем показать его как есть (по умолчанию 3); перевод заменит его, когда придёт")
    g.add_argument("-p", "--port", type=int, default=8765, metavar="N",
                   help="порт для -c (по умолчанию 8765; от него зависят сохранения в браузере)")
    g.add_argument("-B", "--no-browser", action="store_true",
                   help="для -c: не открывать браузер (Ren'Py — не запускать игру) самому")

    g = ap.add_argument_group("Переводчик и скорость")
    g.add_argument("-e", "--engine", choices=ENGINES, metavar="ИМЯ",
                   help="free — по умолчанию: бесплатный Google (несколько адресов по кругу); "
                        "по ключу API: google-cloud, deepl, microsoft")
    g.add_argument("-k", "--key", "--api-key", dest="key", metavar="КЛЮЧ",
                   help="ключ API для google-cloud / deepl / microsoft")
    g.add_argument("--region", default=os.environ.get("AZURE_TRANSLATOR_REGION"), metavar="РЕГИОН",
                   help="регион ключа Microsoft, например westeurope")
    g.add_argument("-f", "--fast", action="store_true",
                   help="быстрый режим: запросы идут одновременно на все рабочие адреса Google "
                        "(или в 3 потока для переводчиков по ключу). Быстрее, но блокировки бывают чаще")
    g.add_argument("-D", "--delay", type=float, default=None, metavar="СЕК",
                   help="пауза между запросами в секундах (по умолчанию 1, в -l и -c 0). Больше — медленнее, "
                        "но реже блокируют: попробуйте 2–3")
    g.add_argument("-M", "--max-chars", type=int, default=0, metavar="N",
                   help="перевести за этот запуск не больше N символов (чтобы не выйти за лимит ключа); "
                        "остальное — при следующем запуске")
    g.add_argument("-W", "--max-wait", type=int, default=60, metavar="МИН",
                   help="сколько минут подряд ждать, если переводчик блокирует (по умолчанию 60); "
                        "потом скрипт соберёт игру из готового и остановится")
    g.add_argument("-g", "--glossary", metavar="ФАЙЛ",
                   help="JSON-файл со своими переводами, например {\"Arcology\": \"Аркология\"}")

    g = ap.add_argument_group("SugarCube: тонкая настройка (обычно не нужна)")
    g.add_argument("-m", "--mode", choices=("both", "safe", "full"), default="both",
                   help="какие версии делать: both — обе (по умолчанию), safe — только безопасную, "
                        "full — только полную")
    g.add_argument("--no-gender", action="store_true",
                   help="не делать варианты «он/она» (немного меньше символов, но хуже грамматика)")
    g.add_argument("--gender-default", choices=("auto", "f", "m", "none"), default="auto", metavar="РОД",
                   help="род персонажей во фразах, где есть только имя («Сара предана» или «предан»): "
                        "auto — определить по игре (по умолчанию), f — женский, m — мужской, none — не задавать")
    g.add_argument("--gender-vars", metavar="ФАЙЛ",
                   help="JSON-файл с доп. переменными-местоимениями, например {\"pn\": [\"he\", \"she\"]}")
    g.add_argument("--no-context", action="store_true",
                   help="не подсказывать переводчику соседний текст для коротких обрывков («devoted», «Perky»). "
                        "По умолчанию подсказка включена: «Упругая», а не «Весёлый»; «Сара предана», а не «предан»")
    g.add_argument("--context", action="store_true", help=argparse.SUPPRESS)  # старый флаг, теперь по умолчанию
    g.add_argument("--no-is-fix", action="store_true",
                   help="не убирать на экране оставшееся английское «is/are/was» в уже русских фразах "
                        "(«Сара is предана» → «Сара предана»). Работает только для ru/uk/be")
    g.add_argument("--no-lisp", action="store_true",
                   help="не сохранять шепелявость (в Free Cities: <<s>>, <<ss>>, <<c>>, <<z>> внутри слов)")
    g.add_argument("--no-values", action="store_true",
                   help="не показывать значения переменных переведёнными (\"white\" → «белый» только на экране, "
                        "в самой игре значение не меняется)")
    g.add_argument("--no-ui", action="store_true",
                   help="не переводить интерфейс SugarCube (Сохранения, Настройки ...)")
    g.add_argument("--no-js", action="store_true",
                   help="не трогать JavaScript вообще (только текст пассажей и ссылки)")
    g.add_argument("-s", "--skip", metavar="ШАБЛОН",
                   help="не переводить пассажи, чьё имя подходит под шаблон, например \"Debug|Cheat\"")
    g.add_argument("-K", "--keep", metavar="ФАЙЛ",
                   help="текстовый файл со строками, которые нельзя переводить (по одной на строку) — "
                        "если после перевода что-то сломалось")
    g.add_argument("-t", "--translate-list", metavar="ФАЙЛ",
                   help="текстовый файл со строками кода, которые нужно перевести обязательно "
                        "(по одной на строку; берите их из отчёта .skipped.tsv). Ключи-сравнения "
                        "всё равно не переводятся, чтобы не сломать игру")
    g.add_argument("--force", action="store_true",
                   help="переводить, даже если формат игры не SugarCube (Harlowe и др. — на свой риск)")
    g.add_argument("-a", "--analyze", action="store_true",
                   help="ничего не переводить, а сохранить файл <игра>.structure.txt со структурой кода игры "
                        "(текст заменён на T) — чтобы прислать его для настройки скрипта")

    g = ap.add_argument_group("Кэш")
    g.add_argument("-F", "--fresh", action="store_true",
                   help="начать перевод заново: старый кэш переименуется в .bak, всё переведётся с нуля")
    g.add_argument("--cache", metavar="ФАЙЛ",
                   help="где хранить уже переведённое (по умолчанию <игра>.ru.cache.json рядом с игрой)")
    g.add_argument("--reuse-cache", action="store_true", help=argparse.SUPPRESS)  # кэш старой версии — без вопроса

    if len(sys.argv) == 1:
        print(HELP_INTRO.strip() + "\n\nСправка по всем возможностям:  python sugarcube_translate.py -h",
              file=sys.stderr)
        return
    argv = []
    for a in sys.argv[1:]:  # -uk, -de, -pt-BR → --dst uk
        m = re.fullmatch(r"-([a-z]{2,3}(?:-[A-Za-z]{2,4})?)", a)
        argv += ["--dst", m.group(1)] if m and a != "-h" else [a]
    args = ap.parse_args(argv)
    watch_exit()
    if args.input and not args.check:
        args.input = resolve_input(args.input)
    live_like = args.console or args.portable or bool(args.import_files)
    if args.delay is None:
        args.delay = 0.0 if live_like else 1.0  # в игре ждать нельзя: адреса Google и так чередуются
    if args.dst and not re.fullmatch(r"[a-z]{2,3}(?:-[A-Za-z]{2,4})?", args.dst):
        ap.error(f"непонятный код языка: {args.dst} (примеры: ru, uk, en, de, pt-BR)")
    last_lang = settings_load().get("lang")
    if not (isinstance(last_lang, str) and re.fullmatch(r"[a-z]{2,3}(?:-[A-Za-z]{2,4})?", last_lang)):
        last_lang = None
    if args.dst:
        if not (args.check or args.remove):
            settings_save(lang=args.dst)  # -uk, --dst uk — тоже запоминаем
    elif sys.stdin.isatty() and not (args.check or args.dry_run or args.analyze or args.remove or live_like) \
            and not looks_web(args.input):
        # предлагаем язык, выбранный в прошлый раз (в первый раз — язык системы), а не всегда русский
        sug = last_lang or locale_lang(args.src)
        q = "На какой язык переводить?"
        while True:
            ans = ask(f"{q} Код языка (ru, uk, en, de, pl, fr, es, ...), "
                      + (f"Enter — {sug}, " if sug else "") + "exit — выйти: ").strip().lstrip("-")
            if not ans and sug:
                ans = sug
            if re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,4})?", ans) and ans.lower() != args.src.lower():
                p = ans.split("-")
                args.dst = p[0].lower() + ("-" + p[1] if len(p) > 1 else "")
                break
            print("Нужен код языка, например: ru, uk, de, pl, fr, es, ja, zh-CN.", file=sys.stderr)
        settings_save(lang=args.dst)
    elif not live_like:
        args.dst = last_lang or "ru"
    if args.dst and not re.fullmatch(r"[a-z]{2,3}(?:-[A-Za-z]{2,4})?", args.dst):
        ap.error(f"непонятный код языка: {args.dst} (примеры: ru, uk, en, de, pt-BR)")
    if not live_like:
        print(f"Язык перевода: {args.dst}", file=sys.stderr)
    LISP["on"], LISP["lang"] = not args.no_lisp, args.dst or "ru"
    CONF["context"] = not args.no_context
    CONF["dst"] = args.dst or "ru"
    if not args.input and not args.check:
        ap.error("укажите игру, например: python sugarcube_translate.py \"Моя игра.html\"")

    modes = ["safe", "full"] if args.mode == "both" else [args.mode]
    OPTS.js, OPTS.gender = not args.no_js, not args.no_gender
    OPTS.values = not args.no_values
    base = dict(GENDER_BASE)
    if args.gender_vars:
        with open(args.gender_vars, encoding="utf-8") as f:
            base.update({k: tuple(v) for k, v in json.load(f).items()})
    for k, (m, f) in base.items():
        GENDER[k] = (m, f)
        GENDER[k[0].upper() + k[1:]] = (m.capitalize(), f.capitalize())
        GENDER[k + "Cap"] = (m.capitalize(), f.capitalize())
    if args.keep:
        with open(args.keep, encoding="utf-8-sig") as f:
            KEEP.update(line.rstrip("\r\n") for line in f if line.strip())
    if args.translate_list:
        with open(args.translate_list, encoding="utf-8-sig") as f:
            MUST.update(line.rstrip("\r\n").strip() for line in f if line.strip())
    glossary = {}
    if args.glossary:
        with open(args.glossary, encoding="utf-8") as f:
            glossary = json.load(f)

    env_keys = {"google-cloud": "GOOGLE_API_KEY", "deepl": "DEEPL_API_KEY", "microsoft": "AZURE_TRANSLATOR_KEY"}
    engine = args.engine or ("google-cloud" if args.key or os.environ.get("GOOGLE_API_KEY") else "free")
    key = args.key or (os.environ.get(env_keys[engine]) if engine in env_keys else None)
    if engine in env_keys and not key:
        raise SystemExit(f"Для переводчика {engine} нужен ключ: --key ВАШ_КЛЮЧ")
    if args.check:
        print(f"Проверка переводчика: {engine}", file=sys.stderr)
        ok = Translator(args.src, args.dst, "", engine, key, args.region).check()
        print("Работает — можно переводить." if ok else
              "Не работает. Подождите несколько часов, отключите VPN или смените сеть; "
              "либо используйте переводчик по ключу: --engine microsoft / deepl / google-cloud.", file=sys.stderr)
        return

    if not os.path.exists(args.input):
        raise SystemExit(f"Не найден файл или папка: {args.input}")
    kind, eg = detect_engine(args.input)
    if kind:
        return run_engine(args, kind, eg, engine, key, glossary)
    if args.remove:
        raise SystemExit("--remove нужен только для Ren'Py и Godot: в SugarCube перевод — отдельный файл, "
                         "оригинал не меняется.")
    game = open_game(args.input)
    game_path = getattr(game, "path", args.input)  # для папки с готовой игрой — путь к её .html
    outputs = output_paths(game_path, args.output, args.dst or "ru")
    already = any("Добавлено sugarcube_translate" in p["body"] for p in game.passages if "script" in p["tags"])
    if isinstance(game, WebApp):
        already = "sugarcube_translate: перевод на лету" in game.text
    if already and not args.force:
        raise SystemExit("Это уже переведённая версия игры (в ней есть код, добавленный этим скриптом).\n"
                         "Переводите ОРИГИНАЛЬНЫЙ английский файл: старые переводы возьмутся из кэша, а новые "
                         "исправления (связность фраз, «is», род) сработают только на оригинале.\n"
                         "Если всё же нужно — добавьте --force.")
    letters = "".join(p["body"] for p in game.passages if "script" not in p["tags"])[:3_000_000]
    n_lat, n_cyr = len(re.findall(r"[A-Za-z]", letters)), len(re.findall(r"[А-Яа-яЁёІіЇїЄє]", letters))
    if n_cyr > 0.3 * (n_lat + n_cyr) and not args.force:
        print("Внимание: в игре уже много кириллицы — похоже, файл уже переведён. Лучше переводить оригинал.",
              file=sys.stderr)
    fmt = game.format()
    if fmt and "sugarcube" not in fmt.lower() and not args.force and not live_like:
        if fmt == "web" or isinstance(game, HtmlFile):
            raise SystemExit(f"Это игра не на SugarCube ({'HTML/JavaScript' if fmt == 'web' else fmt}): её текст собирается "
                             "другим движком, заранее его не перевести без поломок.\nДля неё есть перевод на лету — "
                             "переводится то, что видно на экране:\n"
                             f"  python sugarcube_translate.py \"{args.input}\" -l   (файл, который работает сам)\n"
                             f"  python sugarcube_translate.py \"{args.input}\" -c   (через окно скрипта)")
        raise SystemExit(f"Формат игры: {fmt}. Скрипт рассчитан на SugarCube; другие форматы (Harlowe и т.д.) "
                         f"используют другую разметку. Если всё равно хотите попробовать — добавьте --force.")
    passages = game.passages
    scan_lisp(passages)
    if live_like:
        return run_live(args, game, game_path, engine, key, glossary)
    print("Разбор игры...", file=sys.stderr)
    harvest(passages)
    skip_re = re.compile(args.skip) if args.skip else None

    for p in passages:
        CUR["passage"] = p["name"]
        body = p["body"]
        if (p["tags"] & SKIP_TAGS or p["name"] in SKIP_NAMES
                or (skip_re and skip_re.search(p["name"]))):
            p["mode"] = None
        elif "script" in p["tags"]:
            p["mode"] = "js" if OPTS.js else None
            if p["mode"]:
                CUR["pure_js"] = True
                try:
                    p["seq"] = process_js(body, "data")
                finally:
                    CUR["pure_js"] = False
        else:
            p["mode"] = "markup"
            p["seq"] = build_markup(body)

    # род по умолчанию: если игра почти всегда говорит «she» — женский, «he» — мужской
    if args.gender_default == "auto":
        f, m = GENDER_LIT["f"], GENDER_LIT["m"]
        CONF["gdefault"] = "f" if f >= 20 and f >= 4 * m else "m" if m >= 20 and m >= 4 * f else None
        why = f"(в коде игры «she/her»: {f}, «he/his»: {m})"
    else:
        CONF["gdefault"] = None if args.gender_default == "none" else args.gender_default
        why = "(задано флагом)"
    print("Род по умолчанию для фраз только с именем: "
          + {"f": "женский", "m": "мужской", None: "не задан"}[CONF["gdefault"]] + " " + why, file=sys.stderr)

    # решения для каждого режима (сама разметка разбирается один раз)
    for mode in modes:
        OPTS.aggressive = mode == "full"
        for u in JSUNITS:
            if isinstance(u, Str):
                u.claimed = False
        for c in CHAINS:
            c.finalize()
        for u in JSUNITS:
            if not isinstance(u, Chain):
                u.finalize()
        # одна и та же строка должна быть переведена либо везде, либо нигде — иначе ломаются сравнения
        seen = {}
        for u in JSUNITS:
            k = unit_value(u)
            if k is not None:
                seen.setdefault(k, [False, False])[0 if u.active else 1] = True
        mixed = {k for k, (a, i) in seen.items() if a and i}
        for u in JSUNITS:
            if u.active and unit_value(u) in mixed:
                u.active, u.reason = False, "эта же строка в другом месте игры — ключ/данные"
                u.text.active = False
        for u in JSUNITS:
            u.modes[mode] = u.active
            u.reasons = getattr(u, "reasons", {})
            u.reasons[mode] = getattr(u, "reason", "")

    if args.analyze:
        path = analyze(game, passages, modes, game_path.rstrip("/\\") + ".structure.txt",
                       shutil.which("node") is not None)
        size = os.path.getsize(path)
        print(f"Готово: {path} ({size / 1024:.0f} КБ). Текст игры в нём заменён на T — "
              f"этот файл можно прислать для настройки перевода.", file=sys.stderr)
        return

    in_base = game_path.rstrip("/\\")
    cache_path = args.cache or in_base + "." + args.dst + ".cache.json"
    tr = Translator(args.src, args.dst, cache_path, engine, key, args.region, args.delay, glossary,
                    args.max_chars, args.max_wait)
    if args.fresh:
        tr.start_fresh()
    elif tr.cache_old and not args.reuse_cache and not (args.dry_run or args.analyze):
        n_old = sum(1 for k in tr.cache if not k.startswith("\u0001"))
        print(f"\nКэш перевода создан старой версией скрипта ({n_old:,} фраз). В новой версии фразы готовятся\n"
              f"для переводчика иначе, поэтому лучше перевести игру заново (это займёт время и лимиты).",
              file=sys.stderr)
        if sys.stdin.isatty():
            ans = ask("Начать перевод заново? Старый кэш сохранится как .bak  [Д/н, exit — выйти]: ", "н").strip().lower()
            if ans in ("", "д", "да", "y", "yes", "l"):
                tr.start_fresh()
            else:
                print("Продолжаю со старым кэшем.", file=sys.stderr)
                tr.cache_old = False
        else:
            print("Продолжаю со старым кэшем (чтобы начать заново — флаг --fresh).", file=sys.stderr)
            tr.cache_old = False

    def todo(reqs):
        return [s for s in reqs if not tr.has(s)]

    def chars(reqs):
        return sum(map(len, todo(reqs)))

    per_mode = {}
    for mode in modes:
        set_mode(mode)
        per_mode[mode] = list(dict.fromkeys(r for t in TEXTS for r in t.requests()))
    done_in_code = {u.val for u in JSUNITS if isinstance(u, Str) and u.val and u.modes
                    and all(u.modes.get(m) for m in modes)}
    lisp_pairs = LISP_SCAN["pairs"]
    letter_vals = {w.lower() for w in LISP_SCAN["widgets"]} | {"th"}
    values = [] if args.no_values else sorted(
        v for v in VALUE_CANDS if value_candidate(v) and v not in done_in_code
        and v not in lisp_pairs and v.lower() not in letter_vals)
    values = sorted(set(values) | {w for w in lisp_pairs.values() if not args.no_values})
    print(f"Пассажей: {len(passages)}, переводим: {sum(1 for p in passages if p['mode'])}", file=sys.stderr)
    safe_set = set(per_mode.get("safe", []))
    if "safe" in per_mode:
        left = todo(per_mode["safe"])
        print(f"SAFE: {len(per_mode['safe']):,} фраз; ещё не переведено {len(left):,} "
              f"({chars(left):,} символов)", file=sys.stderr)
    if "full" in per_mode:
        extra = [r for r in per_mode["full"] if r not in safe_set] if safe_set else per_mode["full"]
        left = todo(extra)
        label = "FULL дополнительно к safe" if safe_set else "FULL"
        print(f"{label}: {len(extra):,} фраз; ещё не переведено {len(left):,} ({chars(left):,} символов)",
              file=sys.stderr)
    for u in JSUNITS:  # включаем всё, что нужно хотя бы одной версии
        u.active = any(u.modes.values())
        if isinstance(u, Chain):
            u.merged = u.active
        if u.text is not None:
            u.text.active = u.active
    gvar = list(dict.fromkeys(t.localize(v)[0] for t in TEXTS
                              if t.active and t.group and needs_translation(t.core) for v in ("m", "f")))
    if gvar:
        print(f"  из них вариантов «он/она»: {chars(gvar):,} символов (без них: --no-gender)", file=sys.stderr)
    ctx_all = [r for r in dict.fromkeys(r for m in modes for r in per_mode[m]) if r in CTX_REQS]
    if ctx_all:
        print(f"  из них подсказок контекста для коротких фраз: {len(ctx_all):,}; ещё не переведено "
              f"{chars(ctx_all):,} символов (без них: --no-context)", file=sys.stderr)
    value_reqs = list(dict.fromkeys(value_hint(v) or v for v in values))
    if values:
        left = todo(value_reqs)
        print(f"Значения переменных для показа (white → белый и т.п.): {len(values):,}; ещё не переведено "
              f"{len(left):,} ({chars(left):,} символов; без них: --no-values)", file=sys.stderr)
    if tr.redo:
        print(f"В кэше {tr.redo:,} фраз, которые переводчик раньше вернул без перевода, — переведу их заново.",
              file=sys.stderr)
    allreq = list(dict.fromkeys(r for m in modes for r in per_mode[m]))
    if allreq:
        done_n = sum(1 for r in allreq if tr.has(r))
        print(f"Всего переведено: {done_n / len(allreq):.1%} ({done_n:,} из {len(allreq):,} фраз)", file=sys.stderr)
    print(f"Переводчик: {engine}" + (" (бесплатный)" if engine in ("free", "google") else ""),
          file=sys.stderr)
    if args.dry_run:
        return

    # какие адреса Google работают — запросы будут идти по кругу только на них
    if engine in ("free", "google") and any(todo(per_mode[m]) for m in modes):
        n_ok = tr.probe()
        if args.fast:
            tr.workers = max(1, min(n_ok, 6))
    elif args.fast:
        tr.workers = 3
    if tr.workers > 1:
        print(f"Быстрый режим: {tr.workers} запроса одновременно.", file=sys.stderr)

    # перевод: сначала всё для safe, потом недостающее для full — каждая фраза один раз
    try:
        for mode in modes:
            print(f"Перевод ({mode})...", file=sys.stderr)
            tr.prefetch(per_mode[mode])
        if values:
            print("Перевод значений переменных (только для показа)...", file=sys.stderr)
            tr.prefetch(value_reqs)
        # сборка из кэша; чего не хватило (имя-подсказка потерялась, переводчик испортил метки) —
        # переводим отдельно и собираем ещё раз
        pending = [t for t in TEXTS if t.active]
        for rnd in range(3):
            need = []
            for t in pending:
                need += t.apply(tr)
            need = [x for x in dict.fromkeys(need) if not tr.has(x)]
            pending = [t for t in pending if t.out.get("n") is None and needs_translation(t.core)]
            if not need or tr.offline or not pending:
                break
            print(f"Дополнительный перевод: {len(need):,} фраз", file=sys.stderr)
            tr.prefetch(need)
        for t in TEXTS:
            t.apply_fallback(tr)
    except KeyboardInterrupt:
        tr.halt.set()
        tr.save(force=True)
        print("\nОстановлено. Кэш сохранён — запустите ту же команду, чтобы продолжить.", file=sys.stderr)
        sys.stderr.flush()
        os._exit(1)  # не ждём фоновые потоки с их сетевыми запросами
    except Exception:
        tr.save(force=True)
        print("\nНеожиданная ошибка. Всё переведённое сохранено в кэше — пришлите текст ниже.", file=sys.stderr)
        raise
    tr.save(force=True)
    partial = None
    if tr.offline:
        allreq = list(dict.fromkeys(r for m in modes for r in per_mode[m]))
        done_n = sum(1 for r in allreq if tr.has(r))
        partial = done_n / len(allreq) if allreq else 1.0
        print(f"\nПеревод остановлен: {tr.stop_reason}.", file=sys.stderr)
        if done_n == 0:
            print("Пока не переведено ни одной фразы, поэтому файлы игры не создаю. Что делать: "
                  "подождите несколько часов и запустите снова; проверить доступ можно командой "
                  "python sugarcube_translate.py --check", file=sys.stderr)
            return
        print(f"Переведено {partial:.0%} фраз. Соберу игру с тем, что есть (остальное — на английском). "
              f"Запустите ту же команду позже — продолжится с этого места.", file=sys.stderr)

    have_node = shutil.which("node") is not None
    vmap = {}
    # значения, где подсказка «свойство: значение» не сработала, — переводим как есть, одной пачкой
    redo = [v for v in values if value_hint(v) and tr.has(value_hint(v))
            and hint_result(tr.get(value_hint(v))) is None and not tr.has(v)]
    if redo and not tr.offline:
        try:
            tr.prefetch(redo, quiet=True)
        except KeyboardInterrupt:
            tr.save(force=True)
            raise
    for v in values:
        h = value_hint(v)
        t = hint_result(tr.get(h)) if h and tr.has(h) else None
        if t is None:  # подсказка не сработала (или её нет) — значение как есть
            t = tr.get(v) if (tr.has(v) or not tr.offline) else None
        if t and t.strip() and t.strip() != v and not untranslated(v, t, args.dst):
            if STUTTER_EN.search(v):
                t = fix_stutter(t, v)
            t = re.sub(r"[<>\[\]{}$@|\\]", "", sanitize(clean_copula(t))).strip()
            if t:
                vmap[v] = t
    for v, w in lisp_pairs.items():  # Mathter → «Маштер»: шепелявим перевод обычного слова, а не гадаем
        if w in vmap and v not in vmap:
            vmap[v] = lisp_text(vmap[w])
    if not args.no_values and (any(t.group for t in TEXTS) or any(
            isinstance(i, Raw) and i.kind == "var" and gender_info(i) for i in ITEMS)):
        # слова-местоимения для переменных рода там, где нет развилки «она/он» ("she" → «она»)
        if args.dst.lower().startswith("ru"):
            pron = dict(PRONOUNS_RU)
        else:
            words = list(PRONOUNS_RU)
            tr.prefetch(words, quiet=True)
            pron = {w: tr.get(w) for w in words if tr.get(w)}
        for w, t in pron.items():
            for a, b in ((w, t), (w.capitalize(), t[:1].upper() + t[1:])):
                vmap.setdefault(a, b)
    VALUES["on"], VALUES["map"] = bool(vmap), vmap
    ui = not args.no_ui
    ui_map = ui_strings(tr, args.dst) if ui else None
    ui = bool(ui_map)
    for mode in modes:
        set_mode(mode)
        game.reset()
        print(f"Сборка и проверка ({mode})...", file=sys.stderr)
        reverted, used_gender, used_lisp, kept = [], False, False, []
        for p in passages:
            if not p.get("mode"):
                continue
            CUR["passage"] = p["name"]
            orig = p["body"]
            p.pop("lines_kept", None)
            ok, new, _ = render_checked(p, have_node)
            if p.get("lines_kept"):
                kept.append((p["name"], p["lines_kept"]))
            if ok:
                if new != orig:
                    p["new"] = new
                used_gender = used_gender or "ruGender(" in new
                used_lisp = used_lisp or "ruIsLisp(" in new
            else:
                reverted.append(p["name"])
        copula_fix = not args.no_is_fix and no_copula_lang()
        if used_gender or ui or vmap or used_lisp or copula_fix:
            if not game.inject(prelude_js(used_gender, ui, vmap, ui_map, used_lisp, copula_fix)):
                print("Внимание: не нашёл, куда добавить служебный JavaScript.", file=sys.stderr)
        out = outputs[mode]
        game.save(out)
        rep = out.rstrip("/\\") + ".report.tsv"
        write_report(rep, mode, reverted, kept)
        skipped = write_skipped(out.rstrip("/\\") + ".skipped.tsv", mode)
        print(f"Готово ({mode}): {out}" + (f"  [переведено частично: {partial:.0%}]" if partial is not None
                                              else ""), file=sys.stderr)
        print(f"  отчёт: {rep}", file=sys.stderr)
        print(f"  не переведено строк кода: {skipped:,} — список с причинами: "
              f"{out.rstrip(chr(47) + chr(92))}.skipped.tsv", file=sys.stderr)
        if reverted:
            print(f"  внимание: {len(reverted)} пасс. оставлено на английском (не прошли проверку), "
                  f"список в конце отчёта", file=sys.stderr)
    game.reset()


if __name__ == "__main__":
    sys.setrecursionlimit(10000)
    try:
        rc = main()
    except KeyboardInterrupt:  # Ctrl+C или exit в любой момент: выбор языка, вопрос про кэш, разбор игры
        print("\nОтменено.", file=sys.stderr)
        sys.stderr.flush()
        os._exit(1)
    if _CONSOLE["q"] is not None:  # поток, читающий консоль, не даст Python закрыться обычным путём
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(rc if isinstance(rc, int) else 0)
