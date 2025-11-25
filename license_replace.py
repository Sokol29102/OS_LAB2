#!/usr/bin/env python3
from __future__ import annotations #це тут для кращої типізації

import argparse #щоб ловити аргументи з терміналу
import difflib #для порівняння (обчислює схожість коротше)
import re #оце нормалізує текст (для регулярних виразів)
import subprocess #щоб викликати grep та sed
from dataclasses import dataclass #оце для зручних класів структур
from pathlib import Path #для легшої роботи з шляхами
from typing import Optional, Tuple, Iterable #підсказки


@dataclass(frozen=True) #щоб не міняли фроузен
class Header:
    raw: str #бере просто сирий текст як у файлі
    body: str #сирий текст всередині коментаря
    style: str #який там стиль типу блок або строка кожна окрема


def read(path: Path) -> str: #оце перетворює файл в рядок
    return path.read_text(encoding="utf-8") #дивимось файл як текст і перетворюємо в стрінг


def write(path: Path, text: str) -> None: #тут щоб записувати в файл
    path.write_text(text, encoding="utf-8") #записуємо текст в файл


def c_files(root: Path, recursive: bool) -> Iterable[Path]: #виписує всі .c
    return (
        p
        for p in (root.rglob("*.c") if recursive else root.glob("*.c"))
        if p.is_file()
    ) #генерує нам шляхи до файлів (може рекурсивно)


def extract_header(src: str) -> Optional[Header]: #витягує нам коментар який хедер зверху файла
    i, n = 0, len(src) #"i" це позиція в тексті, "n" його довжина
    if src.startswith("\ufeff"): #якщо текст починається з BOM
        i += 1 #пропускаємо BOM
    while i < n and src[i] in " \t\r\n": #пропускаємо початкові пробіли, таби та переноси рядків
        i += 1 #вперед по тексту
    if i >= n: #якщо ми дійшли до кінця
        return None #нема нічого то повертаємо None

   #отут дивимось коментарі які йдуть //
    if src.startswith("//", i): #якщо починається коментар з //
        start = i #записуємо початок
        body_lines, j = [], i #body_lines — список рядків "тіла" коментаря, j — поточна позиція для читання рядків
        while j < n and src.startswith("//", j): #поки наступний рядок теж починається з //
            end = src.find("\n", j) #знаходимо кінець рядка (символ нового рядка)
            if end == -1: #якщо символ нового рядка не знайдено (коментар до кінця файлу)
                line = src[j:] #беремо все до кінця тексту
                j = n #йдемо в кінець тексту
            else: #якщо знайшли кінець рядка
                line = src[j:end] #беремо підрядок від j до end
                j = end + 1 #переходимо на наступний символ після \n
            body_lines.append(line[2:].lstrip()) #відкидаємо '//' і ліві пробіли та додаємо в список
        raw = src[start:j] #сирий коментар весь блок послідовних рядків з //
        body = "\n".join(body_lines).rstrip("\n") #склеюємо очищені рядки в один текст тіла коментаря
        return Header(raw, body, "line") #повертаємо об’єкт Header для стилю "line"

    if src.startswith("/*", i): #якщо на поточній позиції починається блочний коментар
        start = i #запам’ятовуємо початок блоку коментаря
        end = src.find("*/", i + 2) #шукаємо */
        if end == -1: #якщо нема */
            return None #то коментар неправильний
        end += 2 #переміщаємося за "*/" (він там заходить в сирий текст)
        raw = src[start:end] #тут текст блочного коментаря від start до end
        inner = raw[2:-2] #вирізаємо з сирого тексту /* і */
        lines = inner.splitlines() #розбиваємо внутрішній текст на рядки
        if lines and not lines[0].strip(): #якщо перший рядок порожній (наприклад чисто пробіли)
            lines = lines[1:] #пропускаємо перший порожній рядок

        cleaned = [] #сюди будемо збирати очищені рядки без ведучих '*'
        for ln in lines: #проходимо по кожному рядку всередині блочного коментаря
            s = ln.lstrip() #прибираємо пробіли зліва
            if s.startswith("*"): #якщо рядок починається з '*'
                s = s[1:].lstrip() #відрізаємо '*' і ще раз прибираємо пробіли зліва
            cleaned.append(s) #додаємо очищений рядок у список
        while cleaned and not cleaned[-1].strip(): #прибираємо порожні рядки з кінця
            cleaned.pop() #видаляємо останній рядок якщо він порожній
        body = "\n".join(cleaned).rstrip("\n") #склеюємо очищені рядки в текст тіла
        return Header(raw, body, "block") #повертаємо Header для стилю "block"

    return None #якщо не знайшли ні //, ні /* на початку то повертаємо None (немає коментаря)


def norm(text: str) -> str: #нормалізація тексту для коректного порівняння
    t = text.lower() #переводимо текст у нижній регістр
    t = re.sub(r"[=*#\-_/\\]+", " ", t) #замінюємо послідовності спеціальних символів на пробіл
    t = re.sub(r"\s+", " ", t).strip() #стискаємо всі пробільні символи до одного пробілу і обрізаємо з країв
    return t #повертаємо нормалізований текст


