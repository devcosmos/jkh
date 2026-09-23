/** Русское склонение существительного/словосочетания по числу — "1 новый риск, 2 новых
 * риска, 5 новых рисков" (плашки-счётчики на «Обзоре» и «Рисках»). Стандартное правило:
 * ...1 (кроме ...11) — one, ...2-4 (кроме ...12-14) — few, всё остальное — many. */
export function pluralizeRu(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && !(mod100 >= 12 && mod100 <= 14)) return few;
  return many;
}
