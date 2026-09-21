// Единый стиль для интерактивных элементов управления (кнопки, селекты, поля ввода) —
// раньше они были белыми, как и карточки/таблицы, и визуально сливались с некликабельным
// фоном. Карточки и таблицы остаются белыми; управляющие элементы выделены голубым
// оттенком, с двумя уровнями: акцентная (SOLID) кнопка для главного действия и
// второстепенная (SECONDARY) — для всего остального, включая поля ввода и селекты.

/** Второстепенная кнопка/поле — бледно-голубой фон и рамка вместо белого. */
export const SECONDARY_CONTROL =
  "border border-sky-200 bg-sky-50 text-slate-700 transition-colors hover:border-sky-300 hover:bg-sky-100 hover:text-slate-900";

/** То же самое, но для текстовых полей: на фокусе поле "выбеливается" и получает
 * кольцо — тогда видно, где именно курсор, а не просто общий голубой тон. */
export const SECONDARY_FIELD =
  "border border-sky-200 bg-sky-50 text-slate-900 outline-none transition-colors focus:border-sky-400 focus:bg-white focus:ring-4 focus:ring-sky-100";

/** Акцентная (primary) кнопка — главное действие на экране/в форме. */
export const PRIMARY_CONTROL = "bg-sky-500 text-white transition-colors hover:bg-sky-600";