def sim(a: str, b: str) -> float: #обчислення схожості двох текстів
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio() #порівнюємо нормалізовані рядки і повертаємо коефіцієнт [0..1]


def format_body(body: str, style: str) -> str: #формуємо текст нового хедера з "тіла" ліцензії в потрібному стилі
    lines = body.splitlines() or [body] #розбиваємо тіло ліцензії на рядки, якщо немає \n — один рядок
    if style == "line": #якщо потрібен рядковий стиль (ну формата //)
        return (
            "\n".join("// " + ln if ln.strip() else "//" for ln in lines) + "\n"
        ) #для кожного рядка додаємо // (або просто // для порожніх рядків) і завершуємо \n
    if style == "block": #якщо потрібен блочний стиль (тут короче /* і оце */)
        out = ["/*"] #починаємо блок з /* на окремому рядку
        for ln in lines: #проходимо по кожному
            out.append(" * " + ln if ln.strip() else " *") #для непорожніх рядків додаємо " * текст", а для" *"
        out.append(" */\n") #додаємо закриваючий рядок " */" і завершальний перенос
        return "\n".join(out) #склеюємо всі рядки в один текст блочного коментаря
    raise ValueError(style) #якщо стиль невідомий, то помилка


def replace_header(src: str, new_header: str) -> Tuple[str, bool]: #замінюємо коментар у тексті файлу
    h = extract_header(src) #пробуємо витягнути існуючий коментар з файлу
    if not h: #якщо коментаря нема
        return new_header + src, True #просто додаємо новий коментар на початок файлу і повертаємо що були зміни
    start = src.find(h.raw) #знаходимо позицію сирого коментаря в тексті
    end = start + len(h.raw) #обчислюємо позицію кінця коментаря
    return (
        src[:start] + new_header + src[end:].lstrip("\n"),
        True,
    ) #замінюємо старий коментарь на новий і прибираємо зайві порожні рядки після нього


def parse_args() -> argparse.Namespace: #розбір аргументів командного рядка
    p = argparse.ArgumentParser( #створюємо парсер аргументів
        description="замінює ліцензії в файлах" #Опис утиліти
    )
    p.add_argument(
        "--dir", required=True, type=Path, help="Directory with .c files"
    ) #папка з файлами які треба міняти
    p.add_argument(
        "--source-exemplar",
        required=True,
        type=Path, #приклад файла з ліцензією яку міняти
        help="file with old license header",
    )
    p.add_argument(
        "--target-exemplar",
        required=True,
        type=Path, #приклад на яку заміняти
        help="file with new license header",
    )
    p.add_argument(
        "--recursive",
        action="store_true", #шукати в папках і підпапках рекурсивно короче
        help="recurse into subdirectories",
    )
    p.add_argument(
        "--threshold",
        type=float,
        default=0.75, #наскільки схожими воно буде рахувати їх
        help="similarity threshold from 0 to 1",
    )
    return p.parse_args() #забираємо аргументи


def main() -> int:
    args = parse_args()
    if not args.dir.is_dir(): #дивимось чи директорія яку сказали взагалі існує
        print(f"там взагалі нічого нема ->{args.dir}")
        return 2

    src_h = extract_header(read(args.source_exemplar))
    tgt_h = extract_header(
        read(args.target_exemplar)
    ) #тут витягуємо нову (щоб не забути що ці дві строки роблять)
    if not src_h: #якщо у зразку старої ліц. нема коментаря з ліцензією то дивимось
        print("у старому файлі пусто")
        return 2
    if not tgt_h: #і якщо в новому
        print("у новому файлі пусто")
        return 2

    scanned = changed = 0 #лічильники
    for path in c_files(args.dir, args.recursive): #проходимо по всіх файлах в папці( і в папках в папці теж)
        scanned += 1

       #тут ми добавляємо греп
       #grep -q "GPL" file.c як воно б вконсолі було б
        grep_proc = subprocess.run(
            ["grep", "-q", "GPL", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if grep_proc.returncode == 1:
           #якшо у файлі немає GPL то навіть не пробуємо
            continue
        if grep_proc.returncode not in (0, 1):
           #якась помилка grep то пропускаємо
            print(f"grep помилка для {path}, пропускаю")
            continue

        text = read(path)
        fh = extract_header(text)
        if not fh: #якщо нема ліцензії
            continue

        if sim(fh.body, src_h.body) < args.threshold: #якщо не достатньо схоже на стару ліцензію
            continue

        new_header = format_body(
            tgt_h.body, fh.style
        ) #робимо новий коментар з тіла нової ліцензії в ідентичній формі (ну або блок або строки)
        new_text, _ = replace_header(text, new_header) #замінюємо текст в пам'яті
        write(path, new_text) #а потім у файл.

       #туто добавили сед, воно тупо прибирає пробіли і таби в кінці рядків
       #sed -i 's/[ \t]*$//' file.c    типу консольна версія
        subprocess.run(
            ["sed", "-i", r"s/[ \t]*$//", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        changed += 1
        print(f"оновлено: {path}")

    print(f"проскановано={scanned}, змінено={changed}")
    return 0


if __name__ == "__main__": #якщо цей файл просто напряму запустили то просто виконати і повернути результат
    raise SystemExit(main())
